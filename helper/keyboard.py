import evdev

from .devices import HelperDevice

MODIFIER_KEY_NAMES = {
    evdev.ecodes.KEY_LEFTCTRL: "CTRL",
    evdev.ecodes.KEY_RIGHTCTRL: "CTRL",
    evdev.ecodes.KEY_LEFTALT: "ALT",
    evdev.ecodes.KEY_RIGHTALT: "ALTGR",
    evdev.ecodes.KEY_LEFTSHIFT: "SHIFT",
    evdev.ecodes.KEY_RIGHTSHIFT: "SHIFT",
    evdev.ecodes.KEY_LEFTMETA: "META",
    evdev.ecodes.KEY_RIGHTMETA: "META",
}

KEYBOARD_KEY_CODES = frozenset(
    value
    for name, value in vars(evdev.ecodes).items()
    if name.startswith("KEY_") and isinstance(value, int)
)


class KeyboardState:
    """Track the current state of a keyboard."""

    def __init__(self) -> None:
        self._pressed_keys: set[int] = set()

    def reset(self) -> None:
        """Clear all currently pressed keys."""
        self._pressed_keys.clear()

    def update(self, event: evdev.InputEvent) -> None:
        """Update the pressed-key state from one keyboard event."""
        if event.type != evdev.ecodes.EV_KEY:
            return

        if event.value == 1:
            self._pressed_keys.add(event.code)
        elif event.value == 0:
            self._pressed_keys.discard(event.code)

    def is_pressed(self, key_code: int) -> bool:
        """Return whether a key is currently pressed."""
        return key_code in self._pressed_keys

    def get_pressed_keys(self) -> frozenset[int]:
        """Return the currently pressed key codes."""
        return frozenset(self._pressed_keys)

    def get_modifiers(self) -> frozenset[str]:
        """Return the currently pressed modifier names."""
        return frozenset(
            modifier
            for key_code, modifier in MODIFIER_KEY_NAMES.items()
            if key_code in self._pressed_keys
        )


class KeyboardSelector:
    """Select a keyboard from input activity without blocking the main loop."""

    def __init__(self) -> None:
        self._devices: dict[
            str,
            tuple[HelperDevice, evdev.InputDevice],
        ] = {}

    def start(self, keyboards: list[HelperDevice]) -> None:
        """Start selecting a keyboard from the given candidates."""
        self.stop()

        for keyboard in keyboards:
            try:
                input_device = evdev.InputDevice(
                    keyboard.info.path,
                )
            except (PermissionError, OSError):
                continue

            self._devices[keyboard.device_id] = (
                keyboard,
                input_device,
            )

    def get_watched_fds(self) -> list[int]:
        """Return file descriptors for active keyboard candidates."""

        return [
            input_device.fileno()
            for _, input_device in self._devices.values()
        ]

    def process_ready(
        self,
        ready_fds: list[int],
    ) -> tuple[HelperDevice, list[evdev.InputEvent]] | None:
        """Process ready candidates and return the selected keyboard."""
        for fd in ready_fds:
            for device_id, (keyboard, input_device) in list(
                self._devices.items(),
            ):
                if input_device.fileno() != fd:
                    continue

                try:
                    events = list(input_device.read())

                    if any(
                        event.type == evdev.ecodes.EV_KEY
                        and event.code in KEYBOARD_KEY_CODES
                        for event in events
                    ):
                        return self._select(keyboard), events
                except OSError:
                    self.remove_device(device_id)
                    continue

        return None

    def remove_device(self, device_id: str) -> None:
        """Remove and close a keyboard from the active candidates."""

        entry = self._devices.pop(device_id, None)

        if entry is None:
            return

        _, input_device = entry
        input_device.close()

    def is_active(self) -> bool:
        """Return whether keyboard selection is currently active."""

        return bool(self._devices)

    def stop(self) -> None:
        """Stop keyboard selection and close all candidates."""

        for _, input_device in self._devices.values():
            input_device.close()

        self._devices.clear()

    def _select(self, keyboard: HelperDevice) -> HelperDevice:
        """Select a keyboard and stop watching all candidates."""

        self.stop()
        return keyboard
