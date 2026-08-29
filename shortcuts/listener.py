from collections.abc import Collection

from input.classifier import DeviceClass
from input.events import read_events_for_classes
from shortcuts.capture import ShortcutCapture
from shortcuts.keyboard import KeyboardLayout
from shortcuts.model import Shortcut


class ShortcutListener:
    """Listen to supported input devices until a shortcut is captured."""

    def __init__(
        self,
        keyboard_layout: KeyboardLayout,
    ) -> None:
        self._keyboard_layout = keyboard_layout

    def capture(
        self,
        device_classes: Collection[DeviceClass],
        allowed_mouse_buttons: set[int] | None = None,
        stop_requested=lambda: False,
    ) -> Shortcut:
        """Capture the first valid shortcut from the requested device classes."""

        capture = ShortcutCapture(
            self._keyboard_layout,
            allowed_mouse_buttons=allowed_mouse_buttons,
        )

        for event in read_events_for_classes(
            device_classes,
            stop_requested=stop_requested,
        ):
            shortcut = capture.process_event(event)

            if shortcut is not None:
                return shortcut

        raise RuntimeError(
            "Input event stream ended before a shortcut was captured."
        )
