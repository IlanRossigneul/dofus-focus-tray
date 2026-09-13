from unittest.mock import MagicMock

import evdev

from helper.commands import HelperContext
from helper.input_processing import process_input
from helper.policy import ShortcutAction
from helper.protocol import (
    ERROR_DEVICE_ERROR,
    EVENT_ERROR,
    EVENT_KEYBOARD_EVENT,
    EVENT_MOUSE_BUTTON_EVENT,
    EVENT_SHORTCUT,
)
from helper.state import HelperState
from input.classifier import DeviceClass


def build_input_processing_context():
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


def build_keyboard():
    keyboard = MagicMock()
    keyboard.device_id = "keyboard-1"
    keyboard.device_class = DeviceClass.KEYBOARD
    return keyboard


def build_mouse():
    mouse = MagicMock()
    mouse.device_id = "mouse-1"
    mouse.device_class = DeviceClass.MOUSE
    return mouse


def build_input_event(
    event_type,
    code,
    value,
    timestamp=123.456,
):
    event = MagicMock()
    event.type = event_type
    event.code = code
    event.value = value
    event.timestamp.return_value = timestamp
    return event


def test_process_input_sends_keyboard_events():
    context, state = build_input_processing_context()

    keyboard = build_keyboard()
    event = build_input_event(
        evdev.ecodes.EV_KEY,
        evdev.ecodes.KEY_A,
        1,
    )

    state.capture_active = True
    context.keyboard_state.get_modifiers.return_value = frozenset(
        {"CTRL"},
    )

    context.reader.get_watched_fds.return_value = [42]
    context.reader.read_ready.return_value = [
        (keyboard, event),
    ]

    should_continue = process_input(
        context,
        state,
        [42],
        set(),
        [],
    )

    assert should_continue is False

    context.reader.read_ready.assert_called_once_with([42])

    context.server.send_event.assert_called_once_with(
        {
            "type": EVENT_KEYBOARD_EVENT,
            "device_id": "keyboard-1",
            "code": evdev.ecodes.KEY_A,
            "value": 1,
            "timestamp": 123.456,
            "modifiers": ["CTRL"],
        }
    )


def test_process_input_does_not_send_keyboard_event_without_modifier():
    context, state = build_input_processing_context()

    keyboard = build_keyboard()
    event = build_input_event(
        evdev.ecodes.EV_KEY,
        evdev.ecodes.KEY_A,
        1,
    )

    state.capture_active = True
    context.keyboard_state.get_modifiers.return_value = frozenset()

    context.reader.get_watched_fds.return_value = [42]
    context.reader.read_ready.return_value = [
        (keyboard, event),
    ]

    should_continue = process_input(
        context,
        state,
        [42],
        set(),
        [],
    )

    assert should_continue is False

    context.reader.read_ready.assert_called_once_with([42])
    context.server.send_event.assert_not_called()


def test_process_input_ignores_mouse_motion_events():
    context, state = build_input_processing_context()

    mouse = build_mouse()
    event = build_input_event(
        evdev.ecodes.EV_REL,
        evdev.ecodes.REL_X,
        17,
    )

    state.capture_active = True

    context.reader.get_watched_fds.return_value = [42]
    context.reader.read_ready.return_value = [
        (mouse, event),
    ]

    should_continue = process_input(
        context,
        state,
        [42],
        set(),
        [],
    )

    assert should_continue is False
    context.server.send_event.assert_not_called()


def test_process_input_sends_mouse_button_events():
    context, state = build_input_processing_context()

    mouse = build_mouse()
    event = build_input_event(
        evdev.ecodes.EV_KEY,
        evdev.ecodes.BTN_SIDE,
        1,
    )

    state.capture_active = True

    context.reader.get_watched_fds.return_value = [42]
    context.reader.read_ready.return_value = [
        (mouse, event),
    ]

    should_continue = process_input(
        context,
        state,
        [42],
        set(),
        [],
    )

    assert should_continue is False

    context.server.send_event.assert_called_once_with(
        {
            "type": EVENT_MOUSE_BUTTON_EVENT,
            "device_id": "mouse-1",
            "code": evdev.ecodes.BTN_SIDE,
            "value": 1,
            "timestamp": 123.456,
        }
    )


