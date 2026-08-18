from shortcuts.capture import ShortcutCapture
from input.classifier import DeviceClass, classify_device
from input.discovery import discover_input_devices
from input.events import read_events_from_devices
from shortcuts.keyboard import KeyboardLayout
from shortcuts.model import Shortcut


class ShortcutListener:
    """Listen to supported input devices until a shortcut is captured."""

    def __init__(self, keyboard_layout: KeyboardLayout):
        self._keyboard_layout = keyboard_layout

    def capture(self) -> Shortcut:
        """Capture the first valid shortcut from available input devices."""

        devices = discover_input_devices()

        capture_devices = [
            device
            for device in devices
            if classify_device(device).device_class
            in (
                DeviceClass.KEYBOARD,
                DeviceClass.MOUSE,
            )
        ]

        capture = ShortcutCapture(
            self._keyboard_layout,
        )

        for event in read_events_from_devices(capture_devices):
            shortcut = capture.process_event(event)

            if shortcut is not None:
                return shortcut

        raise RuntimeError("Input event stream ended before a shortcut was captured.")
