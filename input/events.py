from dataclasses import dataclass
from typing import Iterator
import select

import evdev

from .discovery import InputDeviceInfo


@dataclass(frozen=True)
class InputEvent:
    """Normalized evdev input event."""

    device: InputDeviceInfo
    event_type: int
    event_code: int
    value: int
    timestamp: float


def read_events(device: InputDeviceInfo) -> Iterator[InputEvent]:
    """Read and normalize events from a single evdev interface."""

    input_device = evdev.InputDevice(device.path)

    try:
        for event in input_device.read_loop():
            yield InputEvent(
                device=device,
                event_type=event.type,
                event_code=event.code,
                value=event.value,
                timestamp=event.timestamp(),
            )
    finally:
        input_device.close()


def read_events_from_devices(
    devices: list[InputDeviceInfo],
) -> Iterator[InputEvent]:
    """Read events from multiple evdev interfaces simultaneously."""

    input_devices = []

    for device in devices:
        try:
            input_devices.append(
                evdev.InputDevice(device.path)
            )
        except (PermissionError, OSError):
            continue

    if not input_devices:
        return

    device_by_fd = {
        input_device.fileno(): input_device
        for input_device in input_devices
    }

    info_by_fd = {
        input_device.fileno(): device
        for input_device, device in zip(input_devices, devices)
    }

    try:
        while True:
            ready, _, _ = select.select(
                input_devices,
                [],
                [],
            )

            for input_device in ready:
                device_info = info_by_fd[input_device.fileno()]

                try:
                    events = input_device.read()

                except OSError:
                    continue

                for event in events:
                    yield InputEvent(
                        device=device_info,
                        event_type=event.type,
                        event_code=event.code,
                        value=event.value,
                        timestamp=event.timestamp(),
                    )

    finally:
        for input_device in input_devices:
            input_device.close()


def is_mouse_motion(event: InputEvent) -> bool:
    """Return whether an event represents mouse movement."""

    return (
        event.event_type == evdev.ecodes.EV_REL
        and event.event_code
        in (
            evdev.ecodes.REL_X,
            evdev.ecodes.REL_Y,
        )
        and event.value != 0
    )


def is_mouse_button(event: InputEvent) -> bool:
    """Return whether an event represents a mouse button."""

    return (
        event.event_type == evdev.ecodes.EV_KEY
        and event.event_code
        in (
            evdev.ecodes.BTN_LEFT,
            evdev.ecodes.BTN_RIGHT,
            evdev.ecodes.BTN_MIDDLE,
            evdev.ecodes.BTN_SIDE,
            evdev.ecodes.BTN_EXTRA,
        )
        and event.value in (0, 1)
    )


def is_keyboard_key(event: InputEvent) -> bool:
    """Return whether an event represents a keyboard key."""

    if event.event_type != evdev.ecodes.EV_KEY:
        return False

    return event.event_code >= evdev.ecodes.KEY_RESERVED


def is_user_input(event: InputEvent) -> bool:
    """Return whether an event represents relevant user input."""

    return (
        is_mouse_motion(event)
        or is_mouse_button(event)
        or is_keyboard_key(event)
    )


def describe_event(event: InputEvent) -> str:
    """Return a human-readable description of an input event."""

    event_type = evdev.ecodes.EV.get(
        event.event_type,
        str(event.event_type),
    )

    event_code = evdev.ecodes.bytype.get(
        event.event_type,
        {},
    ).get(
        event.event_code,
        str(event.event_code),
    )

    return (
        f"{event.device.path} "
        f"{event_type} "
        f"{event_code} "
        f"{event.value}"
    )