def test_process_input_does_not_forward_intercepted_mouse_button():
    context, state = build_input_processing_context()

    mouse = build_mouse()
    state.selected_mouse = mouse

    interceptor = MagicMock()
    interceptor.is_started.return_value = True
    interceptor.fileno.return_value = 99
    interceptor.should_intercept.return_value = True

    event = build_input_event(
        evdev.ecodes.EV_KEY,
        evdev.ecodes.BTN_SIDE,
        1,
    )

    interceptor.read.return_value = [event]
    state.mouse_interceptor = interceptor

    should_continue = process_input(
        context,
        state,
        [99],
        set(),
        [],
    )

    assert should_continue is False

    interceptor.should_intercept.assert_called_once_with(event)
    interceptor.forward_event.assert_not_called()
    context.server.send_event.assert_not_called()


def test_process_input_forwards_non_intercepted_mouse_event():
    context, state = build_input_processing_context()

    mouse = build_mouse()
    state.selected_mouse = mouse

    interceptor = MagicMock()
    interceptor.is_started.return_value = True
    interceptor.fileno.return_value = 99
    interceptor.should_intercept.return_value = False

    event = build_input_event(
        evdev.ecodes.EV_REL,
        evdev.ecodes.REL_X,
        17,
    )

    interceptor.read.return_value = [event]
    state.mouse_interceptor = interceptor

    should_continue = process_input(
        context,
        state,
        [99],
        set(),
        [],
    )

    assert should_continue is False

    interceptor.should_intercept.assert_called_once_with(event)
    interceptor.forward_event.assert_called_once_with(event)
    context.server.send_event.assert_not_called()


def test_process_input_triggers_keyboard_shortcut():
    context, state = build_input_processing_context()

    state.input_policy = MagicMock()

    keyboard = build_keyboard()
    event = build_input_event(
        evdev.ecodes.EV_KEY,
        evdev.ecodes.KEY_A,
        1,
    )

    action = ShortcutAction.NEXT
    state.input_policy.get_keyboard_action.return_value = action
    context.xkb.keycode_to_key.return_value = "a"
    context.keyboard_state.get_modifiers.return_value = frozenset()

    context.reader.get_watched_fds.return_value = [42]
    context.reader.read_ready.return_value = [
        (keyboard, event),
    ]

    should_continue = process_input(
        context,
        state,
        [42],
        set(),
        [],
    )

    assert should_continue is False

    context.keyboard_state.update.assert_called_once_with(event)
    context.xkb.update_key.assert_called_once_with(
        evdev.ecodes.KEY_A,
        1,
    )
    context.xkb.keycode_to_key.assert_called_once_with(
        evdev.ecodes.KEY_A,
    )
    state.input_policy.get_keyboard_action.assert_called_once_with(
        "A",
        frozenset(),
    )

    context.server.send_event.assert_called_once_with(
        {
            "type": EVENT_SHORTCUT,
            "action": action.value,
        }
    )


def test_process_input_ignores_keyboard_key_release_for_shortcut():
    context, state = build_input_processing_context()

    state.input_policy = MagicMock()

    keyboard = build_keyboard()
    event = build_input_event(
        evdev.ecodes.EV_KEY,
        evdev.ecodes.KEY_A,
        0,
    )

    context.reader.get_watched_fds.return_value = [42]
    context.reader.read_ready.return_value = [
        (keyboard, event),
    ]

    should_continue = process_input(
        context,
        state,
        [42],
        set(),
        [],
    )

    assert should_continue is False

    context.keyboard_state.update.assert_called_once_with(event)
    context.xkb.update_key.assert_called_once_with(
        evdev.ecodes.KEY_A,
        0,
    )
    context.xkb.keycode_to_key.assert_not_called()
    state.input_policy.get_keyboard_action.assert_not_called()
    context.server.send_event.assert_not_called()


