from dataclasses import dataclass
from uuid import uuid4

import evdev

from input.classifier import DeviceClass, classify_device
from input.discovery import InputDeviceInfo


@dataclass(frozen=True)
class HelperDevice:
    """Represent an input device managed by the helper."""

    device_id: str
    info: InputDeviceInfo
    device_class: DeviceClass


class DeviceRegistry:
    """Track the identity of currently discovered input devices."""

    def __init__(self) -> None:
        self._devices: dict[str, HelperDevice] = {}

    def reconcile(
        self,
        infos: list[InputDeviceInfo],
    ) -> tuple[
        list[HelperDevice],
        list[HelperDevice],
        list[HelperDevice],
    ]:
        """Reconcile discovered devices with the current registry."""

        current_by_path = {
            info.path: info
            for info in infos
        }

        added = []
        removed = []

        for path, device in list(self._devices.items()):
            if path not in current_by_path:
                removed.append(device)
                del self._devices[path]

        for path, info in current_by_path.items():
            existing = self._devices.get(path)

            if existing is not None:
                device = HelperDevice(
                    device_id=existing.device_id,
                    info=info,
                    device_class=existing.device_class,
                )
                self._devices[path] = device
                continue

            device_class = classify_device(info).device_class

            device = HelperDevice(
                device_id=str(uuid4()),
                info=info,
                device_class=device_class,
            )

            self._devices[path] = device
            added.append(device)

        current = list(self._devices.values())

        return added, removed, current


def discover_devices() -> list[InputDeviceInfo]:
    """Discover keyboard and mouse input devices available to the helper."""

    devices = []

    for path in sorted(evdev.list_devices()):
        try:
            device = evdev.InputDevice(path)
        except (PermissionError, OSError):
            continue

        try:
            info = InputDeviceInfo(
                path=path,
                name=device.name or "",
                phys=device.phys or "",
                uniq=device.uniq or "",
                vendor=device.info.vendor,
                product=device.info.product,
                bus=device.info.bustype,
                capabilities=device.capabilities(absinfo=False),
            )
            classification = classify_device(info)
        except (PermissionError, OSError):
            continue
        finally:
            device.close()

        if classification.device_class not in (
            DeviceClass.KEYBOARD,
            DeviceClass.MOUSE,
        ):
            continue

        devices.append(info)

    return devices
