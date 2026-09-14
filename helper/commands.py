import logging
import time
from dataclasses import dataclass

from input.classifier import DeviceClass
from shortcuts.model import Shortcut
from shortcuts.storage import ShortcutConfiguration

from .devices import (
    DeviceRegistry,
    HelperDevice,
    discover_devices,
)
from .events import InputEventReader
from .keyboard import (
    KeyboardSelector,
    KeyboardState,
)
from .mouse import (
    MouseGrabber,
    MouseInterceptor,
    MouseSelector,
)
from .policy import InputPolicy
from .protocol import (
    COMMAND_GRAB_SELECTED_MOUSE,
    COMMAND_RELEASE_SELECTED_MOUSE,
    COMMAND_SET_INTERCEPTED_MOUSE_BUTTONS,
    COMMAND_SET_MOUSE_INTERCEPTION,
    COMMAND_SET_SHORTCUT_CONFIGURATION,
    COMMAND_START,
    COMMAND_START_CAPTURE,
    COMMAND_STOP,
    COMMAND_STOP_CAPTURE,
    ERROR_DEVICE_ERROR,
    ERROR_HELPER_NOT_READY,
    ERROR_INVALID_ARGUMENT,
    ERROR_MOUSE_INTERCEPTION_FAILED,
    EVENT_ERROR,
    EVENT_MOUSE_INTERCEPTION_STARTED,
    EVENT_MOUSE_INTERCEPTION_STOPPED,
)
from .server import HelperServer
from .state import HelperState
from .xkb import Xkb

logger = logging.getLogger(__name__)

MOUSE_DISCOVERY_RETRY_DELAY = 1.0


@dataclass
class HelperContext:
    """Provide access to the helper components used by command handlers."""

    server: HelperServer
    registry: DeviceRegistry
    reader: InputEventReader
    keyboard_selector: KeyboardSelector
    mouse_selector: MouseSelector
    keyboard_state: KeyboardState
    xkb: Xkb


def send_error(
    server: HelperServer,
    code: str,
    message: str,
    command: str | None = None,
) -> None:
    """Send a structured protocol error to the tray."""
    payload = {
        "type": EVENT_ERROR,
        "code": code,
        "message": message,
    }

    if command is not None:
        payload["command"] = command

    server.send_event(payload)


def stop_input_monitoring(
    reader: InputEventReader,
    keyboard_selector: KeyboardSelector,
    mouse_selector: MouseSelector,
    mouse_interceptor: MouseInterceptor | None,
) -> None:
    """Stop input monitoring and release all input resources."""
    keyboard_selector.stop()
    mouse_selector.stop()

    if mouse_interceptor is not None:
        mouse_interceptor.stop()

    reader.close()


def get_mouse_devices(
    devices: list[HelperDevice],
) -> list[HelperDevice]:
    """Return currently discovered mouse devices."""
    return [
        device
        for device in devices
        if device.device_class == DeviceClass.MOUSE
    ]


def get_keyboard_devices(
    devices: list[HelperDevice],
) -> list[HelperDevice]:
    """Return currently discovered keyboard devices."""
    return [
        device
        for device in devices
        if device.device_class == DeviceClass.KEYBOARD
    ]


def start_mouse_interceptor(
    mouse_grabber: MouseGrabber,
    intercepted_buttons: set[int],
) -> MouseInterceptor | None:
    """Create and start an interceptor for the grabbed mouse."""
    interceptor = MouseInterceptor(
        mouse_grabber,
        intercepted_buttons,
    )

    try:
        started = interceptor.start()
    except OSError:
        interceptor.stop()
        raise

    if not started:
        interceptor.stop()
        return None

    return interceptor


def stop_mouse_interception(
    server: HelperServer,
    selected_mouse: HelperDevice | None,
    mouse_interceptor: MouseInterceptor | None,
) -> None:
    """Stop mouse interception and notify the tray when it was active."""
    if mouse_interceptor is None:
        return

    mouse_interceptor.stop()

    if selected_mouse is not None:
        server.send_event(
            {
                "type": EVENT_MOUSE_INTERCEPTION_STOPPED,
                "device_id": selected_mouse.device_id,
            }
        )


def build_input_policy(
    configuration: dict,
) -> InputPolicy:
    """Build a policy from a protocol shortcut configuration."""
    shortcut_configuration = {}

    for action, action_configuration in configuration.items():
        shortcut_configuration[action] = ShortcutConfiguration(
            primary=_build_shortcut(
                action_configuration["primary"],
            ),
            alternate=_build_shortcut(
                action_configuration["alternate"],
            ),
        )

    return InputPolicy.from_configuration(
        shortcut_configuration,
    )


def _build_shortcut(
    shortcut: dict | None,
) -> Shortcut | None:
    """Build a Shortcut from its protocol representation."""
    if shortcut is None:
        return None

    return Shortcut(
        trigger=shortcut["trigger"],
        modifiers=frozenset(shortcut["modifiers"]),
    )


