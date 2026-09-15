import errno
import logging
import time
from collections.abc import Iterator

import evdev

from input.discovery import InputDeviceInfo

from .devices import HelperDevice

VIRTUAL_MOUSE_NAME = "Dofus Focus Virtual Mouse"
VIRTUAL_MOUSE_PHYS = "dofus-focus-tray"

MOUSE_BUTTON_CODES = frozenset(
    value
    for name, value in vars(evdev.ecodes).items()
    if name.startswith("BTN_") and isinstance(value, int)
)

FORBIDDEN_MOUSE_BUTTON_CODES = frozenset(
    {
        evdev.ecodes.BTN_LEFT,
        evdev.ecodes.BTN_MIDDLE,
        evdev.ecodes.BTN_RIGHT,
    }
)

ALLOWED_MOUSE_BUTTON_CODES = MOUSE_BUTTON_CODES - FORBIDDEN_MOUSE_BUTTON_CODES

logger = logging.getLogger(__name__)


def is_allowed_mouse_button_event(
    event: evdev.InputEvent,
) -> bool:
    """Return whether a mouse button event is allowed during capture."""
    return (
        event.type == evdev.ecodes.EV_KEY
        and event.code in ALLOWED_MOUSE_BUTTON_CODES
        and event.value in (0, 1)
    )


class MouseSelector:
    """Select a mouse from input activity without blocking the main loop."""

    def __init__(self, timeout: float = 5.0) -> None:
        self._timeout = timeout
        self._deadline: float | None = None
        self._devices: dict[str, tuple[HelperDevice, evdev.InputDevice]] = {}

    def start(self, mice: list[HelperDevice]) -> None:
        """Start selecting a mouse from the given candidates."""
        self.stop()

        for mouse in mice:
            try:
                input_device = evdev.InputDevice(mouse.info.path)
            except (PermissionError, OSError):
                continue
            self._devices[mouse.device_id] = (mouse, input_device)

        if self._devices:
            self._deadline = time.monotonic() + self._timeout

    def add_device(self, mouse: HelperDevice) -> None:
        """Add a mouse candidate to the current selection."""
        if mouse.device_id in self._devices:
            return

        try:
            input_device = evdev.InputDevice(mouse.info.path)
        except (PermissionError, OSError):
            return

        self._devices[mouse.device_id] = (mouse, input_device)

        if self._deadline is None:
            self._deadline = time.monotonic() + self._timeout

    def remove_device(self, device_id: str) -> None:
        """Remove and close a mouse from the active selection candidates."""

        entry = self._devices.pop(device_id, None)
        if entry is None:
            return

        _, input_device = entry
        input_device.close()

        if not self._devices:
            self._deadline = None

    def get_watched_fds(self) -> list[int]:
        """Return file descriptors for active mouse candidates."""

        return [input_device.fileno() for _, input_device in self._devices.values()]

    def process_ready(
        self,
        ready_fds: list[int],
    ) -> tuple[HelperDevice, list[evdev.InputEvent]] | None:
        """Process ready candidate devices and return the selected mouse."""
        for fd in ready_fds:
            for device_id, (mouse, input_device) in list(
                self._devices.items(),
            ):
                if input_device.fileno() != fd:
                    continue

                try:
                    events = input_device.read()
                except OSError:
                    self.remove_device(device_id)
                    continue

                for event in events:
                    if event.type == evdev.ecodes.EV_REL:
                        return self._select(mouse), events

                    if (
                        event.type == evdev.ecodes.EV_KEY
                        and event.code in MOUSE_BUTTON_CODES
                    ):
                        return self._select(mouse), events

        return None

    def is_active(self) -> bool:
        """Return whether mouse selection is currently active."""

        return bool(self._devices)

    def remaining_timeout(self) -> float | None:
        """Return the remaining selection timeout."""

        if self._deadline is None:
            return None

        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            return 0.0

        return remaining

    def stop(self) -> None:
        """Stop mouse selection and close all candidate devices."""

        for _, input_device in self._devices.values():
            input_device.close()

        self._devices.clear()
        self._deadline = None

    def _select(self, mouse: HelperDevice) -> HelperDevice:
        """Select a mouse and stop watching all candidates."""

        self.stop()
        return mouse


class MouseGrabber:
    """Grab and release one selected mouse without event interception."""

    def __init__(self, device: InputDeviceInfo) -> None:
        self._device_info = device
        self._device: evdev.InputDevice | None = None

    def is_started(self) -> bool:
        """Return whether the mouse is currently grabbed."""

        return self._device is not None

    def start(self) -> bool:
        """Open and grab the selected mouse."""

        if self.is_started():
            return True

        device = evdev.InputDevice(
            self._device_info.path,
        )

        try:
            device.grab()

        except OSError as error:
            device.close()

            if error.errno == errno.EBUSY:
                return False

            raise

        self._device = device

        logger.info("Mouse grabbed.")

        return True

    def get_device(self) -> evdev.InputDevice:
        """Return the currently grabbed physical mouse device."""

        if self._device is None:
            raise RuntimeError(
                "Mouse grabber is not started.",
            )

        return self._device

    def stop(self) -> None:
        """Release and close the selected mouse."""

        device = self._device
        self._device = None

        if device is None:
            return

        try:
            device.ungrab()
        except OSError:
            pass

        device.close()

        logger.info("Mouse released.")


class MouseInterceptor:
    """Mirror events from an already grabbed mouse."""

    def __init__(
        self,
        grabber: MouseGrabber,
        intercepted_buttons: set[int],
    ) -> None:
        self._grabber = grabber
        self._intercepted_buttons = intercepted_buttons

        self._virtual_device: evdev.UInput | None = None

    def is_started(self) -> bool:
        """Return whether the interceptor is currently started."""

        return self._virtual_device is not None

    def start(self) -> bool:
        """Create a mirrored virtual device for the grabbed mouse."""

        if self.is_started():
            return True

        try:
            device = self._grabber.get_device()

            virtual_device = evdev.UInput.from_device(
                device,
                name=VIRTUAL_MOUSE_NAME,
                phys=VIRTUAL_MOUSE_PHYS,
            )

        except OSError:
            return False

        self._virtual_device = virtual_device

        logger.debug(
            "Virtual mouse created: fd=%s, intercepted_buttons=%s.",
            virtual_device.fileno(),
            sorted(self._intercepted_buttons),
        )

        return True

    def stop(self) -> None:
        """Destroy the mirrored virtual mouse."""

        virtual_device = self._virtual_device
        self._virtual_device = None

        if virtual_device is not None:
            virtual_device.close()

    def fileno(self) -> int:
        """Return the file descriptor of the grabbed mouse."""

        return self._grabber.get_device().fileno()

    def read(self) -> Iterator[evdev.InputEvent]:
        """Read currently available events from the grabbed mouse."""

        return self._grabber.get_device().read()

    def update_intercepted_buttons(
        self,
        intercepted_buttons: set[int],
    ) -> None:
        """Update the mouse buttons currently intercepted."""

        self._intercepted_buttons = intercepted_buttons

        logger.debug(
            "Mouse intercepted buttons updated: %s.",
            sorted(intercepted_buttons),
        )

    def should_intercept(
        self,
        event: evdev.InputEvent,
    ) -> bool:
        """Return whether an event should be consumed."""

        return (
            is_allowed_mouse_button_event(event)
            and event.code in self._intercepted_buttons
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
