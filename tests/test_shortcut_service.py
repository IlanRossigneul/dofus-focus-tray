import evdev

from input.classifier import Classification, DeviceClass
from input.discovery import InputDeviceInfo
from input.events import InputEvent
from shortcuts.model import Shortcut
from shortcuts.service import ShortcutService
from shortcuts.storage import ShortcutConfiguration


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
    )


def make_event(device, event_code, value=1):
    return InputEvent(
        device=device,
        event_type=evdev.ecodes.EV_KEY,
        event_code=event_code,
        value=value,
        timestamp=0.0,
    )


class FakeKeyboardLayout:
    def keycode_to_key(self, keycode):
        return {
            evdev.ecodes.KEY_N: "N",
        }.get(keycode)


def make_shortcut(trigger, modifiers=None):
    return Shortcut(
        trigger=trigger,
        modifiers=frozenset(modifiers or []),
    )


def make_configuration():
    return {
        "calibration": ShortcutConfiguration(
            primary=make_shortcut("F1"),
            alternate=None,
        ),
        "next": ShortcutConfiguration(
            primary=make_shortcut("N", ["META"]),
            alternate=None,
        ),
        "previous": ShortcutConfiguration(
            primary=make_shortcut("P", ["META"]),
            alternate=None,
        ),
    }


def test_service_executes_matching_action():
    next_shortcut = make_shortcut("N", ["META"])

    configuration = make_configuration()

    executed_actions = []

    service = ShortcutService(
        keyboard_layout=FakeKeyboardLayout(),
        configuration=configuration,
        on_action=executed_actions.append,
        stop_requested=lambda: False,
    )

    service._handle_shortcut(next_shortcut)

    assert executed_actions == ["next"]


def test_service_ignores_unconfigured_shortcut():
    shortcut = make_shortcut("X")

    executed_actions = []

    service = ShortcutService(
        keyboard_layout=FakeKeyboardLayout(),
        configuration=make_configuration(),
        on_action=executed_actions.append,
        stop_requested=lambda: False,
    )

    service._handle_shortcut(shortcut)

    assert executed_actions == []


def test_service_executes_multiple_actions():
    next_shortcut = make_shortcut("N", ["META"])
    previous_shortcut = make_shortcut("P", ["META"])

    executed_actions = []

    service = ShortcutService(
        keyboard_layout=FakeKeyboardLayout(),
        configuration=make_configuration(),
        on_action=executed_actions.append,
        stop_requested=lambda: False,
    )

    service._handle_shortcut(next_shortcut)
    service._handle_shortcut(previous_shortcut)

    assert executed_actions == [
        "next",
        "previous",
    ]


def test_service_updates_configuration():
    old_shortcut = make_shortcut("N", ["META"])
    new_shortcut = make_shortcut("P", ["META"])

    old_configuration = make_configuration()
    old_configuration["next"] = ShortcutConfiguration(
        primary=old_shortcut,
    )

    new_configuration = {
        "calibration": ShortcutConfiguration(
            primary=make_shortcut("F1"),
        ),
        "next": ShortcutConfiguration(),
        "previous": ShortcutConfiguration(
            primary=new_shortcut,
        ),
    }

    executed_actions = []

    service = ShortcutService(
        keyboard_layout=FakeKeyboardLayout(),
        configuration=old_configuration,
        on_action=executed_actions.append,
        stop_requested=lambda: False,
    )

    service.update_configuration(
        new_configuration,
    )

    service._handle_shortcut(old_shortcut)
    service._handle_shortcut(new_shortcut)

    assert executed_actions == ["previous"]


def test_service_runs_input_monitoring(monkeypatch):
    keyboard = make_device(
        "/dev/input/event0",
        "Keyboard",
    )
    gamepad = make_device(
        "/dev/input/event1",
        "Gamepad",
    )

    events = [
        make_event(
            keyboard,
            evdev.ecodes.KEY_N,
        ),
    ]

    captured_devices = []

    def fake_classify_device(device):
        if device is keyboard:
            return Classification(DeviceClass.KEYBOARD, 100)

        return Classification(DeviceClass.GAMEPAD, 100)

    def fake_read_events(
        devices,
        stop_requested,
        device_monitor,
        _,
    ):
        captured_devices.extend(devices)
        return iter(events)

    monkeypatch.setattr(
        "shortcuts.service.discover_input_devices",
        lambda: [keyboard, gamepad],
    )

    monkeypatch.setattr(
        "shortcuts.service.classify_device",
        fake_classify_device,
    )

    monkeypatch.setattr(
        "shortcuts.service.read_events_from_devices",
        fake_read_events,
    )

    executed_actions = []

    service = ShortcutService(
        keyboard_layout=FakeKeyboardLayout(),
        configuration={
            "next": ShortcutConfiguration(
                primary=make_shortcut("N"),
            ),
        },
        on_action=executed_actions.append,
        stop_requested=lambda: False,
    )

    service.run()

    assert captured_devices == [
        keyboard,
    ]
    assert executed_actions == [
        "next",
    ]
