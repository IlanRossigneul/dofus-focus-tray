from types import SimpleNamespace

import evdev

from shortcuts.capture import ShortcutCapture


class FakeKeyboardLayout:
    """Provide deterministic keyboard layout translations for tests."""

    translations = {
        evdev.ecodes.KEY_D: "d",
        evdev.ecodes.KEY_E: "e",
        evdev.ecodes.KEY_Q: "a",
        evdev.ecodes.KEY_A: "q",
        evdev.ecodes.KEY_W: "z",
        evdev.ecodes.KEY_Z: "w",
        evdev.ecodes.KEY_SEMICOLON: "m",
    }

    def keycode_to_key(self, keycode):
        return self.translations.get(keycode)


def make_event(event_type, event_code, value):
    return SimpleNamespace(
        event_type=event_type,
        event_code=event_code,
        value=value,
    )


def key_event(key, value):
    return make_event(
        evdev.ecodes.EV_KEY,
        key,
        value,
    )


def make_capture():
    return ShortcutCapture(FakeKeyboardLayout())


def test_keyboard_shortcut_is_captured():
    capture = make_capture()

    assert capture.process_event(
        key_event(evdev.ecodes.KEY_LEFTCTRL, 1)
    ) is None

    shortcut = capture.process_event(
        key_event(evdev.ecodes.KEY_D, 1)
    )

    assert str(shortcut) == "CTRL + D"
    assert capture.completed is True


def test_multiple_modifiers_are_captured():
    capture = make_capture()

    capture.process_event(
        key_event(evdev.ecodes.KEY_LEFTCTRL, 1)
    )
    capture.process_event(
        key_event(evdev.ecodes.KEY_LEFTALT, 1)
    )

    shortcut = capture.process_event(
        key_event(evdev.ecodes.KEY_D, 1)
    )

    assert str(shortcut) == "CTRL + ALT + D"


def test_modifier_release_is_tracked():
    capture = make_capture()

    capture.process_event(
        key_event(evdev.ecodes.KEY_LEFTCTRL, 1)
    )
    capture.process_event(
        key_event(evdev.ecodes.KEY_LEFTCTRL, 0)
    )

    shortcut = capture.process_event(
        key_event(evdev.ecodes.KEY_D, 1)
    )

    assert str(shortcut) == "D"


def test_keyboard_layout_is_applied_to_trigger():
    capture = make_capture()

    shortcut = capture.process_event(
        key_event(evdev.ecodes.KEY_Q, 1)
    )

    assert str(shortcut) == "A"
    assert shortcut.trigger == "A"


def test_multiple_azerty_translations_are_applied():
    expected = {
        evdev.ecodes.KEY_Q: "A",
        evdev.ecodes.KEY_A: "Q",
        evdev.ecodes.KEY_W: "Z",
        evdev.ecodes.KEY_Z: "W",
        evdev.ecodes.KEY_SEMICOLON: "M",
    }

    for key, expected_key in expected.items():
        capture = make_capture()

        shortcut = capture.process_event(
            key_event(key, 1)
        )

        assert shortcut.trigger == expected_key


def test_azerty_trigger_with_modifiers_is_translated():
    capture = make_capture()

    capture.process_event(
        key_event(evdev.ecodes.KEY_LEFTCTRL, 1)
    )
    capture.process_event(
        key_event(evdev.ecodes.KEY_LEFTALT, 1)
    )

    shortcut = capture.process_event(
        key_event(evdev.ecodes.KEY_Q, 1)
    )

    assert str(shortcut) == "CTRL + ALT + A"


def test_mouse_button_is_captured():
    capture = make_capture()

    shortcut = capture.process_event(
        key_event(evdev.ecodes.BTN_SIDE, 1)
    )

    assert str(shortcut) == "BTN_SIDE"
    assert capture.completed is True


def test_mouse_button_with_modifier_is_captured():
    capture = make_capture()

    capture.process_event(
        key_event(evdev.ecodes.KEY_LEFTCTRL, 1)
    )

    shortcut = capture.process_event(
        key_event(evdev.ecodes.BTN_SIDE, 1)
    )

    assert str(shortcut) == "CTRL + BTN_SIDE"


def test_ignored_mouse_buttons_are_not_captured():
    for button in (
        evdev.ecodes.BTN_LEFT,
        evdev.ecodes.BTN_RIGHT,
        evdev.ecodes.BTN_MIDDLE,
    ):
        capture = make_capture()

        assert capture.process_event(
            key_event(button, 1)
        ) is None

        assert capture.completed is False


def test_mouse_motion_is_ignored():
    capture = make_capture()

    event = make_event(
        evdev.ecodes.EV_REL,
        evdev.ecodes.REL_X,
        10,
    )

    assert capture.process_event(event) is None
    assert capture.completed is False


def test_key_repeat_is_ignored():
    capture = make_capture()

    capture.process_event(
        key_event(evdev.ecodes.KEY_LEFTCTRL, 1)
    )

    assert capture.process_event(
        key_event(evdev.ecodes.KEY_D, 2)
    ) is None

    assert capture.completed is False


def test_first_valid_trigger_completes_capture():
    capture = make_capture()

    shortcut = capture.process_event(
        key_event(evdev.ecodes.KEY_D, 1)
    )

    assert str(shortcut) == "D"
    assert capture.completed is True

    assert capture.process_event(
        key_event(evdev.ecodes.KEY_E, 1)
    ) is None


def test_release_after_capture_is_ignored():
    capture = make_capture()

    capture.process_event(
        key_event(evdev.ecodes.KEY_D, 1)
    )

    assert capture.process_event(
        key_event(evdev.ecodes.KEY_D, 0)
    ) is None
