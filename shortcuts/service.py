import logging
import select
import threading
import time
from collections.abc import Callable

import evdev
import pyudev

from input.classifier import DeviceClass, classify_device
from input.discovery import InputDeviceInfo, discover_input_devices
from input.events import read_events_from_devices
from input.interceptor import (
    MouseInterceptor,
    get_configured_mouse_buttons,
    select_mouse,
)

from .keyboard import KeyboardLayout
from .model import Shortcut
from .processor import ShortcutProcessor
from .storage import ShortcutConfiguration

MOUSE_DISCOVERY_ATTEMPTS = 10
MOUSE_DISCOVERY_RETRY_DELAY = 1.0


logger = logging.getLogger(__name__)


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
        self._enabled = True
        self._mouse_interception_enabled = True
        self._calibrated = False

        self._processor = ShortcutProcessor(
            keyboard_layout,
        )

        self._selected_mouse: InputDeviceInfo | None = None
        self._mouse_interceptor: MouseInterceptor | None = None
        self._mouse_discovery_thread: threading.Thread | None = None
        self._mouse_thread: threading.Thread | None = None
        self._mouse_state_lock = threading.RLock()
        self._mouse_stop_event = threading.Event()

    def _select_mouse_with_retry(
        self,
    ) -> InputDeviceInfo | None:
        """Try to select a mouse repeatedly until one is detected."""

        for attempt in range(MOUSE_DISCOVERY_ATTEMPTS):
            if self._stop_requested():
                return None

            monitor_devices = self._get_monitored_devices()

            mice = [
                device
                for device in monitor_devices
                if classify_device(device).device_class
                == DeviceClass.MOUSE
            ]

            selected_mouse = select_mouse(mice)

            if selected_mouse is not None:
                return selected_mouse

            if attempt < MOUSE_DISCOVERY_ATTEMPTS - 1:
                time.sleep(MOUSE_DISCOVERY_RETRY_DELAY)

        return None

    def _run_mouse_discovery(self) -> None:
        """Select the mouse that will be used for interception."""

        selected_mouse = self._select_mouse_with_retry()

        if selected_mouse is None:
            return

        with self._mouse_state_lock:
            self._selected_mouse = selected_mouse

            logger.info(
                "Mouse grab started: device=%s path=%s",
                selected_mouse.name,
                selected_mouse.path,
            )

            if self._calibrated:
                self._start_mouse_interceptor()

    def _start_mouse_discovery(self) -> None:
        """Start mouse discovery if no discovery is already running."""

        if self._stop_requested():
            return

        if (
            self._mouse_discovery_thread is not None
            and self._mouse_discovery_thread.is_alive()
        ):
            return

        self._mouse_discovery_thread = threading.Thread(
            target=self._run_mouse_discovery,
            name="MouseDiscoveryThread",
            daemon=True,
        )

        self._mouse_discovery_thread.start()

    def _process_mouse_event(
        self,
        event: evdev.InputEvent,
    ) -> None:
        """Process an intercepted mouse-button event."""

        if event.value != 1:
            return

        trigger = evdev.ecodes.BTN.get(
            event.code,
        )

        if trigger is None:
            return

        self._handle_shortcut(
            Shortcut(
                trigger=trigger,
            ),
        )

    def _run_mouse_interceptor(
        self,
        interceptor: MouseInterceptor,
    ) -> None:
        """Process intercepted mouse events while interception is active."""

        while (
            not self._mouse_stop_event.is_set()
            and self._mouse_interceptor is interceptor
        ):
            try:
                ready, _, _ = select.select(
                    [interceptor.fileno()],
                    [],
                    [],
                    0.1,
                )

                if not ready:
                    continue

                for event in interceptor.read():
                    if self._mouse_stop_event.is_set():
                        break

                    if interceptor.should_intercept(event):
                        logger.debug(
                            "Mouse event intercepted: event=%s",
                            evdev.categorize(event),
                        )

                        self._process_mouse_event(
                            event,
                        )

                        continue

                    interceptor.forward_event(event)

            except BlockingIOError:
                continue

            except (OSError, ValueError):
                break

    def _start_mouse_interceptor(self) -> None:
        """Start mouse interception if a mouse has been selected."""

        with self._mouse_state_lock:
            if self._selected_mouse is None:
                return

            if self._mouse_interceptor is not None:
                return

            intercepted_buttons = (
                get_configured_mouse_buttons(
                    self._configuration,
                )
                if self._mouse_interception_enabled
                else set()
            )

            interceptor = MouseInterceptor(
                device=self._selected_mouse,
                intercepted_buttons=intercepted_buttons,
            )

            if not interceptor.start():
                return

            self._mouse_interceptor = interceptor

            self._mouse_stop_event.clear()

            self._mouse_thread = threading.Thread(
                target=self._run_mouse_interceptor,
                args=(interceptor,),
                name="MouseInterceptorThread",
                daemon=True,
            )

            self._mouse_thread.start()

    def _stop_mouse_interceptor(self) -> None:
        """Stop mouse interception and wait for the worker thread to exit."""

        with self._mouse_state_lock:
            interceptor = self._mouse_interceptor
            mouse_thread = self._mouse_thread

            if interceptor is None:
                return

            self._mouse_stop_event.set()
            self._mouse_interceptor = None

            if (
                mouse_thread is not None
                and mouse_thread is not threading.current_thread()
            ):
                mouse_thread.join()

            self._mouse_thread = None

            interceptor.stop()

            logger.info("Mouse grab released")

    def set_calibration_valid(
        self,
        calibrated: bool,
    ) -> None:
        """Update the calibration state and synchronize mouse interception."""

        if self._calibrated == calibrated:
            return

        self._calibrated = calibrated

        if calibrated:
            self._start_mouse_interceptor()
        else:
            self._stop_mouse_interceptor()

    def set_mouse_interception_enabled(
        self,
        enabled: bool,
    ) -> None:
        """Enable or disable interception of configured mouse buttons."""

        if self._mouse_interception_enabled == enabled:
            return

        self._mouse_interception_enabled = enabled

        if self._mouse_interceptor is None:
            return

        intercepted_buttons = (
            get_configured_mouse_buttons(
                self._configuration,
            )
            if enabled
            else set()
        )

        self._mouse_interceptor.update_intercepted_buttons(
            intercepted_buttons,
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

    def _handle_shortcut(
        self,
        shortcut: Shortcut,
    ) -> None:
        """Handle a captured shortcut and execute its configured action."""

        if not self._enabled:
            return

        action = self._match_shortcut(shortcut)

        if action is not None:
            self._on_action(action)

    def _get_monitored_devices(
        self,
    ) -> list[InputDeviceInfo]:
        """Return currently available keyboard and mouse devices."""

        devices = discover_input_devices()

        return [
            device
            for device in devices
            if classify_device(device).device_class
            in (
                DeviceClass.KEYBOARD,
                DeviceClass.MOUSE,
            )
        ]

    def _handle_devices_changed(
        self,
    ) -> list[InputDeviceInfo]:
        """Handle device changes and recover the selected mouse if needed."""

        devices = self._get_monitored_devices()

        with self._mouse_state_lock:
            if self._selected_mouse is None:
                return devices

            selected_mouse_path = self._selected_mouse.path

            if any(
                device.path == selected_mouse_path
                for device in devices
            ):
                return devices

            self._stop_mouse_interceptor()
            self._selected_mouse = None

            self._start_mouse_discovery()

        return devices

    def set_enabled(
        self,
        enabled: bool,
    ) -> None:
        """Enable or disable shortcut actions."""

        self._enabled = enabled

    def update_configuration(
        self,
        configuration: dict[str, ShortcutConfiguration],
    ) -> None:
        """Update the configured shortcut actions."""

        self._configuration = configuration

        if self._mouse_interceptor is None:
            return

        intercepted_buttons = (
            get_configured_mouse_buttons(
                configuration,
            )
            if self._mouse_interception_enabled
            else set()
        )

        self._mouse_interceptor.update_intercepted_buttons(
            intercepted_buttons,
        )

    def run(self) -> None:
        """Monitor input devices until monitoring is stopped."""

        monitor_devices = self._get_monitored_devices()

        self._start_mouse_discovery()

        context = pyudev.Context()
        device_monitor = pyudev.Monitor.from_netlink(
            context,
        )
        device_monitor.filter_by(
            subsystem="input",
        )
        device_monitor.start()

        for event in read_events_from_devices(
            monitor_devices,
            self._stop_requested,
            device_monitor,
            self._handle_devices_changed,
        ):
            shortcut = self._processor.process_event(
                event,
            )

            if shortcut is not None:
                self._handle_shortcut(
                    shortcut,
                )

        self._stop_mouse_interceptor()
