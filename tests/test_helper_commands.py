from unittest.mock import MagicMock

import evdev

from helper.commands import (
    HelperContext,
    build_input_policy,
    handle_command,
    reset_client_state,
)
from helper.policy import ShortcutAction
from helper.protocol import (
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
    ERROR_MOUSE_INTERCEPTION_FAILED,
    EVENT_ERROR,
    EVENT_MOUSE_INTERCEPTION_STARTED,
    EVENT_MOUSE_INTERCEPTION_STOPPED,
)
from helper.state import HelperState
from input.classifier import DeviceClass


def build_command_context():
    server = MagicMock()
    registry = MagicMock()
    reader = MagicMock()
    keyboard_selector = MagicMock()
    mouse_selector = MagicMock()
    keyboard_state = MagicMock()
    xkb = MagicMock()

    context = HelperContext(
        server=server,
        registry=registry,
        reader=reader,
        keyboard_selector=keyboard_selector,
        mouse_selector=mouse_selector,
        keyboard_state=keyboard_state,
        xkb=xkb,
    )

    state = HelperState()

    return context, state


def build_selected_mouse():
    mouse = MagicMock()
    mouse.device_class = DeviceClass.MOUSE
    mouse.device_id = "mouse-1"
    mouse.info = MagicMock()
    return mouse


def test_start_command_starts_input_monitoring_and_discovers_devices(
    monkeypatch,
):
    context, state = build_command_context()

    keyboard = MagicMock()
    keyboard.device_class = DeviceClass.KEYBOARD

    mouse = build_selected_mouse()

    current_devices = [keyboard, mouse]

    context.registry.reconcile.return_value = (
        [keyboard, mouse],
        [],
        current_devices,
    )

    monkeypatch.setattr(
        "helper.commands.discover_devices",
        MagicMock(return_value=current_devices),
    )

    context.mouse_selector.is_active.return_value = True

    handled = handle_command(
        {"type": COMMAND_START},
        context,
        state,
    )

    assert handled is True
    assert state.input_monitoring_active is True
    assert state.current_devices == current_devices

    context.registry.reconcile.assert_called_once_with(
        current_devices,
    )

    context.reader.start_device_monitor.assert_called_once_with()

    context.keyboard_selector.start.assert_called_once_with(
        [keyboard],
    )

    context.mouse_selector.start.assert_called_once_with(
        [mouse],
    )


def test_start_command_ignores_duplicate_start():
    context, state = build_command_context()

    state.input_monitoring_active = True

    handled = handle_command(
        {"type": COMMAND_START},
        context,
        state,
    )

    assert handled is True
    context.registry.reconcile.assert_not_called()
    context.reader.start_device_monitor.assert_not_called()
    context.keyboard_selector.start.assert_not_called()
    context.mouse_selector.start.assert_not_called()


def test_grab_selected_mouse_command_starts_grabber(monkeypatch):
    context, state = build_command_context()

    mouse = build_selected_mouse()
    state.selected_mouse = mouse

    grabber = MagicMock()
    grabber.is_started.return_value = True

    monkeypatch.setattr(
        "helper.commands.MouseGrabber",
        MagicMock(return_value=grabber),
    )

    handled = handle_command(
        {"type": COMMAND_GRAB_SELECTED_MOUSE},
        context,
        state,
    )

    assert handled is True
    assert state.mouse_grabber is grabber
    grabber.start.assert_called_once_with()


def test_start_mouse_interception_removes_selected_mouse_from_reader(
    monkeypatch,
):
    context, state = build_command_context()

    mouse = build_selected_mouse()
    state.selected_mouse = mouse

    grabber = MagicMock()
    grabber.is_started.return_value = True
    state.mouse_grabber = grabber

    interceptor = MagicMock()
    interceptor.is_started.return_value = True

    start_interceptor = MagicMock(
        return_value=interceptor,
    )

    monkeypatch.setattr(
        "helper.commands.start_mouse_interceptor",
        start_interceptor,
    )

    handled = handle_command(
        {
            "type": COMMAND_SET_MOUSE_INTERCEPTION,
            "enabled": True,
        },
        context,
        state,
    )

    assert handled is True

    context.reader.remove_device.assert_called_once_with(
        mouse.device_id,
    )

    start_interceptor.assert_called_once_with(
        grabber,
        set(),
    )

    assert state.mouse_interceptor is interceptor

    context.server.send_event.assert_called_once_with(
        {
            "type": EVENT_MOUSE_INTERCEPTION_STARTED,
            "device_id": mouse.device_id,
        }
    )


