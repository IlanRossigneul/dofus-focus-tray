import logging
import socket

import evdev

from input.classifier import DeviceClass
from shortcuts.model import Shortcut

from .commands import HelperContext, send_error
from .devices import HelperDevice
from .keyboard import MODIFIER_KEY_NAMES
from .mouse import is_allowed_mouse_button_event
from .protocol import (
    ERROR_DEVICE_ERROR,
    EVENT_KEYBOARD_EVENT,
    EVENT_MOUSE_BUTTON_EVENT,
    EVENT_SHORTCUT,
)
from .state import HelperState

logger = logging.getLogger(__name__)


def process_input(
    context: HelperContext,
    state: HelperState,
    readable: list[int | socket.socket],
    new_reader_fds: set[int],
    selected_events: list[tuple[HelperDevice, evdev.InputEvent]],
) -> bool:
    """Process input events and return whether the main loop must continue."""
    reader_fds = set(context.reader.get_watched_fds())

    input_fds = [
        fd
        for fd in readable
        if (isinstance(fd, int) and fd in reader_fds and fd not in new_reader_fds)
    ]

    input_events = list(selected_events)

    if input_fds:
        input_events.extend(
            context.reader.read_ready(input_fds),
        )

    for device, event in input_events:
        if (
            device.device_class == DeviceClass.KEYBOARD
            and event.type == evdev.ecodes.EV_KEY
        ):
            context.keyboard_state.update(event)
            context.xkb.update_key(
                event.code,
                event.value,
            )

            if state.capture_active:
                if event.value != 1:
                    continue

                if event.code in MODIFIER_KEY_NAMES:
                    continue

                modifiers = context.keyboard_state.get_modifiers()

                if not modifiers:
                    continue

                context.server.send_event(
                    {
                        "type": EVENT_KEYBOARD_EVENT,
                        "device_id": device.device_id,
                        "code": event.code,
                        "value": event.value,
                        "timestamp": event.timestamp(),
                        "modifiers": sorted(modifiers),
                    }
                )
                continue

            if event.value != 1:
                continue

            if event.code in MODIFIER_KEY_NAMES:
                continue

            trigger = Shortcut(
                trigger=context.xkb.keycode_to_key(
                    event.code,
                ),
            ).trigger

            action = state.input_policy.get_keyboard_action(
                trigger,
                context.keyboard_state.get_modifiers(),
            )

            if action is None:
                continue

            context.server.send_event(
                {
                    "type": EVENT_SHORTCUT,
                    "action": action.value,
                }
            )

        elif device.device_class == DeviceClass.MOUSE:
            if not state.capture_active:
                continue

            if not is_allowed_mouse_button_event(event):
                continue

            context.server.send_event(
                {
                    "type": EVENT_MOUSE_BUTTON_EVENT,
                    "device_id": device.device_id,
                    "code": event.code,
                    "value": event.value,
                    "timestamp": event.timestamp(),
                }
            )

    if (
        state.capture_active
        and state.mouse_grabber is not None
        and state.mouse_grabber.is_started()
        and state.mouse_interceptor is None
        and state.mouse_grabber.get_device().fileno() in readable
    ):
        try:
            events = state.mouse_grabber.get_device().read()

            if state.selected_mouse is not None:
                for event in events:
                    if not is_allowed_mouse_button_event(event):
                        continue

                    context.server.send_event(
                        {
                            "type": EVENT_MOUSE_BUTTON_EVENT,
                            "device_id": state.selected_mouse.device_id,
                            "code": event.code,
                            "value": event.value,
                            "timestamp": event.timestamp(),
                        }
                    )
        except OSError as error:
            logger.error(
                "Failed to read grabbed mouse during capture: %s",
                error,
            )

            send_error(
                context.server,
                ERROR_DEVICE_ERROR,
                "Failed to read the selected mouse.",
            )

            return True

    if (
        state.mouse_interceptor is not None
        and state.mouse_interceptor.is_started()
        and state.mouse_interceptor.fileno() in readable
    ):
        try:
            events = state.mouse_interceptor.read()

            for event in events:
                if state.selected_mouse is None:
                    continue

                if state.capture_active:
                    if is_allowed_mouse_button_event(event):
                        logger.debug(
                            "Mouse capture event: code=%s value=%s.",
                            event.code,
                            event.value,
                        )

                        context.server.send_event(
                            {
                                "type": EVENT_MOUSE_BUTTON_EVENT,
                                "device_id": state.selected_mouse.device_id,
                                "code": event.code,
                                "value": event.value,
                                "timestamp": event.timestamp(),
                            }
                        )

                    continue

                if event.type == evdev.ecodes.EV_KEY and event.value in (0, 1):
                    logger.debug(
                        "Mouse button event: code=%s value=%s.",
                        event.code,
                        event.value,
                    )

                if event.type == evdev.ecodes.EV_KEY and event.value == 1:
                    action = state.input_policy.get_mouse_action(
                        event.code,
                    )

                    if action is not None:
                        logger.debug(
                            "Mouse shortcut triggered: code=%s action=%s.",
                            event.code,
                            action,
                        )

                        context.server.send_event(
                            {
                                "type": EVENT_SHORTCUT,
                                "action": action.value,
                            }
                        )

                intercepted = state.mouse_interceptor.should_intercept(
                    event,
                )

                if event.type == evdev.ecodes.EV_KEY and event.value in (0, 1):
                    logger.debug(
                        "Mouse event forwarding: code=%s value=%s intercepted=%s.",
                        event.code,
                        event.value,
                        intercepted,
                    )

                if not intercepted:
                    state.mouse_interceptor.forward_event(event)

        except OSError as error:
            logger.error(
                "Failed to read intercepted mouse: %s",
                error,
            )

            selected_device = state.selected_mouse

            state.mouse_interceptor.stop()
            state.mouse_interceptor = None

            if selected_device is not None and state.capture_active:
                context.reader.add_device(selected_device)

            send_error(
                context.server,
                ERROR_DEVICE_ERROR,
                "Failed to read the selected mouse.",
            )

            return True

    return False
