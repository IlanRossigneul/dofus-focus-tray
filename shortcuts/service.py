from collections.abc import Callable

from input.classifier import DeviceClass, classify_device
from input.discovery import discover_input_devices
from input.events import read_events_from_devices
from shortcuts.keyboard import KeyboardLayout
from shortcuts.model import Shortcut
from shortcuts.processor import ShortcutProcessor
from shortcuts.storage import ShortcutConfiguration


class ShortcutService:
    """Monitor input devices and execute configured shortcut actions."""

    def __init__(
        self,
        keyboard_layout: KeyboardLayout,
        configuration: dict[str, ShortcutConfiguration],
        on_action: Callable[[str], None],
        stop_requested: Callable[[], bool],
    ):
        self._configuration = configuration
        self._on_action = on_action
        self._stop_requested = stop_requested
        self._processor = ShortcutProcessor(
            keyboard_layout,
        )

    def _match_shortcut(
        self,
        shortcut: Shortcut,
    ) -> str | None:
        """Return the action matching a shortcut, or None if there is no match."""

        for action, configuration in self._configuration.items():
            if shortcut in (
                configuration.primary,
                configuration.alternate,
            ):
                return action

        return None

    def _handle_shortcut(self, shortcut: Shortcut) -> None:
        """Handle a captured shortcut and execute its configured action."""

        action = self._match_shortcut(shortcut)

        if action is not None:
            self._on_action(action)

    def update_configuration(
        self,
        configuration: dict[str, ShortcutConfiguration],
    ) -> None:
        """Update the configured shortcut actions."""

        self._configuration = configuration

    def run(self) -> None:
        """Monitor input events until monitoring is stopped."""

        devices = discover_input_devices()

        monitor_devices = [
            device
            for device in devices
            if classify_device(device).device_class
            in (
                DeviceClass.KEYBOARD,
                DeviceClass.MOUSE,
            )
        ]

        for event in read_events_from_devices(
            monitor_devices,
            self._stop_requested,
        ):
            shortcut = self._processor.process_event(event)

            if shortcut is not None:
                self._handle_shortcut(shortcut)
