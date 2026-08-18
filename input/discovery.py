from dataclasses import dataclass
from pathlib import Path

import evdev
import pyudev


@dataclass(frozen=True)
class InputDeviceInfo:
    path: str
    name: str
    phys: str
    uniq: str
    vendor: int
    product: int
    bus: int
    capabilities: dict
    udev_properties: dict[str, str]


def _get_udev_properties(context: pyudev.Context, path: str) -> dict[str, str]:
    """Return udev properties associated with an input device."""
    device = pyudev.Devices.from_device_file(context, path)

    return {
        key: value
        for key, value in device.properties.items()
        if value is not None
    }


def discover_input_devices() -> list[InputDeviceInfo]:
    """Discover all Linux evdev input interfaces."""
    context = pyudev.Context()
    devices = []

    for path in sorted(Path("/dev/input").glob("event*")):
        try:
            device = evdev.InputDevice(str(path))

            devices.append(
                InputDeviceInfo(
                    path=str(path),
                    name=device.name or "",
                    phys=device.phys or "",
                    uniq=device.uniq or "",
                    vendor=device.info.vendor,
                    product=device.info.product,
                    bus=device.info.bustype,
                    capabilities=device.capabilities(absinfo=False),
                    udev_properties=_get_udev_properties(context, str(path)),
                )
            )

        except (PermissionError, OSError, pyudev.DeviceNotFoundByFileError):
            continue

    return devices
