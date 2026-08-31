from dataclasses import dataclass
from pathlib import Path

import evdev


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


def discover_input_devices() -> list[InputDeviceInfo]:
    """Discover all Linux evdev input interfaces."""
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
                )
            )

        except (PermissionError, OSError):
            continue

    return devices
