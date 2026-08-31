import errno
import select
import time
from collections.abc import Iterator

import evdev

from .discovery import InputDeviceInfo

VIRTUAL_MOUSE_NAME = "Dofus Focus Virtual Mouse"
VIRTUAL_MOUSE_PHYS = "dofus-focus-tray"


def get_configured_mouse_buttons(
    configuration: dict,
) -> set[int]:
    """Return evdev codes for configured mouse-button shortcuts."""

    buttons = set()

    for shortcut_configuration in configuration.values():
        for shortcut in (
            shortcut_configuration.primary,
            shortcut_configuration.alternate,
        ):
            if shortcut is None:
                continue

            if not shortcut.trigger.startswith("BTN_"):
                continue

            event_code = getattr(
                evdev.ecodes,
                shortcut.trigger,
                None,
            )

            if event_code is not None:
                buttons.add(event_code)

    return buttons


def select_mouse(
    mice: list[InputDeviceInfo],
    timeout: float = 5,
) -> InputDeviceInfo | None:
    """Select the mouse that produces the first real mouse event."""

    if not mice:
        return None

    opened_devices = []

    try:
        for device in mice:
            try:
                input_device = evdev.InputDevice(device.path)
                opened_devices.append((device, input_device))
            except (PermissionError, OSError):
                continue

        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            fds = [
                input_device.fileno()
                for _, input_device in opened_devices
            ]

            if not fds:
                return None

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
                            return device

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
                            return device

    finally:
        for _, input_device in opened_devices:
            input_device.close()

    return None


class MouseInterceptor:
    """Grab one mouse and mirror its non-intercepted events."""

    def __init__(
        self,
        device: InputDeviceInfo,
        intercepted_buttons: set[int],
    ) -> None:
        self._device_info = device
        self._intercepted_buttons = intercepted_buttons

        self._device: evdev.InputDevice | None = None
        self._virtual_device: evdev.UInput | None = None

    def is_started(self) -> bool:
        """Return whether the interceptor is currently started."""

        return (
            self._device is not None
            and self._virtual_device is not None
        )

    def start(self) -> bool:
        """Grab the physical mouse and create a mirrored virtual device."""

        if self.is_started():
            return True

        device = evdev.InputDevice(
            self._device_info.path,
        )

        try:
            device.grab()

            virtual_device = evdev.UInput.from_device(
                device,
                name=VIRTUAL_MOUSE_NAME,
                phys=VIRTUAL_MOUSE_PHYS,
            )

        except OSError as error:
            device.close()

            if error.errno == errno.EBUSY:
                return False

            raise

        except Exception:
            device.close()
            raise

        self._device = device
        self._virtual_device = virtual_device

        return True

    def stop(self) -> None:
        """Release the physical mouse and destroy the virtual device."""

        virtual_device = self._virtual_device
        device = self._device

        self._virtual_device = None
        self._device = None

        if virtual_device is not None:
            virtual_device.close()

        if device is not None:
            try:
                device.ungrab()
            except OSError:
                pass

            device.close()

    def fileno(self) -> int:
        """Return the file descriptor of the grabbed mouse."""

        if self._device is None:
            raise RuntimeError(
                "Mouse interceptor is not started.",
            )

        return self._device.fileno()

    def read(self) -> Iterator[evdev.InputEvent]:
        """Read currently available events from the grabbed mouse."""

        if self._device is None:
            raise RuntimeError(
                "Mouse interceptor is not started.",
            )

        return self._device.read()

    def update_intercepted_buttons(
        self,
        intercepted_buttons: set[int],
    ) -> None:
        """Update the mouse buttons currently intercepted."""

        self._intercepted_buttons = intercepted_buttons

    def should_intercept(
        self,
        event: evdev.InputEvent,
    ) -> bool:
        """Return whether an event should be consumed."""

        return (
            event.type == evdev.ecodes.EV_KEY
            and event.code in self._intercepted_buttons
            and event.value in (0, 1)
        )

    def forward_event(
        self,
        event: evdev.InputEvent,
    ) -> None:
        """Forward an event to the mirrored virtual mouse."""

        if self._virtual_device is None:
            raise RuntimeError(
                "Mouse interceptor is not started.",
            )

        self._virtual_device.write_event(event)
        self._virtual_device.syn()
