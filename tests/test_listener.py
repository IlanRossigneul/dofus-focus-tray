import evdev
import pytest

from input.classifier import DeviceClass
from input.events import InputEvent
from shortcuts.listener import ShortcutListener


class FakeKeyboardLayout:
    def keycode_to_key(self, keycode):
        return evdev.ecodes.KEY[keycode].removeprefix("KEY_")


def make_event(event_type, event_code, value):
    return InputEvent(
        device=None,
        event_type=event_type,
        event_code=event_code,
        value=value,
        timestamp=0.0,
    )


def test_listener_captures_first_valid_shortcut(monkeypatch):
    events = [
        make_event(
            evdev.ecodes.EV_KEY,
            evdev.ecodes.KEY_LEFTCTRL,
            1,
        ),
        make_event(
            evdev.ecodes.EV_KEY,
            evdev.ecodes.KEY_D,
            1,
        ),
        make_event(
            evdev.ecodes.EV_KEY,
            evdev.ecodes.KEY_E,
            1,
        ),
    ]

    monkeypatch.setattr(
        "shortcuts.listener.read_events_for_classes",
        lambda device_classes, stop_requested=lambda: False: iter(events),
    )

    shortcut = ShortcutListener(
        FakeKeyboardLayout(),
    ).capture(
        (
            DeviceClass.KEYBOARD,
        ),
    )

    assert str(shortcut) == "CTRL + D"


def test_listener_passes_requested_device_classes_to_event_reader(monkeypatch):
    received_device_classes = []

    def fake_read_events(
        device_classes,
        stop_requested=lambda: False,
    ):
        received_device_classes.append(device_classes)
        return iter(())

    monkeypatch.setattr(
        "shortcuts.listener.read_events_for_classes",
        fake_read_events,
    )

    with pytest.raises(
        RuntimeError,
        match="Input event stream ended before a shortcut was captured.",
    ):
        ShortcutListener(
            FakeKeyboardLayout(),
        ).capture(
            (
                DeviceClass.KEYBOARD,
                DeviceClass.MOUSE,
            ),
        )

    assert received_device_classes == [
        (
            DeviceClass.KEYBOARD,
            DeviceClass.MOUSE,
        ),
    ]


def test_listener_accepts_mouse_shortcut(monkeypatch):
    events = [
        make_event(
            evdev.ecodes.EV_KEY,
            evdev.ecodes.BTN_SIDE,
            1,
        ),
    ]

    monkeypatch.setattr(
        "shortcuts.listener.read_events_for_classes",
        lambda device_classes, stop_requested=lambda: False: iter(events),
    )

    shortcut = ShortcutListener(
        FakeKeyboardLayout(),
    ).capture(
        (
            DeviceClass.MOUSE,
        ),
        allowed_mouse_buttons={
            evdev.ecodes.BTN_SIDE,
        },
    )

    assert str(shortcut) == "BTN_SIDE"


def test_listener_stops_at_first_valid_shortcut(monkeypatch):
    events = [
        make_event(
            evdev.ecodes.EV_KEY,
            evdev.ecodes.KEY_D,
            1,
        ),
        make_event(
            evdev.ecodes.EV_KEY,
            evdev.ecodes.KEY_E,
            1,
        ),
    ]

    consumed_events = []

    def fake_read_events(
        device_classes,
        stop_requested=lambda: False,
    ):
        for event in events:
            consumed_events.append(event)
            yield event

    monkeypatch.setattr(
        "shortcuts.listener.read_events_for_classes",
        fake_read_events,
    )

    shortcut = ShortcutListener(
        FakeKeyboardLayout(),
    ).capture(
        (
            DeviceClass.KEYBOARD,
        ),
    )

    assert str(shortcut) == "D"
    assert consumed_events == [events[0]]


def test_listener_raises_if_event_stream_ends(monkeypatch):
    monkeypatch.setattr(
        "shortcuts.listener.read_events_for_classes",
        lambda device_classes, stop_requested=lambda: False: iter(()),
    )

    with pytest.raises(
        RuntimeError,
        match="Input event stream ended before a shortcut was captured.",
    ):
        ShortcutListener(
            FakeKeyboardLayout(),
        ).capture(
            (
                DeviceClass.KEYBOARD,
            ),
        )


def test_listener_passes_stop_requested_to_event_reader(monkeypatch):
    received_stop_requested = []

    def stop_requested():
        return True

    def fake_read_events(
        device_classes,
        stop_requested=lambda: False,
    ):
        received_stop_requested.append(stop_requested)
        return iter(())

    monkeypatch.setattr(
        "shortcuts.listener.read_events_for_classes",
        fake_read_events,
    )

    with pytest.raises(RuntimeError):
        ShortcutListener(
            FakeKeyboardLayout(),
        ).capture(
            (
                DeviceClass.KEYBOARD,
            ),
            stop_requested=stop_requested,
        )

    assert len(received_stop_requested) == 1
    assert received_stop_requested[0] is stop_requested
