from typing import ClassVar

import evdev

from shortcuts.capture import ShortcutCapture
from shortcuts.events import ShortcutEvent


class FakeKeyboardLayout:
    """Provide deterministic keyboard layout translations for tests."""

    translations: ClassVar[dict[int, str]] = {
        evdev.ecodes.KEY_D: "d",
        evdev.ecodes.KEY_E: "e",
    }

    def keycode_to_key(self, keycode):
        return self.translations.get(keycode)


def make_capture():
    return ShortcutCapture(FakeKeyboardLayout())


def make_event(
    event_type: int,
    event_code: int,
    value: int,
) -> ShortcutEvent:
    return ShortcutEvent(
        event_type=event_type,
        event_code=event_code,
        value=value,
        timestamp=0.0,
    )


def test_keyboard_input_event_is_captured():
    capture = make_capture()

    assert capture.process_event(
        make_event(
            evdev.ecodes.EV_KEY,
            evdev.ecodes.KEY_LEFTCTRL,
            1,
        )
    ) is None

    shortcut = capture.process_event(
        make_event(
            evdev.ecodes.EV_KEY,
            evdev.ecodes.KEY_D,
            1,
        )
    )

    assert str(shortcut) == "CTRL + D"
    assert capture.completed is True


def test_mouse_button_input_event_is_captured():
    capture = make_capture()

    shortcut = capture.process_event(
        make_event(
            evdev.ecodes.EV_KEY,
            evdev.ecodes.BTN_SIDE,
            1,
        )
    )

    assert str(shortcut) == "BTN_SIDE"
    assert capture.completed is True


def test_mouse_button_with_keyboard_modifier_is_captured():
    capture = make_capture()

    capture.process_event(
        make_event(
            evdev.ecodes.EV_KEY,
            evdev.ecodes.KEY_LEFTCTRL,
            1,
        )
    )

    shortcut = capture.process_event(
        make_event(
            evdev.ecodes.EV_KEY,
            evdev.ecodes.BTN_EXTRA,
            1,
        )
    )

    assert str(shortcut) == "CTRL + BTN_EXTRA"
    assert capture.completed is True


def test_mouse_motion_input_event_is_ignored():
    capture = make_capture()

    event = make_event(
        evdev.ecodes.EV_REL,
        evdev.ecodes.REL_X,
        10,
    )

    assert capture.process_event(event) is None
    assert capture.completed is False


def test_unknown_keyboard_input_event_is_ignored():
    capture = make_capture()

    shortcut = capture.process_event(
        make_event(
            evdev.ecodes.EV_KEY,
            evdev.ecodes.KEY_A,
            1,
        )
    )

    assert shortcut is None
    assert capture.completed is False


def test_events_are_ignored_after_capture_is_completed():
    capture = make_capture()

    shortcut = capture.process_event(
        make_event(
            evdev.ecodes.EV_KEY,
            evdev.ecodes.KEY_D,
            1,
        )
    )

    assert str(shortcut) == "D"
    assert capture.completed is True

    assert capture.process_event(
        make_event(
            evdev.ecodes.EV_KEY,
            evdev.ecodes.KEY_E,
            1,
        )
    ) is None
