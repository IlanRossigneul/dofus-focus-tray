import argparse

import evdev

from input.classifier import (
    DeviceClass,
    classify_device,
    get_devices_by_class,
)
from input.discovery import discover_input_devices
from input.events import read_events_for_classes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitor Linux evdev input events.",
    )

    input_group = parser.add_mutually_exclusive_group(
        required=True,
    )

    input_group.add_argument(
        "--mouse",
        action="store_const",
        const=DeviceClass.MOUSE,
        dest="device_class",
        help="Monitor all mouse candidates.",
    )

    input_group.add_argument(
        "--keyboard",
        action="store_const",
        const=DeviceClass.KEYBOARD,
        dest="device_class",
        help="Monitor all keyboard candidates.",
    )

    return parser.parse_args()


def get_event_code(event) -> str:
    """Return the evdev code name for an input event."""

    event_code = str(
        evdev.ecodes.bytype.get(
            event.event_type,
            {},
        ).get(
            event.event_code,
            event.event_code,
        )
    )

    return event_code


def is_relevant_event(
    event,
    device_class: DeviceClass,
) -> bool:
    """Return whether an event is relevant for the requested device class."""

    if device_class == DeviceClass.MOUSE:
        if event.event_type == evdev.ecodes.EV_REL:
            return event.event_code in (
                evdev.ecodes.REL_X,
                evdev.ecodes.REL_Y,
            )

        if event.event_type == evdev.ecodes.EV_KEY:
            return event.event_code >= evdev.ecodes.BTN_MOUSE

        return False

    if device_class == DeviceClass.KEYBOARD:
        return event.event_type == evdev.ecodes.EV_KEY

    return False


def monitor_input_devices(
    devices,
    device_class: DeviceClass,
) -> None:
    """Monitor events from all matching input interfaces simultaneously."""

    input_devices = get_devices_by_class(
        devices,
        device_class,
    )

    print("=" * 80)
    print(f"{device_class.value.capitalize()} candidates")
    print("=" * 80)

    for device in input_devices:
        classification = classify_device(device)

        print(
            f"{device.path:<25} "
            f"{device.name:<45} "
            f"confidence={classification.confidence}%"
        )
        print(f"  phys: {device.phys!r}")
        print(f"  uniq: {device.uniq!r}")

    print("=" * 80)
    print(f"Listening for {device_class.value} events...")
    print("=" * 80)

    try:
        for event in read_events_for_classes(
            (device_class,),
        ):
            if not is_relevant_event(
                event,
                device_class,
            ):
                continue

            event_type = evdev.ecodes.EV.get(
                event.event_type,
                str(event.event_type),
            )

            event_code = get_event_code(event)

            print(
                f"{event.timestamp:.6f} "
                f"{event.device.path:<25} "
                f"{event.device.name:<45} "
                f"{event_type:<8} "
                f"{event_code:<15} "
                f"{event.value}"
            )

    except KeyboardInterrupt:
        print("\nStopped.")


def main() -> int:
    args = parse_args()
    devices = discover_input_devices()

    monitor_input_devices(
        devices,
        args.device_class,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