def reset_client_state(
    context: HelperContext,
    state: HelperState,
) -> None:
    """Reset all client-dependent state and release input resources."""
    stop_input_monitoring(
        context.reader,
        context.keyboard_selector,
        context.mouse_selector,
        state.mouse_interceptor,
    )

    if state.mouse_grabber is not None:
        state.mouse_grabber.stop()
        state.mouse_grabber = None

    state.handshake_completed = False
    state.input_monitoring_active = False
    state.selected_keyboard = None
    state.selected_mouse = None
    state.mouse_interceptor = None
    state.next_mouse_discovery = None
    state.capture_active = False
    state.input_policy = InputPolicy()
    context.keyboard_state.reset()
    context.xkb.reset()


def handle_command(
    command: dict,
    context: HelperContext,
    state: HelperState,
) -> bool:
    """Handle a post-handshake command.

    Return True when the command corresponds to one of the command
    handlers below, so the caller can reproduce the original loop's
    ``continue`` behavior. Return False for commands that were not
    handled here.
    """
    command_type = command["type"]

    if command_type == COMMAND_START:
        _handle_start(context, state)
        return True

    if command_type == COMMAND_START_CAPTURE:
        _handle_start_capture(context, state)
        return True

    if command_type == COMMAND_STOP_CAPTURE:
        _handle_stop_capture(context, state)
        return True

    if command_type == COMMAND_STOP:
        _handle_stop(context, state)
        return True

    if command_type == COMMAND_GRAB_SELECTED_MOUSE:
        _handle_grab_selected_mouse(context, state)
        return True

    if command_type == COMMAND_RELEASE_SELECTED_MOUSE:
        _handle_release_selected_mouse(context, state)
        return True

    if command_type == COMMAND_SET_MOUSE_INTERCEPTION:
        _handle_mouse_interception(command, context, state)
        return True

    if command_type == COMMAND_SET_INTERCEPTED_MOUSE_BUTTONS:
        _handle_intercepted_mouse_buttons(command, state)
        return True

    if command_type == COMMAND_SET_SHORTCUT_CONFIGURATION:
        _handle_shortcut_configuration(command, context, state)
        return True

    return False


def _handle_start(
    context: HelperContext,
    state: HelperState,
) -> None:
    """Handle the START command."""
    if state.input_monitoring_active:
        return

    discovered_devices = discover_devices()

    _, _, state.current_devices = context.registry.reconcile(
        discovered_devices,
    )

    context.reader.start_device_monitor()

    state.selected_keyboard = None

    logger.info("Starting keyboard discovery.")

    context.keyboard_selector.start(
        get_keyboard_devices(state.current_devices),
    )

    state.selected_mouse = None
    state.mouse_interceptor = None

    context.mouse_selector.start(
        get_mouse_devices(state.current_devices),
    )

    if not context.mouse_selector.is_active():
        state.next_mouse_discovery = (
            time.monotonic()
            + MOUSE_DISCOVERY_RETRY_DELAY
        )
    else:
        state.next_mouse_discovery = None

    state.input_monitoring_active = True
    logger.info("Input monitoring started.")


def _handle_start_capture(
    context: HelperContext,
    state: HelperState,
) -> None:
    """Handle the START_CAPTURE command."""
    if not state.input_monitoring_active:
        send_error(
            context.server,
            ERROR_HELPER_NOT_READY,
            "Input monitoring is not active.",
            COMMAND_START_CAPTURE,
        )
        return

    if state.capture_active:
        return

    if state.mouse_interceptor is not None:
        state.mouse_interceptor.stop()
        state.mouse_interceptor = None

    if state.selected_mouse is not None and (
        state.mouse_grabber is None
        or not state.mouse_grabber.is_started()
    ):
        context.reader.add_device(state.selected_mouse)

    state.capture_active = True
    logger.info("Shortcut capture started.")


def _handle_stop_capture(
    context: HelperContext,
    state: HelperState,
) -> None:
    """Handle the STOP_CAPTURE command."""
    if not state.capture_active:
        return

    if state.selected_mouse is not None:
        context.reader.remove_device(
            state.selected_mouse.device_id,
        )

    state.capture_active = False
    logger.info("Shortcut capture stopped.")


def _handle_stop(
    context: HelperContext,
    state: HelperState,
) -> None:
    """Handle the STOP command."""
    stop_input_monitoring(
        context.reader,
        context.keyboard_selector,
        context.mouse_selector,
        state.mouse_interceptor,
    )

    if state.mouse_grabber is not None:
        state.mouse_grabber.stop()
        state.mouse_grabber = None

    state.input_monitoring_active = False
    state.selected_keyboard = None
    state.selected_mouse = None
    state.mouse_interceptor = None
    state.intercepted_mouse_buttons = set()
    state.next_mouse_discovery = None
    state.capture_active = False
    state.input_policy = InputPolicy()
    context.keyboard_state.reset()
    context.xkb.reset()


