from collections.abc import Callable
from dataclasses import dataclass
from typing import Iterator
import select

import evdev
import pyudev

from .discovery import InputDeviceInfo, discover_input_devices


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
    stop_requested: Callable[[], bool] = lambda: False,
    device_monitor: pyudev.Monitor | None = None,
    on_devices_changed: Callable[[], list[InputDeviceInfo]] | None = None,
) -> Iterator[InputEvent]:
    """Read events from multiple evdev interfaces simultaneously."""

    input_devices = {}
    info_by_fd = {}
    fd_by_path = {}

    def add_device(device: InputDeviceInfo) -> None:
        if device.path in input_devices:
            return

        try:
            input_device = evdev.InputDevice(device.path)
            fd = input_device.fileno()
        except (PermissionError, OSError):
            return

        input_devices[device.path] = input_device
        info_by_fd[fd] = device
        fd_by_path[device.path] = fd

    def remove_device(path: str) -> None:
        input_device = input_devices.pop(path, None)
        fd = fd_by_path.pop(path, None)

        if input_device is None:
            return

        if fd is not None:
            info_by_fd.pop(fd, None)

        input_device.close()

    def sync_devices(
        current_devices: list[InputDeviceInfo],
    ) -> None:
        current_paths = {
            device.path
            for device in current_devices
        }

        for path in list(input_devices):
            if path not in current_paths:
                remove_device(path)

        for device in current_devices:
            add_device(device)

    for device in devices:
        add_device(device)

    try:
        while not stop_requested():
            watched_fds = list(info_by_fd)

            if device_monitor is not None:
                watched_fds.append(
                    device_monitor.fileno(),
                )

            if not watched_fds:
                select.select(
                    [],
                    [],
                    [],
                    0.2,
                )
                continue

            try:
                ready, _, _ = select.select(
                    watched_fds,
                    [],
                    [],
                    0.2,
                )
            except OSError:
                if stop_requested():
                    break

                if on_devices_changed is not None:
                    sync_devices(
                        on_devices_changed(),
                    )

                continue

            if device_monitor is not None:
                monitor_fd = device_monitor.fileno()

                if monitor_fd in ready:
                    while device_monitor.poll(
                        timeout=0,
                    ) is not None:
                        pass

                    if (
                        not stop_requested()
                        and on_devices_changed is not None
                    ):
                        sync_devices(
                            on_devices_changed(),
                        )

                    ready.remove(monitor_fd)

            for fd in ready:
                device_info = info_by_fd.get(fd)

                if device_info is None:
                    continue

                input_device = input_devices.get(
                    device_info.path,
                )

                if input_device is None:
                    continue

                try:
                    for event in input_device.read():
                        yield InputEvent(
                            device=device_info,
                            event_type=event.type,
                            event_code=event.code,
                            value=event.value,
                            timestamp=event.timestamp(),
                        )
                except OSError:
                    remove_device(
                        device_info.path,
                    )

    finally:
        for input_device in input_devices.values():
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
