from dataclasses import dataclass, field
from pathlib import Path

from .discovery import InputDeviceInfo


@dataclass
class PhysicalDevice:
    """A physical device exposing one or more evdev input interfaces."""

    physical_id: str
    name: str
    interfaces: list[InputDeviceInfo] = field(default_factory=list)


def _find_usb_parent(path: str) -> str | None:
    """Find the USB device path shared by all interfaces of a physical device."""

    event_name = Path(path).name
    device_path = Path("/sys/class/input") / event_name / "device"

    try:
        current = device_path.resolve()
    except FileNotFoundError:
        return None

    for parent in (current, *current.parents):
        if (parent / "idVendor").exists() and (parent / "idProduct").exists():
            return str(parent)

    return None


def _get_physical_id(device: InputDeviceInfo) -> str:
    """Build a stable identifier for the physical device."""

    usb_parent = _find_usb_parent(device.path)

    if usb_parent is not None:
        return f"usb:{usb_parent}"

    properties = device.udev_properties

    path = properties.get("ID_PATH")
    if path:
        return f"path:{path}"

    serial = properties.get("ID_SERIAL")
    if serial and serial != "noserial":
        return f"serial:{serial}"

    return f"event:{Path(device.path).name}"


def group_physical_devices(
    interfaces: list[InputDeviceInfo],
) -> list[PhysicalDevice]:
    """Group evdev interfaces belonging to the same physical device."""

    devices: dict[str, PhysicalDevice] = {}

    for interface in interfaces:
        physical_id = _get_physical_id(interface)

        device = devices.get(physical_id)

        if device is None:
            device = PhysicalDevice(
                physical_id=physical_id,
                name=interface.name,
            )
            devices[physical_id] = device

        device.interfaces.append(interface)

    return list(devices.values())
