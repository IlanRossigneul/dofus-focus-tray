import logging
import threading
import time
from collections.abc import Callable
from typing import Any

import evdev

from app.helper_client import HelperClient, HelperClientError
from helper.protocol import (
    EVENT_KEYBOARD_EVENT,
    EVENT_MOUSE_BUTTON_EVENT,
    EVENT_MOUSE_INTERCEPTION_STARTED,
    EVENT_MOUSE_INTERCEPTION_STOPPED,
    EVENT_MOUSE_RELATIVE_EVENT,
    EVENT_MOUSE_SELECTED,
    EVENT_MOUSE_SELECTED_LOST,
    EVENT_SHORTCUT,
)
from helper.xkb import Xkb

from .capture import (
    ShortcutCapture,
    ShortcutCaptureRejected,
    get_configured_mouse_buttons,
)
from .events import ShortcutEvent
from .model import Shortcut
from .storage import ShortcutConfiguration

logger = logging.getLogger(__name__)


class ShortcutService:
    """Monitor input devices and execute configured shortcut actions."""

    def __init__(
        self,
        xkb: Xkb,
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

        self._xkb = xkb

        self._capture_lock = threading.RLock()

        self._capture: ShortcutCapture | None = None
        self._capture_callback: Callable[[Shortcut], None] | None = None
        self._capture_error_callback: Callable[[Exception], None] | None = None
        self._capture_rejected_callback: Callable[[str], None] | None = None

        self._helper_client = HelperClient(
            on_event=self._handle_helper_event,
            on_disconnect=self._handle_helper_disconnect,
        )

        self._selected_mouse: str | None = None
        self._mouse_state_lock = threading.RLock()
        self._mouse_grabbed = False

    def _handle_helper_event(
        self,
        event: dict[str, Any],
    ) -> None:
        """Handle an event received from the input helper."""
        event_type = event["type"]

        if event_type == EVENT_KEYBOARD_EVENT:
            self._handle_helper_keyboard_event(event)
            return

        if event_type == EVENT_SHORTCUT:
            self._handle_helper_shortcut(event)
            return

        if event_type == EVENT_MOUSE_BUTTON_EVENT:
            self._handle_helper_mouse_button_event(event)
            return

        if event_type == EVENT_MOUSE_RELATIVE_EVENT:
            self._handle_helper_mouse_relative_event(event)
            return

        if event_type == EVENT_MOUSE_SELECTED:
            self._handle_helper_mouse_selected(event)
            return

        if event_type == EVENT_MOUSE_SELECTED_LOST:
            self._handle_helper_mouse_selected_lost()
            return

        if event_type == EVENT_MOUSE_INTERCEPTION_STARTED:
            self._handle_helper_mouse_interception_started(event)
            return

        if event_type == EVENT_MOUSE_INTERCEPTION_STOPPED:
            self._handle_helper_mouse_interception_stopped(event)
            return

    def _handle_helper_keyboard_event(
        self,
        event: dict[str, Any],
    ) -> None:
        """Process a keyboard event received during shortcut capture."""

        shortcut_event = ShortcutEvent(
            event_type=evdev.ecodes.EV_KEY,
            event_code=event["code"],
            value=event["value"],
            timestamp=event["timestamp"],
            modifiers=frozenset(event.get("modifiers", [])),
        )

        self._process_capture_event(
            shortcut_event,
        )

    def _handle_helper_mouse_button_event(
        self,
        event: dict[str, Any],
    ) -> None:
        """Process a mouse button event received during shortcut capture."""

        shortcut_event = ShortcutEvent(
            event_type=evdev.ecodes.EV_KEY,
            event_code=event["code"],
            value=event["value"],
            timestamp=event["timestamp"],
        )

        self._process_capture_event(
            shortcut_event,
        )

    def _handle_helper_mouse_relative_event(
        self,
        event: dict[str, Any],
    ) -> None:
        """Ignore mouse relative events for shortcut processing."""

    def _handle_helper_disconnect(self) -> None:
        """Handle an unexpected input helper disconnection."""
        if not self._stop_requested():
            logger.error("Input helper connection lost")

    def _handle_helper_mouse_selected(
        self,
        event: dict[str, Any],
    ) -> None:
        """Store the mouse selected by the input helper."""
        with self._mouse_state_lock:
            self._selected_mouse = event["device_id"]

        self._set_helper_intercepted_mouse_buttons(
            get_configured_mouse_buttons(
                self._configuration,
            )
            if self._mouse_interception_enabled
            else set(),
        )
        self._sync_helper_mouse_interception()

    def _handle_helper_mouse_selected_lost(self) -> None:
        """Clear the selected mouse after it was lost."""
        with self._mouse_state_lock:
            self._selected_mouse = None
            self._mouse_grabbed = False

    def _handle_helper_mouse_interception_started(
        self,
        event: dict[str, Any],
    ) -> None:
        """Handle confirmation that mouse interception started."""

        logger.info(
            "Mouse interception started: device_id=%s",
            event["device_id"],
        )

    def _handle_helper_mouse_interception_stopped(
        self,
        event: dict[str, Any],
    ) -> None:
        """Handle confirmation that mouse interception stopped."""

        logger.info(
            "Mouse interception stopped: device_id=%s",
            event["device_id"],
        )

    def _set_helper_mouse_interception(
        self,
        enabled: bool,
    ) -> None:
        """Request the input helper to enable or disable mouse interception."""

        try:
            self._helper_client.set_mouse_interception(
                enabled,
            )
        except HelperClientError:
            logger.error(
                "Unable to update mouse interception through input helper",
            )

    def _set_helper_intercepted_mouse_buttons(
        self,
        buttons: set[int],
    ) -> None:
        """Request the input helper to update intercepted mouse buttons."""

        try:
            self._helper_client.set_intercepted_mouse_buttons(
                buttons,
            )
        except HelperClientError:
            logger.error(
                "Unable to update intercepted mouse buttons through input helper",
            )

    def _sync_helper_mouse_interception(self) -> None:
        """Synchronize mouse grab and interception with the current state."""

        if (
            self._calibrated
            and self._selected_mouse is not None
            and self._mouse_interception_enabled
        ):
            if not self._mouse_grabbed:
                try:
                    self._helper_client.grab_selected_mouse()
                except HelperClientError:
                    logger.error(
                        "Unable to grab selected mouse through input helper",
                    )
                    return

                self._mouse_grabbed = True

            self._set_helper_intercepted_mouse_buttons(
                get_configured_mouse_buttons(
                    self._configuration,
                ),
            )
            self._set_helper_mouse_interception(True)
            return

        self._set_helper_mouse_interception(False)
        self._set_helper_intercepted_mouse_buttons(set())

        if self._mouse_grabbed:
            try:
                self._helper_client.release_selected_mouse()
            except HelperClientError:
                logger.error(
                    "Unable to release selected mouse through input helper",
                )
                return

            self._mouse_grabbed = False

    def set_calibration_valid(
        self,
        calibrated: bool,
    ) -> None:
        """Update the calibration state and synchronize mouse interception."""

        if self._calibrated == calibrated:
            return

        self._calibrated = calibrated
        self._sync_helper_mouse_interception()

    def set_mouse_interception_enabled(
        self,
        enabled: bool,
    ) -> None:
        """Enable or disable interception of configured mouse buttons."""

        if self._mouse_interception_enabled == enabled:
            return

        self._mouse_interception_enabled = enabled
        self._sync_helper_mouse_interception()

    def start_capture(
        self,
        allowed_mouse_buttons: set[int] | None,
        callback: Callable[[Shortcut], None],
        error_callback: Callable[[Exception], None],
        rejected_callback: Callable[[str], None],
    ) -> None:
        """Start capturing the next valid shortcut from helper input events."""

        with self._capture_lock:
            if self._capture is not None:
                return

            self._capture = ShortcutCapture(
                self._xkb,
                allowed_mouse_buttons=allowed_mouse_buttons,
            )
            self._capture_callback = callback
            self._capture_error_callback = error_callback
            self._capture_rejected_callback = rejected_callback

        try:
            self._helper_client.start_capture(
                allowed_mouse_buttons,
            )
        except HelperClientError as error:
            with self._capture_lock:
                self._capture = None
                self._capture_callback = None
                self._capture_error_callback = None
                self._capture_rejected_callback = None

            error_callback(error)

    def stop_capture(self) -> None:
        """Stop the current shortcut capture."""

        try:
            self._helper_client.stop_capture()
        except HelperClientError:
            logger.warning(
                "Unable to stop input helper capture cleanly",
            )
            return

        with self._capture_lock:
            self._capture = None
            self._capture_callback = None
            self._capture_error_callback = None
            self._capture_rejected_callback = None

        self._sync_helper_mouse_interception()

    def _process_capture_event(
        self,
        event: ShortcutEvent,
    ) -> bool:
        """Process an input event through the active shortcut capture."""

        with self._capture_lock:
            capture = self._capture

            if capture is None:
                return False

            try:
                shortcut = capture.process_event(
                    event,
                )
            except ShortcutCaptureRejected as error:
                callback = self._capture_rejected_callback

                if callback is None:
                    return True

                callback_argument = error.trigger
            except Exception as error:  # noqa: BLE001
                callback = self._capture_error_callback

                self._capture = None
                self._capture_callback = None
                self._capture_error_callback = None
                self._capture_rejected_callback = None

                if callback is None:
                    return True

                callback_argument = error
            else:
                if shortcut is None:
                    return True

                callback = self._capture_callback

                self._capture = None
                self._capture_callback = None
                self._capture_error_callback = None
                self._capture_rejected_callback = None

                if callback is None:
                    return True

                callback_argument = shortcut

        callback(callback_argument)
        return True

    def _handle_helper_shortcut(
        self,
        event: dict[str, Any],
    ) -> None:
        """Handle an authorized shortcut action from the input helper."""

        if not self._enabled:
            return

        self._on_action(event["action"])

    def set_enabled(
        self,
        enabled: bool,
    ) -> None:
        """Enable or disable shortcut actions."""

        self._enabled = enabled

    def _serialize_configuration(
        self,
        configuration: dict[str, ShortcutConfiguration],
    ) -> dict:
        """Convert shortcut configurations to the helper protocol format."""

        return {
            action: {
                "primary": self._serialize_shortcut(
                    action_configuration.primary,
                ),
                "alternate": self._serialize_shortcut(
                    action_configuration.alternate,
                ),
            }
            for action, action_configuration in configuration.items()
        }

    @staticmethod
    def _serialize_shortcut(
        shortcut: Shortcut | None,
    ) -> dict | None:
        """Convert a shortcut to the helper protocol format."""

        if shortcut is None:
            return None

        return {
            "trigger": shortcut.trigger,
            "modifiers": sorted(shortcut.modifiers),
        }

    def update_configuration(
        self,
        configuration: dict[str, ShortcutConfiguration],
    ) -> None:
        """Update the configured shortcut actions."""

        self._configuration = configuration

        try:
            self._helper_client.set_shortcut_configuration(
                self._serialize_configuration(
                    configuration,
                ),
            )
        except HelperClientError:
            logger.error(
                "Unable to update shortcut configuration through input helper",
            )

        intercepted_buttons = (
            get_configured_mouse_buttons(
                configuration,
            )
            if self._mouse_interception_enabled
            else set()
        )

        self._set_helper_intercepted_mouse_buttons(
            intercepted_buttons,
        )

    def run(self) -> None:
        """Keep the input helper connection active until monitoring is stopped."""

        try:
            self._helper_client.connect()
            self._helper_client.start()

            self._helper_client.set_shortcut_configuration(
                self._serialize_configuration(
                    self._configuration,
                ),
            )

            while not self._stop_requested():
                time.sleep(0.1)

        finally:
            try:
                self._helper_client.stop()
            except HelperClientError:
                logger.warning("Unable to stop input helper cleanly")

            self._helper_client.disconnect()
