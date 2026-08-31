import evdev

from input.discovery import InputDeviceInfo
from input.events import InputEvent
from shortcuts.processor import ShortcutProcessor

DEVICE = InputDeviceInfo(
    path="/dev/input/event0",
    name="Test device",
    phys="",
    uniq="",
    vendor=0,
    product=0,
    bus=0,
    capabilities={},
)


class FakeKeyboardLayout:
    def keycode_to_key(self, keycode):
        return {
            evdev.ecodes.KEY_N: "N",
        }.get(keycode)


def make_event(event_code, value=1):
    return InputEvent(
        device=DEVICE,
        event_type=evdev.ecodes.EV_KEY,
        event_code=event_code,
        value=value,
        timestamp=0.0,
    )


def make_processor():
    return ShortcutProcessor(FakeKeyboardLayout())


def test_key_without_modifier_produces_shortcut():
    processor = make_processor()

    shortcut = processor.process_event(
        make_event(evdev.ecodes.KEY_N),
    )

    assert shortcut is not None
    assert shortcut.trigger == "N"
    assert shortcut.modifiers == frozenset()


def test_modifier_press_does_not_produce_shortcut():
    processor = make_processor()

    shortcut = processor.process_event(
        make_event(evdev.ecodes.KEY_LEFTCTRL),
    )

    assert shortcut is None


def test_modifier_is_included_in_shortcut():
    processor = make_processor()

    processor.process_event(
        make_event(evdev.ecodes.KEY_LEFTCTRL),
    )

    shortcut = processor.process_event(
        make_event(evdev.ecodes.KEY_N),
    )

    assert shortcut is not None
    assert shortcut.trigger == "N"
    assert shortcut.modifiers == frozenset({"CTRL"})


def test_multiple_modifiers_are_included_in_shortcut():
    processor = make_processor()

    processor.process_event(
        make_event(evdev.ecodes.KEY_LEFTCTRL),
    )
    processor.process_event(
        make_event(evdev.ecodes.KEY_LEFTSHIFT),
    )

    shortcut = processor.process_event(
        make_event(evdev.ecodes.KEY_N),
    )

    assert shortcut is not None
    assert shortcut.trigger == "N"
    assert shortcut.modifiers == frozenset({"CTRL", "SHIFT"})


def test_modifier_release_removes_modifier():
    processor = make_processor()

    processor.process_event(
        make_event(evdev.ecodes.KEY_LEFTCTRL),
    )
    processor.process_event(
        make_event(
            evdev.ecodes.KEY_LEFTCTRL,
            value=0,
        ),
    )

    shortcut = processor.process_event(
        make_event(evdev.ecodes.KEY_N),
    )

    assert shortcut is not None
    assert shortcut.modifiers == frozenset()


def test_key_release_does_not_produce_shortcut():
    processor = make_processor()

    shortcut = processor.process_event(
        make_event(
            evdev.ecodes.KEY_N,
            value=0,
        ),
    )

    assert shortcut is None


def test_key_repeat_does_not_produce_shortcut():
    processor = make_processor()

    shortcut = processor.process_event(
        make_event(
            evdev.ecodes.KEY_N,
            value=2,
        ),
    )

    assert shortcut is None


def test_btn_extra_produces_shortcut():
    processor = make_processor()

    shortcut = processor.process_event(
        make_event(evdev.ecodes.BTN_EXTRA),
    )

    assert shortcut is not None
    assert shortcut.trigger == "BTN_EXTRA"
    assert shortcut.modifiers == frozenset()


def test_btn_side_produces_shortcut():
    processor = make_processor()

    shortcut = processor.process_event(
        make_event(evdev.ecodes.BTN_SIDE),
    )

    assert shortcut is not None
    assert shortcut.trigger == "BTN_SIDE"
    assert shortcut.modifiers == frozenset()


def test_left_mouse_button_does_not_produce_shortcut():
    processor = make_processor()

    shortcut = processor.process_event(
        make_event(evdev.ecodes.BTN_LEFT),
    )

    assert shortcut is None


def test_right_mouse_button_does_not_produce_shortcut():
    processor = make_processor()

    shortcut = processor.process_event(
        make_event(evdev.ecodes.BTN_RIGHT),
    )

    assert shortcut is None


def test_middle_mouse_button_does_not_produce_shortcut():
    processor = make_processor()

    shortcut = processor.process_event(
        make_event(evdev.ecodes.BTN_MIDDLE),
    )

    assert shortcut is None


def test_modifier_state_is_preserved_between_events():
    processor = make_processor()

    processor.process_event(
        make_event(evdev.ecodes.KEY_LEFTCTRL),
    )

    first_shortcut = processor.process_event(
        make_event(evdev.ecodes.KEY_N),
    )

    second_shortcut = processor.process_event(
        make_event(evdev.ecodes.KEY_N),
    )

    assert first_shortcut.modifiers == frozenset({"CTRL"})
    assert second_shortcut.modifiers == frozenset({"CTRL"})