def test_start_mouse_interception_reports_failure_without_restoring_reader(
    monkeypatch,
):
    context, state = build_command_context()

    mouse = build_selected_mouse()
    state.selected_mouse = mouse

    grabber = MagicMock()
    grabber.is_started.return_value = True
    state.mouse_grabber = grabber

    monkeypatch.setattr(
        "helper.commands.start_mouse_interceptor",
        MagicMock(return_value=None),
    )

    handled = handle_command(
        {
            "type": COMMAND_SET_MOUSE_INTERCEPTION,
            "enabled": True,
        },
        context,
        state,
    )

    assert handled is True
    assert state.mouse_interceptor is None

    context.reader.remove_device.assert_called_once_with(
        mouse.device_id,
    )
    context.reader.add_device.assert_not_called()

    context.server.send_event.assert_called_once_with(
        {
            "type": EVENT_ERROR,
            "code": ERROR_MOUSE_INTERCEPTION_FAILED,
            "message": "The selected mouse is already in use.",
            "command": COMMAND_SET_MOUSE_INTERCEPTION,
        }
    )


def test_stop_mouse_interception_does_not_restore_reader_when_capture_is_inactive():
    context, state = build_command_context()

    mouse = build_selected_mouse()
    state.selected_mouse = mouse

    interceptor = MagicMock()
    interceptor.is_started.return_value = True
    state.mouse_interceptor = interceptor

    handled = handle_command(
        {
            "type": COMMAND_SET_MOUSE_INTERCEPTION,
            "enabled": False,
        },
        context,
        state,
    )

    assert handled is True
    assert state.mouse_interceptor is None

    interceptor.stop.assert_called_once_with()
    context.reader.add_device.assert_not_called()

    context.server.send_event.assert_called_once_with(
        {
            "type": EVENT_MOUSE_INTERCEPTION_STOPPED,
            "device_id": mouse.device_id,
        }
    )


def test_set_intercepted_mouse_buttons_updates_interceptor():
    context, state = build_command_context()

    interceptor = MagicMock()
    interceptor.is_started.return_value = True
    state.mouse_interceptor = interceptor

    buttons = [
        evdev.ecodes.BTN_SIDE,
        evdev.ecodes.BTN_EXTRA,
    ]

    handled = handle_command(
        {
            "type": COMMAND_SET_INTERCEPTED_MOUSE_BUTTONS,
            "buttons": buttons,
        },
        context,
        state,
    )

    assert handled is True
    assert state.intercepted_mouse_buttons == set()

    interceptor.update_intercepted_buttons.assert_called_once_with(
        set(),
    )


def test_set_intercepted_mouse_buttons_uses_configured_mouse_buttons():
    context, state = build_command_context()

    state.input_policy = build_input_policy(
        {
            "calibration": {
                "primary": {
                    "trigger": "F1",
                    "modifiers": ["CTRL"],
                },
                "alternate": None,
            },
            "next": {
                "primary": {
                    "trigger": "N",
                    "modifiers": ["META"],
                },
                "alternate": {
                    "trigger": "BTN_SIDE",
                    "modifiers": [],
                },
            },
            "previous": {
                "primary": {
                    "trigger": "P",
                    "modifiers": ["ALT", "SHIFT"],
                },
                "alternate": None,
            },
        }
    )

    buttons = [
        evdev.ecodes.BTN_SIDE,
        evdev.ecodes.BTN_EXTRA,
    ]

    handled = handle_command(
        {
            "type": COMMAND_SET_INTERCEPTED_MOUSE_BUTTONS,
            "buttons": buttons,
        },
        context,
        state,
    )

    assert handled is True
    assert state.intercepted_mouse_buttons == {
        evdev.ecodes.BTN_SIDE,
    }


def test_stop_command_stops_and_restarts_input_monitoring(monkeypatch):
    context, state = build_command_context()

    monkeypatch.setattr(
        "helper.commands.discover_devices",
        MagicMock(return_value=[]),
    )

    context.registry.reconcile.return_value = (
        [],
        [],
        [],
    )

    context.mouse_selector.is_active.return_value = False

    assert handle_command(
        {"type": COMMAND_START},
        context,
        state,
    ) is True

    assert handle_command(
        {"type": COMMAND_STOP},
        context,
        state,
    ) is True

    assert state.input_monitoring_active is False
    assert state.selected_keyboard is None
    assert state.selected_mouse is None
    assert state.mouse_interceptor is None
    assert state.mouse_grabber is None
    assert state.capture_active is False

    assert handle_command(
        {"type": COMMAND_START},
        context,
        state,
    ) is True

    assert context.reader.start_device_monitor.call_count == 2
    context.reader.close.assert_called_once_with()


