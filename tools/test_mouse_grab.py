import select
import time

import evdev

from config.paths import SHORTCUTS_FILE
from input.classifier import DeviceClass, classify_device
from input.discovery import discover_input_devices
from input.interceptor import (
    MouseInterceptor,
    get_configured_mouse_buttons,
)
from shortcuts.storage import ShortcutStorage


def main() -> None:
    devices = discover_input_devices()

    mice = [
        device
        for device in devices
        if classify_device(device).device_class
        == DeviceClass.MOUSE
    ]

    print("=" * 80)
    print("Discovered mice")
    print("=" * 80)

    for device in mice:
        print(
            f"{device.path:<25} "
            f"{device.name:<45} "
            f"phys={device.phys!r}"
        )

    print("=" * 80)

    if not mice:
        print("No mouse found.")
        return

    print()
    print("Move the mouse or press a mouse button.")
    print("Listening for real mouse events for 5 seconds...")
    print()

    selected = None
    opened_devices = []

    try:
        for device in mice:
            try:
                input_device = evdev.InputDevice(device.path)
                opened_devices.append((device, input_device))
            except (PermissionError, OSError):
                continue

        deadline = time.monotonic() + 5

        while time.monotonic() < deadline and selected is None:
            fds = [
                input_device.fileno()
                for _, input_device in opened_devices
            ]

            if not fds:
                break

            remaining = deadline - time.monotonic()

            ready, _, _ = select.select(
                fds,
                [],
                [],
                remaining,
            )

            for fd in ready:
                for device, input_device in opened_devices:
                    if input_device.fileno() != fd:
                        continue

                    for event in input_device.read():
                        if event.type == evdev.ecodes.EV_REL:
                            selected = device
                            break

                        if (
                            event.type == evdev.ecodes.EV_KEY
                            and event.code
                            in (
                                evdev.ecodes.BTN_LEFT,
                                evdev.ecodes.BTN_RIGHT,
                                evdev.ecodes.BTN_MIDDLE,
                                evdev.ecodes.BTN_SIDE,
                                evdev.ecodes.BTN_EXTRA,
                            )
                        ):
                            selected = device
                            break

                    if selected is not None:
                        break

        if selected is None:
            print("No mouse event detected.")
            return

        print(
            f"Selected mouse: {selected.path} "
            f"({selected.name})"
        )

    finally:
        for _, input_device in opened_devices:
            input_device.close()

    print()
    print("Waiting 10 seconds before grabbing...")
    time.sleep(10)

    configuration = ShortcutStorage(
        SHORTCUTS_FILE,
    ).load()

    intercepted_buttons = get_configured_mouse_buttons(
        configuration,
    )

    print()
    print("Configured mouse buttons:")

    for button in sorted(intercepted_buttons):
        print(
            f"  {evdev.ecodes.BTN[button]} "
            f"({button})"
        )

    interceptor = MouseInterceptor(
        device=selected,
        intercepted_buttons=intercepted_buttons,
    )

    print(
        f"Grabbing {selected.path} "
        f"({selected.name})..."
    )

    if not interceptor.start():
        print("Failed to grab mouse.")
        return

    print()
    print("=" * 80)
    print("MOUSE GRABBED")
    print("=" * 80)
    print("BTN_SIDE is intercepted.")
    print("All other mouse events are forwarded.")
    print()
    print("Test:")
    print("- Move the mouse")
    print("- Click left")
    print("- Click right")
    print("- Click middle")
    print("- Press BTN_SIDE")
    print()
    print("Press Ctrl+C to stop.")
    print("=" * 80)

    deadline = time.monotonic() + 60

    try:
        while time.monotonic() < deadline:
            try:
                for event in interceptor.read():
                    if interceptor.should_intercept(event):
                        print(
                            "INTERCEPTED:",
                            evdev.categorize(event),
                            flush=True,
                        )
                        continue

                    print(
                        "FORWARDED:",
                        evdev.categorize(event),
                        flush=True,
                    )

                    interceptor.forward_event(event)

            except BlockingIOError:
                time.sleep(0.01)

    except KeyboardInterrupt:
        print("\nStopping early...")

    finally:
        interceptor.stop()
        print("Mouse grab released.")


if __name__ == "__main__":
    main()