def test_process_input_ignores_keyboard_modifier_for_shortcut():
    context, state = build_input_processing_context()

    state.input_policy = MagicMock()

    keyboard = build_keyboard()
    event = build_input_event(
        evdev.ecodes.EV_KEY,
        evdev.ecodes.KEY_LEFTCTRL,
        1,
    )

    context.reader.get_watched_fds.return_value = [42]
    context.reader.read_ready.return_value = [
        (keyboard, event),
    ]

    should_continue = process_input(
        context,
        state,
        [42],
        set(),
        [],
    )

    assert should_continue is False

    context.keyboard_state.update.assert_called_once_with(event)
    context.xkb.update_key.assert_called_once_with(
        evdev.ecodes.KEY_LEFTCTRL,
        1,
    )
    context.xkb.keycode_to_key.assert_not_called()
    state.input_policy.get_keyboard_action.assert_not_called()
    context.server.send_event.assert_not_called()


def test_process_input_processes_selected_events():
    context, state = build_input_processing_context()

    keyboard = build_keyboard()
    event = build_input_event(
        evdev.ecodes.EV_KEY,
        evdev.ecodes.KEY_A,
        1,
    )

    state.capture_active = True
    context.keyboard_state.get_modifiers.return_value = frozenset(
        {"CTRL"},
    )

    should_continue = process_input(
        context,
        state,
        [],
        set(),
        [(keyboard, event)],
    )

    assert should_continue is False

    context.reader.read_ready.assert_not_called()

    context.server.send_event.assert_called_once_with(
        {
            "type": EVENT_KEYBOARD_EVENT,
            "device_id": "keyboard-1",
            "code": evdev.ecodes.KEY_A,
            "value": 1,
            "timestamp": 123.456,
            "modifiers": ["CTRL"],
        }
    )


def test_process_input_sends_grabbed_mouse_button_event():
    context, state = build_input_processing_context()

    mouse = build_mouse()
    state.selected_mouse = mouse
    state.capture_active = True

    grabbed_device = MagicMock()
    grabbed_device.fileno.return_value = 99

    event = build_input_event(
        evdev.ecodes.EV_KEY,
        evdev.ecodes.BTN_SIDE,
        1,
    )

    grabbed_device.read.return_value = [event]
    state.mouse_grabber = MagicMock()
    state.mouse_grabber.is_started.return_value = True
    state.mouse_grabber.get_device.return_value = grabbed_device

    should_continue = process_input(
        context,
        state,
        [99],
        set(),
        [],
    )

    assert should_continue is False

    grabbed_device.read.assert_called_once_with()

    context.server.send_event.assert_called_once_with(
        {
            "type": EVENT_MOUSE_BUTTON_EVENT,
            "device_id": "mouse-1",
            "code": evdev.ecodes.BTN_SIDE,
            "value": 1,
            "timestamp": 123.456,
        }
    )


def test_process_input_reports_grabbed_mouse_read_error():
    context, state = build_input_processing_context()

    mouse = build_mouse()
    state.selected_mouse = mouse
    state.capture_active = True

    grabbed_device = MagicMock()
    grabbed_device.fileno.return_value = 99
    grabbed_device.read.side_effect = OSError("read failed")

    state.mouse_grabber = MagicMock()
    state.mouse_grabber.is_started.return_value = True
    state.mouse_grabber.get_device.return_value = grabbed_device

    should_continue = process_input(
        context,
        state,
        [99],
        set(),
        [],
    )

    assert should_continue is True

    context.server.send_event.assert_called_once_with(
        {
            "type": EVENT_ERROR,
            "code": ERROR_DEVICE_ERROR,
            "message": "Failed to read the selected mouse.",
        }
    )


def test_process_input_reports_interceptor_read_error_and_restores_mouse():
    context, state = build_input_processing_context()

    mouse = build_mouse()
    state.selected_mouse = mouse
    state.capture_active = True

    interceptor = MagicMock()
    interceptor.is_started.return_value = True
    interceptor.fileno.return_value = 99
    interceptor.read.side_effect = OSError("read failed")

    state.mouse_interceptor = interceptor

    should_continue = process_input(
        context,
        state,
        [99],
        set(),
        [],
    )

    assert should_continue is True

    interceptor.stop.assert_called_once_with()
    assert state.mouse_interceptor is None

    context.reader.add_device.assert_called_once_with(mouse)

    context.server.send_event.assert_called_once_with(
        {
            "type": EVENT_ERROR,
            "code": ERROR_DEVICE_ERROR,
            "message": "Failed to read the selected mouse.",
        }
    )
