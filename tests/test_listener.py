import evdev

from input.classifier import DeviceClass, Classification
from input.events import InputEvent
from input.discovery import InputDeviceInfo
from shortcuts.listener import ShortcutListener


class FakeKeyboardLayout:
    def keycode_to_key(self, keycode):
        return evdev.ecodes.KEY[keycode].removeprefix("KEY_")


def make_device(path, name="Test device"):
    return InputDeviceInfo(
        path=path,
        name=name,
        phys="",
        uniq="",
        vendor=0,
        product=0,
        bus=0,
        capabilities={},
        udev_properties={},
    )


def make_event(device, event_type, event_code, value):
    return InputEvent(
        device=device,
        event_type=event_type,
        event_code=event_code,
        value=value,
        timestamp=0.0,
    )


def test_listener_captures_first_valid_shortcut(monkeypatch):
    keyboard = make_device("/dev/input/event0", "Keyboard")

    events = [
        make_event(
            keyboard,
            evdev.ecodes.EV_KEY,
            evdev.ecodes.KEY_LEFTCTRL,
            1,
        ),
        make_event(
            keyboard,
            evdev.ecodes.EV_KEY,
            evdev.ecodes.KEY_D,
            1,
        ),
        make_event(
            keyboard,
            evdev.ecodes.EV_KEY,
            evdev.ecodes.KEY_E,
            1,
        ),
    ]

    monkeypatch.setattr(
        "shortcuts.listener.discover_input_devices",
        lambda: [keyboard],
    )

    monkeypatch.setattr(
        "shortcuts.listener.classify_device",
        lambda device: Classification(DeviceClass.KEYBOARD, 100),
    )

    monkeypatch.setattr(
        "shortcuts.listener.read_events_from_devices",
        lambda devices: iter(events),
    )

    shortcut = ShortcutListener(FakeKeyboardLayout()).capture()

    assert str(shortcut) == "CTRL + D"


def test_listener_uses_keyboard_and_mouse_devices(monkeypatch):
    keyboard = make_device("/dev/input/event0", "Keyboard")
    mouse = make_device("/dev/input/event1", "Mouse")
    gamepad = make_device("/dev/input/event2", "Gamepad")

    def fake_classify_device(device):
        if device is keyboard:
            return Classification(DeviceClass.KEYBOARD, 100)

        if device is mouse:
            return Classification(DeviceClass.MOUSE, 100)

        return Classification(DeviceClass.GAMEPAD, 100)

    captured_devices = []

    monkeypatch.setattr(
        "shortcuts.listener.discover_input_devices",
        lambda: [keyboard, mouse, gamepad],
    )

    monkeypatch.setattr(
        "shortcuts.listener.classify_device",
        fake_classify_device,
    )

    def fake_read_events(devices):
        captured_devices.extend(devices)
        return iter(())

    monkeypatch.setattr(
        "shortcuts.listener.read_events_from_devices",
        fake_read_events,
    )

    try:
        ShortcutListener(FakeKeyboardLayout()).capture()
    except RuntimeError:
        pass

    assert captured_devices == [keyboard, mouse]


def test_listener_accepts_mouse_shortcut(monkeypatch):
    mouse = make_device("/dev/input/event1", "Mouse")

    events = [
        make_event(
            mouse,
            evdev.ecodes.EV_KEY,
            evdev.ecodes.BTN_SIDE,
            1,
        ),
    ]

    monkeypatch.setattr(
        "shortcuts.listener.discover_input_devices",
        lambda: [mouse],
    )

    monkeypatch.setattr(
        "shortcuts.listener.classify_device",
        lambda device: Classification(DeviceClass.MOUSE, 100),
    )

    monkeypatch.setattr(
        "shortcuts.listener.read_events_from_devices",
        lambda devices: iter(events),
    )

    shortcut = ShortcutListener(FakeKeyboardLayout()).capture()

    assert str(shortcut) == "BTN_SIDE"


def test_listener_stops_at_first_valid_shortcut(monkeypatch):
    keyboard = make_device("/dev/input/event0", "Keyboard")

    events = [
        make_event(
            keyboard,
            evdev.ecodes.EV_KEY,
            evdev.ecodes.KEY_D,
            1,
        ),
        make_event(
            keyboard,
            evdev.ecodes.EV_KEY,
            evdev.ecodes.KEY_E,
            1,
        ),
    ]

    consumed_events = []

    def fake_read_events(devices):
        for event in events:
            consumed_events.append(event)
            yield event

    monkeypatch.setattr(
        "shortcuts.listener.discover_input_devices",
        lambda: [keyboard],
    )

    monkeypatch.setattr(
        "shortcuts.listener.classify_device",
        lambda device: Classification(DeviceClass.KEYBOARD, 100),
    )

    monkeypatch.setattr(
        "shortcuts.listener.read_events_from_devices",
        fake_read_events,
    )

    shortcut = ShortcutListener(FakeKeyboardLayout()).capture()

    assert str(shortcut) == "D"
    assert consumed_events == [events[0]]


def test_listener_raises_if_event_stream_ends(monkeypatch):
    keyboard = make_device("/dev/input/event0", "Keyboard")

    monkeypatch.setattr(
        "shortcuts.listener.discover_input_devices",
        lambda: [keyboard],
    )

    monkeypatch.setattr(
        "shortcuts.listener.classify_device",
        lambda device: Classification(DeviceClass.KEYBOARD, 100),
    )

    monkeypatch.setattr(
        "shortcuts.listener.read_events_from_devices",
        lambda devices: iter(()),
    )

    try:
        ShortcutListener(FakeKeyboardLayout()).capture()
    except RuntimeError as error:
        assert str(error) == (
            "Input event stream ended before a shortcut was captured."
        )
    else:
        raise AssertionError("Expected RuntimeError")
