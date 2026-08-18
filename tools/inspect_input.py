import argparse

import evdev

from input.classifier import DeviceClass, classify_device
from input.discovery import discover_input_devices
from input.events import (
    is_keyboard_key,
    is_mouse_button,
    is_mouse_motion,
    read_events,
    read_events_from_devices,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect Linux evdev input events."
    )

    parser.add_argument(
        "--event",
        help="Path to the evdev interface to monitor.",
    )

    parser.add_argument(
        "--monitor",
        action="store_true",
        help="Monitor all relevant input interfaces simultaneously.",
    )

    return parser.parse_args()


def find_device(devices, path):
    for device in devices:
        if device.path == path:
            return device

    return None


def get_event_category(event) -> str | None:
    """Return the relevant user-input category for an event."""

    if is_mouse_motion(event):
        return "MOUSE_MOTION"

    if is_mouse_button(event):
        return "MOUSE_BUTTON"

    if is_keyboard_key(event):
        return "KEYBOARD_KEY"

    return None


def monitor_device(device):
    """Monitor a single evdev interface."""

    classification = classify_device(device)

    print("=" * 80)
    print(f"Device: {device.name}")
    print(f"Path:   {device.path}")
    print(f"Type:   {classification.device_class.value}")
    print(f"Score:  {classification.confidence}%")
    print("=" * 80)

    try:
        for event in read_events(device):
            category = get_event_category(event)

            if category is None:
                continue

            event_type = evdev.ecodes.EV.get(
                event.event_type,
                str(event.event_type),
            )

            event_code = str(
                evdev.ecodes.bytype.get(
                    event.event_type,
                    {},
                ).get(
                    event.event_code,
                    event.event_code,
                )
            )

            print(
                f"{event.timestamp:.6f} "
                f"{category:<15} "
                f"{event_type:<10} "
                f"{event_code:<20} "
                f"{event.value}"
            )

    except KeyboardInterrupt:
        print("\nStopped.")


def get_monitorable_devices(devices):
    """Return interfaces that may represent user input devices."""

    monitorable_classes = {
        DeviceClass.MOUSE,
        DeviceClass.KEYBOARD,
        DeviceClass.GAMEPAD,
    }

    return [
        device
        for device in devices
        if classify_device(device).device_class
        in monitorable_classes
    ]


def monitor_all_devices(devices):
    """Monitor all candidate input interfaces simultaneously."""

    monitorable_devices = get_monitorable_devices(devices)

    print("=" * 80)
    print("Monitoring input interfaces")
    print("=" * 80)

    for device in monitorable_devices:
        classification = classify_device(device)

        print(
            f"{device.path:<25} "
            f"{device.name:<45} "
            f"{classification.device_class.value:<10}"
        )

    print("=" * 80)
    print("Waiting for user input...")
    print("=" * 80)

    try:
        for event in read_events_from_devices(monitorable_devices):
            category = get_event_category(event)

            if category is None:
                continue

            event_type = evdev.ecodes.EV.get(
                event.event_type,
                str(event.event_type),
            )

            event_code = str(
                evdev.ecodes.bytype.get(
                    event.event_type,
                    {},
                ).get(
                    event.event_code,
                    event.event_code,
                )
            )

            print(
                f"{event.timestamp:.6f} "
                f"{event.device.path:<25} "
                f"{event.device.name:<45} "
                f"{category:<15} "
                f"{event_type:<10} "
                f"{event_code:<20} "
                f"{event.value}"
            )

    except KeyboardInterrupt:
        print("\nStopped.")


def main():
    args = parse_args()
    devices = discover_input_devices()

    if args.event:
        device = find_device(devices, args.event)

        if device is None:
            print(f"Unknown input device: {args.event}")
            return 1

        monitor_device(device)
        return 0

    if args.monitor:
        monitor_all_devices(devices)
        return 0

    for device in devices:
        classification = classify_device(device)

        print(
            f"{device.path:<25} "
            f"{device.name:<45} "
            f"{classification.device_class.value:<18} "
            f"{classification.confidence}%"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