def test_start_capture_adds_selected_mouse_to_reader():
    context, state = build_command_context()

    state.input_monitoring_active = True
    state.selected_mouse = build_selected_mouse()

    handled = handle_command(
        {"type": COMMAND_START_CAPTURE},
        context,
        state,
    )

    assert handled is True
    assert state.capture_active is True

    context.reader.add_device.assert_called_once_with(
        state.selected_mouse,
    )


def test_stop_capture_removes_selected_mouse_from_reader():
    context, state = build_command_context()

    mouse = build_selected_mouse()

    state.input_monitoring_active = True
    state.selected_mouse = mouse
    state.capture_active = True

    handled = handle_command(
        {"type": COMMAND_STOP_CAPTURE},
        context,
        state,
    )

    assert handled is True
    assert state.capture_active is False

    context.reader.remove_device.assert_called_once_with(
        mouse.device_id,
    )


def test_start_capture_rejects_command_before_input_monitoring():
    context, state = build_command_context()

    handled = handle_command(
        {"type": COMMAND_START_CAPTURE},
        context,
        state,
    )

    assert handled is True
    assert state.capture_active is False

    context.server.send_event.assert_called_once_with(
        {
            "type": EVENT_ERROR,
            "code": ERROR_HELPER_NOT_READY,
            "message": "Input monitoring is not active.",
            "command": COMMAND_START_CAPTURE,
        }
    )


def test_start_capture_ignores_duplicate_command():
    context, state = build_command_context()

    state.input_monitoring_active = True
    state.capture_active = True

    handled = handle_command(
        {"type": COMMAND_START_CAPTURE},
        context,
        state,
    )

    assert handled is True
    context.reader.add_device.assert_not_called()


def test_stop_capture_ignores_inactive_command():
    context, state = build_command_context()

    state.input_monitoring_active = True

    handled = handle_command(
        {"type": COMMAND_STOP_CAPTURE},
        context,
        state,
    )

    assert handled is True
    context.reader.remove_device.assert_not_called()
    context.reader.close.assert_not_called()
    context.keyboard_selector.stop.assert_not_called()
    context.mouse_selector.stop.assert_not_called()


def test_start_capture_stops_active_mouse_interception():
    context, state = build_command_context()

    mouse = build_selected_mouse()

    state.input_monitoring_active = True
    state.selected_mouse = mouse

    grabber = MagicMock()
    grabber.is_started.return_value = True
    state.mouse_grabber = grabber

    interceptor = MagicMock()
    interceptor.is_started.return_value = True
    state.mouse_interceptor = interceptor

    assert handle_command(
        {"type": COMMAND_START_CAPTURE},
        context,
        state,
    ) is True

    interceptor.stop.assert_called_once_with()
    assert state.mouse_interceptor is None
    context.reader.add_device.assert_not_called()
    assert state.capture_active is True


def test_stop_capture_keeps_input_monitoring_active():
    context, state = build_command_context()

    state.input_monitoring_active = True
    state.capture_active = True

    assert handle_command(
        {"type": COMMAND_STOP_CAPTURE},
        context,
        state,
    ) is True

    assert state.input_monitoring_active is True
    assert state.capture_active is False

    context.reader.close.assert_not_called()
    context.keyboard_selector.stop.assert_not_called()
    context.mouse_selector.stop.assert_not_called()


def test_set_shortcut_configuration_rejects_invalid_configuration():
    context, state = build_command_context()

    invalid_configuration = {
        "calibration": {
            "primary": {
                "trigger": "F1",
                "modifiers": [],
            },
            "alternate": None,
        },
        "next": {
            "primary": None,
            "alternate": None,
        },
        "previous": {
            "primary": None,
            "alternate": None,
        },
    }

    handled = handle_command(
        {
            "type": COMMAND_SET_SHORTCUT_CONFIGURATION,
            "configuration": invalid_configuration,
        },
        context,
        state,
    )

    assert handled is True

    context.server.send_event.assert_called_once_with(
        {
            "type": EVENT_ERROR,
            "code": "invalid_argument",
            "message": "Keyboard shortcuts require at least one modifier.",
            "command": COMMAND_SET_SHORTCUT_CONFIGURATION,
        }
    )


