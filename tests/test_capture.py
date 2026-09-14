from types import SimpleNamespace
from typing import ClassVar

import evdev
import pytest

from shortcuts.capture import (
    ShortcutCapture,
    ShortcutCaptureRejected,
)


class FakeXkb:
    """Provide deterministic keyboard layout translations for tests."""

    translations: ClassVar[dict[int, str]] = {
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


def make_event(
    event_type,
    event_code,
    value,
    modifiers=frozenset(),
):
    return SimpleNamespace(
        event_type=event_type,
        event_code=event_code,
        value=value,
        modifiers=modifiers,
    )


def key_event(
    key,
    value,
    modifiers=frozenset(),
):
    return make_event(
        evdev.ecodes.EV_KEY,
        key,
        value,
        modifiers,
    )


def make_capture():
    return ShortcutCapture(FakeXkb())


def test_keyboard_input_without_modifier_is_processed():
    capture = make_capture()

    shortcut = capture.process_event(
        key_event(evdev.ecodes.KEY_D, 1)
    )

    assert str(shortcut) == "D"


def test_keyboard_shortcut_is_captured():
    capture = make_capture()

    shortcut = capture.process_event(
        key_event(
            evdev.ecodes.KEY_D,
            1,
            frozenset({"CTRL"}),
        )
    )

    assert str(shortcut) == "CTRL + D"


def test_multiple_modifiers_are_captured():
    capture = make_capture()

    shortcut = capture.process_event(
        key_event(
            evdev.ecodes.KEY_D,
            1,
            frozenset({"CTRL", "ALT"}),
        )
    )

    assert str(shortcut) == "CTRL + ALT + D"


def test_keyboard_layout_is_applied_to_trigger():
    capture = make_capture()

    shortcut = capture.process_event(
        key_event(
            evdev.ecodes.KEY_Q,
            1,
            frozenset({"CTRL"}),
        )
    )

    assert str(shortcut) == "CTRL + A"
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
            key_event(
                key,
                1,
                frozenset({"CTRL"}),
            )
        )

        assert shortcut.trigger == expected_key


def test_azerty_trigger_with_modifiers_is_translated():
    capture = make_capture()

    shortcut = capture.process_event(
        key_event(
            evdev.ecodes.KEY_Q,
            1,
            frozenset({"CTRL", "ALT"}),
        )
    )

    assert str(shortcut) == "CTRL + ALT + A"


def test_mouse_button_is_captured():
    capture = make_capture()

    shortcut = capture.process_event(
        key_event(evdev.ecodes.BTN_SIDE, 1)
    )

    assert str(shortcut) == "BTN_SIDE"


def test_other_mouse_button_is_captured():
    capture = make_capture()

    shortcut = capture.process_event(
        key_event(evdev.ecodes.BTN_FORWARD, 1)
    )

    assert str(shortcut) == "BTN_FORWARD"


@pytest.mark.parametrize(
    "button_name",
    (
        "BTN_LEFT",
        "BTN_MIDDLE",
        "BTN_RIGHT",
    ),
)
def test_forbidden_mouse_buttons_are_rejected(button_name):
    capture = make_capture()

    button = getattr(evdev.ecodes, button_name)

    with pytest.raises(
        ShortcutCaptureRejected,
        match=button_name,
    ) as error:
        capture.process_event(
            key_event(button, 1)
        )

    assert error.value.trigger == button_name


def test_mouse_button_outside_allowed_set_is_rejected():
    capture = ShortcutCapture(
        FakeXkb(),
        allowed_mouse_buttons={evdev.ecodes.BTN_SIDE},
    )

    with pytest.raises(
        ShortcutCaptureRejected,
        match="BTN_FORWARD",
    ) as error:
        capture.process_event(
            key_event(evdev.ecodes.BTN_FORWARD, 1)
        )

    assert error.value.trigger == "BTN_FORWARD"


def test_mouse_motion_is_ignored():
    capture = make_capture()

    event = make_event(
        evdev.ecodes.EV_REL,
        evdev.ecodes.REL_X,
        10,
    )

    assert capture.process_event(event) is None


def test_key_repeat_is_ignored():
    capture = make_capture()

    assert capture.process_event(
        key_event(
            evdev.ecodes.KEY_D,
            2,
            frozenset({"CTRL"}),
        )
    ) is None


def test_first_valid_trigger_completes_capture():
    capture = make_capture()

    shortcut = capture.process_event(
        key_event(
            evdev.ecodes.KEY_D,
            1,
            frozenset({"CTRL"}),
        )
    )

    assert str(shortcut) == "CTRL + D"

    assert capture.process_event(
        key_event(
            evdev.ecodes.KEY_E,
            1,
            frozenset({"CTRL"}),
        )
    ) is None


def test_release_after_capture_is_ignored():
    capture = make_capture()

    capture.process_event(
        key_event(
            evdev.ecodes.KEY_D,
            1,
            frozenset({"CTRL"}),
        )
    )

    assert capture.process_event(
        key_event(
            evdev.ecodes.KEY_D,
            0,
            frozenset({"CTRL"}),
        )
    ) is None
