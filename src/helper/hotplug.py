import logging
import socket
import time

import evdev

from .commands import (
    HelperContext,
    get_keyboard_devices,
    get_mouse_devices,
    stop_mouse_interception,
)
from .devices import HelperDevice, discover_devices
from .protocol import (
    EVENT_KEYBOARD_SELECTED,
    EVENT_KEYBOARD_SELECTED_LOST,
    EVENT_MOUSE_SELECTED,
    EVENT_MOUSE_SELECTED_LOST,
)
from .state import HelperState

logger = logging.getLogger(__name__)

MOUSE_DISCOVERY_RETRY_DELAY = 1.0


def process_mouse_discovery(
    context: HelperContext,
    state: HelperState,
) -> None:
    """Retry mouse discovery when the scheduled discovery time is reached."""
    if (
        not state.input_monitoring_active
        or state.next_mouse_discovery is None
        or time.monotonic() < state.next_mouse_discovery
        or state.selected_mouse is not None
        or context.mouse_selector.is_active()
    ):
        return

    logger.info("Starting mouse discovery.")

    discovered_devices = discover_devices()

    _, _, state.current_devices = context.registry.reconcile(
        discovered_devices,
    )

    context.mouse_selector.start(
        get_mouse_devices(state.current_devices),
    )

    state.next_mouse_discovery = None


def process_keyboard_selector(
    context: HelperContext,
    state: HelperState,
    readable: list[int | socket.socket],
    selected_events: list[tuple[HelperDevice, evdev.InputEvent]],
) -> set[int]:
    """Process the keyboard selector."""
    new_reader_fds: set[int] = set()

    if context.keyboard_selector.is_active():
        reader_fds_before_selection = set(
            context.reader.get_watched_fds(),
        )

        selector_fds = set(
            context.keyboard_selector.get_watched_fds(),
        )

        ready_selector_fds = [
            fd for fd in readable if isinstance(fd, int) and fd in selector_fds
        ]

        selected = context.keyboard_selector.process_ready(
            ready_selector_fds,
        )

        if selected is not None:
            selected_keyboard, events = selected

            state.selected_keyboard = selected_keyboard

            logger.info(
                "Keyboard selected: %s.",
                selected_keyboard.info.name,
            )

            context.reader.add_device(selected_keyboard)

            selected_events.extend((selected_keyboard, event) for event in events)

            context.server.send_event(
                {
                    "type": EVENT_KEYBOARD_SELECTED,
                    "device_id": selected_keyboard.device_id,
                }
            )

            new_reader_fds = (
                set(context.reader.get_watched_fds()) - reader_fds_before_selection
            )

    return new_reader_fds


def process_mouse_selector(
    context: HelperContext,
    state: HelperState,
    readable: list[int | socket.socket],
    selector_timeout: float | None,
    selected_events: list[tuple[HelperDevice, evdev.InputEvent]],
) -> None:
    """Process the mouse selector."""
    if not context.mouse_selector.is_active():
        return

    selector_fds = set(context.mouse_selector.get_watched_fds())

    ready_selector_fds = [
        fd for fd in readable if isinstance(fd, int) and fd in selector_fds
    ]

    selected = context.mouse_selector.process_ready(
        ready_selector_fds,
    )

    if selected is not None:
        selected_mouse, events = selected

        state.selected_mouse = selected_mouse

        logger.info(
            "Mouse selected: %s.",
            selected_mouse.info.name,
        )

        selected_events.extend((selected_mouse, event) for event in events)

        context.server.send_event(
            {
                "type": EVENT_MOUSE_SELECTED,
                "device_id": selected_mouse.device_id,
            }
        )

        state.next_mouse_discovery = None

    elif selector_timeout is not None and selector_timeout <= 0:
        context.mouse_selector.stop()

        if state.input_monitoring_active and state.selected_mouse is None:
            state.next_mouse_discovery = time.monotonic() + MOUSE_DISCOVERY_RETRY_DELAY


def process_device_changes(
    context: HelperContext,
    state: HelperState,
    readable: list[int | socket.socket],
) -> None:
    """Process input device additions and removals."""
    monitor_fd = context.reader.get_device_monitor_fd()

    if not (
        state.input_monitoring_active
        and monitor_fd is not None
        and monitor_fd in readable
        and context.reader.device_changes_pending()
    ):
        return

    discovered_devices = discover_devices()

    _, removed_devices, state.current_devices = context.registry.reconcile(
        discovered_devices,
    )

    selected_keyboard_removed = state.selected_keyboard is not None and any(
        device.device_id == state.selected_keyboard.device_id
        for device in removed_devices
    )

    if selected_keyboard_removed:
        previous_keyboard = state.selected_keyboard

        logger.info("Keyboard selected lost.")

        context.reader.remove_device(
            previous_keyboard.device_id,
        )

        state.selected_keyboard = None

        context.server.send_event(
            {
                "type": EVENT_KEYBOARD_SELECTED_LOST,
            }
        )

        if state.input_monitoring_active:
            logger.info("Starting keyboard discovery.")

            context.keyboard_selector.start(
                get_keyboard_devices(state.current_devices),
            )

    elif state.selected_keyboard is None:
        context.keyboard_selector.start(
            get_keyboard_devices(state.current_devices),
        )

    selected_mouse_removed = state.selected_mouse is not None and any(
        device.device_id == state.selected_mouse.device_id for device in removed_devices
    )

    if selected_mouse_removed:
        previous_mouse = state.selected_mouse

        logger.info("Selected mouse removed.")

        stop_mouse_interception(
            context.server,
            state.selected_mouse,
            state.mouse_interceptor,
        )

        if state.mouse_grabber is not None:
            state.mouse_grabber.stop()
            state.mouse_grabber = None

        context.server.send_event(
            {
                "type": EVENT_MOUSE_SELECTED_LOST,
            }
        )

        state.mouse_interceptor = None
        state.selected_mouse = None
        context.mouse_selector.stop()

        state.next_mouse_discovery = time.monotonic()

        if previous_mouse is not None:
            context.reader.remove_device(
                previous_mouse.device_id,
            )

    elif state.selected_mouse is None:
        context.mouse_selector.stop()
        context.mouse_selector.start(
            get_mouse_devices(state.current_devices),
        )