def test_build_input_policy_builds_policy_from_configuration():
    configuration = {
        "calibration": {
            "primary": {
                "trigger": "F1",
                "modifiers": ["CTRL"],
            },
            "alternate": None,
        },
        "next": {
            "primary": {
                "trigger": "N",
                "modifiers": ["META"],
            },
            "alternate": {
                "trigger": "BTN_SIDE",
                "modifiers": [],
            },
        },
        "previous": {
            "primary": {
                "trigger": "P",
                "modifiers": ["ALT", "SHIFT"],
            },
            "alternate": None,
        },
    }

    policy = build_input_policy(configuration)

    assert (
        policy.get_keyboard_action(
            "F1",
            frozenset({"CTRL"}),
        )
        == ShortcutAction.CALIBRATION
    )

    assert (
        policy.get_keyboard_action(
            "N",
            frozenset({"META"}),
        )
        == ShortcutAction.NEXT
    )

    assert (
        policy.get_keyboard_action(
            "P",
            frozenset({"ALT", "SHIFT"}),
        )
        == ShortcutAction.PREVIOUS
    )


def test_release_selected_mouse_command_releases_grabber():
    context, state = build_command_context()

    grabber = MagicMock()
    state.mouse_grabber = grabber

    assert handle_command(
        {"type": COMMAND_RELEASE_SELECTED_MOUSE},
        context,
        state,
    ) is True

    grabber.stop.assert_called_once_with()
    assert state.mouse_grabber is None


def test_grab_selected_mouse_command_handles_missing_or_failed_grab(
    monkeypatch,
):
    context, state = build_command_context()

    assert handle_command(
        {"type": COMMAND_GRAB_SELECTED_MOUSE},
        context,
        state,
    ) is True

    context.server.send_event.assert_called_once_with(
        {
            "type": EVENT_ERROR,
            "code": ERROR_HELPER_NOT_READY,
            "message": "No mouse has been selected.",
            "command": COMMAND_GRAB_SELECTED_MOUSE,
        }
    )

    context.server.send_event.reset_mock()

    mouse = build_selected_mouse()
    state.selected_mouse = mouse

    grabber = MagicMock()
    grabber.start.side_effect = OSError("grab failed")

    monkeypatch.setattr(
        "helper.commands.MouseGrabber",
        MagicMock(return_value=grabber),
    )

    assert handle_command(
        {"type": COMMAND_GRAB_SELECTED_MOUSE},
        context,
        state,
    ) is True

    grabber.start.assert_called_once_with()
    assert state.mouse_grabber is None

    context.server.send_event.assert_called_once_with(
        {
            "type": EVENT_ERROR,
            "code": ERROR_DEVICE_ERROR,
            "message": "Failed to grab the selected mouse.",
            "command": COMMAND_GRAB_SELECTED_MOUSE,
        }
    )


def test_grab_selected_mouse_command_handles_mouse_already_in_use(
    monkeypatch,
):
    context, state = build_command_context()

    state.selected_mouse = build_selected_mouse()

    grabber = MagicMock()
    grabber.start.return_value = False

    monkeypatch.setattr(
        "helper.commands.MouseGrabber",
        MagicMock(return_value=grabber),
    )

    assert handle_command(
        {"type": COMMAND_GRAB_SELECTED_MOUSE},
        context,
        state,
    ) is True

    grabber.start.assert_called_once_with()
    assert state.mouse_grabber is None

    context.server.send_event.assert_called_once_with(
        {
            "type": EVENT_ERROR,
            "code": ERROR_DEVICE_ERROR,
            "message": "The selected mouse is already in use.",
            "command": COMMAND_GRAB_SELECTED_MOUSE,
        }
    )


def test_handle_command_returns_false_for_unknown_command():
    context, state = build_command_context()

    assert handle_command(
        {"type": "unknown_command"},
        context,
        state,
    ) is False


def test_reset_client_state_clears_intercepted_mouse_buttons():
    context, state = build_command_context()
    state.intercepted_mouse_buttons = {
        evdev.ecodes.BTN_SIDE,
        evdev.ecodes.BTN_EXTRA,
    }

    reset_client_state(context, state)

    assert state.intercepted_mouse_buttons == set()
