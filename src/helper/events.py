from collections.abc import Iterator

import evdev
import pyudev

from .devices import HelperDevice


class InputEventReader:
    """Manage open evdev devices and monitor input device changes."""

    def __init__(self) -> None:
        self._input_devices: dict[str, evdev.InputDevice] = {}
        self._info_by_fd: dict[int, HelperDevice] = {}
        self._fd_by_device_id: dict[str, int] = {}
        self._device_monitor: pyudev.Monitor | None = None

    def add_device(self, device: HelperDevice) -> None:
        """Open and track an input device."""

        if device.device_id in self._input_devices:
            return

        try:
            input_device = evdev.InputDevice(device.info.path)
            fd = input_device.fileno()
        except (PermissionError, OSError):
            return

        self._input_devices[device.device_id] = input_device
        self._info_by_fd[fd] = device
        self._fd_by_device_id[device.device_id] = fd

    def remove_device(self, device_id: str) -> None:
        """Close and stop tracking an input device."""

        input_device = self._input_devices.pop(device_id, None)
        fd = self._fd_by_device_id.pop(device_id, None)

        if input_device is None:
            return

        if fd is not None:
            self._info_by_fd.pop(fd, None)

        input_device.close()

    def read_ready(
        self,
        ready_fds: list[int],
    ) -> Iterator[tuple[HelperDevice, evdev.InputEvent]]:
        """Read events from ready input devices."""

        for fd in ready_fds:
            device = self._info_by_fd.get(fd)

            if device is None:
                continue

            input_device = self._input_devices.get(device.device_id)

            if input_device is None:
                continue

            try:
                for event in input_device.read():
                    yield device, event
            except OSError:
                self.remove_device(device.device_id)

    def start_device_monitor(self) -> None:
        """Start monitoring input device changes through udev."""

        if self._device_monitor is not None:
            return

        context = pyudev.Context()
        monitor = pyudev.Monitor.from_netlink(context)
        monitor.filter_by(subsystem="input")
        monitor.start()

        self._device_monitor = monitor

    def get_device_monitor_fd(self) -> int | None:
        """Return the udev monitor file descriptor."""

        if self._device_monitor is None:
            return None

        return self._device_monitor.fileno()

    def device_changes_pending(self) -> bool:
        """Return whether pending udev input device changes exist."""

        if self._device_monitor is None:
            return False

        changed = False

        while self._device_monitor.poll(timeout=0) is not None:
            changed = True

        return changed

    def get_watched_fds(self) -> list[int]:
        """Return file descriptors for currently open input devices."""

        return list(self._info_by_fd)

    def close(self) -> None:
        """Close all input devices and stop the udev monitor."""

        for input_device in self._input_devices.values():
            input_device.close()

        self._input_devices.clear()
        self._info_by_fd.clear()
        self._fd_by_device_id.clear()

        self._device_monitor = None