def _handle_grab_selected_mouse(
    context: HelperContext,
    state: HelperState,
) -> None:
    """Handle the GRAB_SELECTED_MOUSE command."""
    if state.selected_mouse is None:
        send_error(
            context.server,
            ERROR_HELPER_NOT_READY,
            "No mouse has been selected.",
            COMMAND_GRAB_SELECTED_MOUSE,
        )
        return

    if (
        state.mouse_grabber is not None
        and state.mouse_grabber.is_started()
    ):
        return

    state.mouse_grabber = MouseGrabber(
        state.selected_mouse.info,
    )

    try:
        started = state.mouse_grabber.start()
    except OSError as error:
        logger.error(
            "Failed to grab selected mouse: %s",
            error,
        )
        state.mouse_grabber = None

        send_error(
            context.server,
            ERROR_DEVICE_ERROR,
            "Failed to grab the selected mouse.",
            COMMAND_GRAB_SELECTED_MOUSE,
        )
        return

    if not started:
        state.mouse_grabber = None

        send_error(
            context.server,
            ERROR_DEVICE_ERROR,
            "The selected mouse is already in use.",
            COMMAND_GRAB_SELECTED_MOUSE,
        )
        return


def _handle_release_selected_mouse(
    context: HelperContext,
    state: HelperState,
) -> None:
    """Handle the RELEASE_SELECTED_MOUSE command."""
    if state.mouse_grabber is None:
        return

    state.mouse_grabber.stop()
    state.mouse_grabber = None


def _handle_mouse_interception(
    command: dict,
    context: HelperContext,
    state: HelperState,
) -> None:
    """Handle the SET_MOUSE_INTERCEPTION command."""
    enabled = command["enabled"]

    if enabled:
        _enable_mouse_interception(
            context,
            state,
        )
        return

    _disable_mouse_interception(
        context,
        state,
    )


def _enable_mouse_interception(
    context: HelperContext,
    state: HelperState,
) -> None:
    """Enable interception for the selected mouse."""
    if state.capture_active:
        return

    if state.selected_mouse is None:
        send_error(
            context.server,
            ERROR_HELPER_NOT_READY,
            "No mouse has been selected.",
            COMMAND_SET_MOUSE_INTERCEPTION,
        )
        return

    if (
        state.mouse_grabber is None
        or not state.mouse_grabber.is_started()
    ):
        send_error(
            context.server,
            ERROR_HELPER_NOT_READY,
            "Mouse must be grabbed before interception.",
            COMMAND_SET_MOUSE_INTERCEPTION,
        )
        return

    if (
        state.mouse_interceptor is not None
        and state.mouse_interceptor.is_started()
    ):
        return

    context.reader.remove_device(
        state.selected_mouse.device_id,
    )

    try:
        state.mouse_interceptor = start_mouse_interceptor(
            state.mouse_grabber,
            state.intercepted_mouse_buttons,
        )
    except OSError as error:
        logger.error(
            "Failed to start mouse interception: %s",
            error,
        )

        state.mouse_interceptor = None

        send_error(
            context.server,
            ERROR_MOUSE_INTERCEPTION_FAILED,
            "Failed to start mouse interception.",
            COMMAND_SET_MOUSE_INTERCEPTION,
        )
        return

    if state.mouse_interceptor is None:
        send_error(
            context.server,
            ERROR_MOUSE_INTERCEPTION_FAILED,
            "The selected mouse is already in use.",
            COMMAND_SET_MOUSE_INTERCEPTION,
        )
        return

    context.server.send_event(
        {
            "type": EVENT_MOUSE_INTERCEPTION_STARTED,
            "device_id": state.selected_mouse.device_id,
        }
    )


def _disable_mouse_interception(
    context: HelperContext,
    state: HelperState,
) -> None:
    """Disable interception for the selected mouse."""
    if state.mouse_interceptor is not None:
        selected_device = state.selected_mouse

        stop_mouse_interception(
            context.server,
            selected_device,
            state.mouse_interceptor,
        )

        state.mouse_interceptor = None

        if selected_device is not None and state.capture_active:
            context.reader.add_device(selected_device)


def _handle_intercepted_mouse_buttons(
    command: dict,
    state: HelperState,
) -> None:
    """Handle the SET_INTERCEPTED_MOUSE_BUTTONS command."""
    configured_mouse_buttons = {
        rule.button
        for rule in state.input_policy.mouse_rules
    }

    state.intercepted_mouse_buttons = (
        set(command["buttons"]) & configured_mouse_buttons
    )

    if (
        state.mouse_interceptor is not None
        and state.mouse_interceptor.is_started()
    ):
        state.mouse_interceptor.update_intercepted_buttons(
            state.intercepted_mouse_buttons,
        )


def _handle_shortcut_configuration(
    command: dict,
    context: HelperContext,
    state: HelperState,
) -> None:
    """Handle the SET_SHORTCUT_CONFIGURATION command."""
    try:
        new_input_policy = build_input_policy(
            command["configuration"],
        )
    except (TypeError, ValueError) as error:
        logger.warning(
            "Rejected shortcut configuration: %s",
            error,
        )

        send_error(
            context.server,
            ERROR_INVALID_ARGUMENT,
            str(error),
            COMMAND_SET_SHORTCUT_CONFIGURATION,
        )
        return

    if new_input_policy == state.input_policy:
        return

    state.input_policy = new_input_policy

    logger.info("Shortcut configuration updated.")
