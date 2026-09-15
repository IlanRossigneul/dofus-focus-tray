import threading

import evdev

from app.helper_client import HelperClient, HelperClientError
from config.paths import SHORTCUTS_FILE
from helper.protocol import (
    EVENT_ERROR,
    EVENT_MOUSE_INTERCEPTION_STARTED,
    EVENT_MOUSE_INTERCEPTION_STOPPED,
    EVENT_MOUSE_SELECTED,
    EVENT_SHORTCUT,
)
from shortcuts.capture import get_configured_mouse_buttons
from shortcuts.storage import ShortcutStorage

SELECTION_TIMEOUT = 5
GRAB_DELAY = 10
TEST_DURATION = 60


class MouseGrabTester:
    """Test mouse selection, grabbing, and mouse button interception."""

    def __init__(self) -> None:
        self._mouse_selected = threading.Event()
        self._interception_started = threading.Event()
        self._interception_stopped = threading.Event()
        self._stop_requested = threading.Event()

        self._selected_mouse_id: str | None = None

        self._mouse_grabbed = False
        self._interception_active = False

        self._intercepted_buttons: set[int] = set()
        self._mouse_actions: dict[str, tuple[str, int]] = {}
        self._shortcut_configuration: dict = {}
        self._helper_error: str | None = None

        self._client = HelperClient(
            on_event=self._handle_event,
            on_disconnect=self._handle_disconnect,
        )

    def start(self) -> None:
        """Connect to the input helper and start device monitoring."""
        self._client.connect()
        self._client.start()

    def stop(self) -> None:
        """Stop interception, release the mouse, and disconnect."""
        if self._client.is_ready():
            if self._interception_active:
                try:
                    self._client.set_mouse_interception(False)
                except HelperClientError:
                    print(
                        "WARNING: Unable to stop mouse interception cleanly.",
                    )
                self._interception_stopped.wait(2)
                self._interception_active = False

            if self._mouse_grabbed:
                try:
                    self._client.release_selected_mouse()
                except HelperClientError:
                    print(
                        "WARNING: Unable to release mouse cleanly.",
                    )
                self._mouse_grabbed = False

            try:
                self._client.stop()
            except HelperClientError:
                print(
                    "WARNING: Unable to stop input helper cleanly.",
                )

        self._client.disconnect()

    def wait_for_mouse(self) -> bool:
        """Wait for the helper to select a mouse from real input activity."""
        print(
            f"Move the mouse within the next {SELECTION_TIMEOUT} seconds...",
        )

        if not self._mouse_selected.wait(SELECTION_TIMEOUT):
            print("ERROR: No mouse activity detected.")
            return False

        device_id = self._selected_mouse_id
        if device_id is None:
            print("ERROR: Mouse selection did not provide a device ID.")
            return False

        print(f"Selected mouse device ID: {device_id}")
        return True

    def load_configuration(self) -> None:
        """Load configured mouse shortcut buttons."""
        configuration = ShortcutStorage(SHORTCUTS_FILE).load()

        self._shortcut_configuration = {
            action: {
                "primary": (
                    {
                        "trigger": shortcut.primary.trigger,
                        "modifiers": sorted(shortcut.primary.modifiers),
                    }
                    if shortcut.primary is not None
                    else None
                ),
                "alternate": (
                    {
                        "trigger": shortcut.alternate.trigger,
                        "modifiers": sorted(shortcut.alternate.modifiers),
                    }
                    if shortcut.alternate is not None
                    else None
                ),
            }
            for action, shortcut in configuration.items()
        }

        self._intercepted_buttons = get_configured_mouse_buttons(
            configuration,
        )

        self._mouse_actions.clear()

        for action, action_configuration in configuration.items():
            for shortcut in (
                action_configuration.primary,
                action_configuration.alternate,
            ):
                if shortcut is None or shortcut.modifiers:
                    continue

                code = evdev.ecodes.ecodes.get(shortcut.trigger)
                if code is None or code not in self._intercepted_buttons:
                    continue

                self._mouse_actions[action] = (
                    shortcut.trigger,
                    code,
                )

        if not self._intercepted_buttons:
            print("Configured mouse buttons: none")
            return

        print("Configured mouse buttons:")
        for button in sorted(self._intercepted_buttons):
            name = evdev.ecodes.BTN.get(button, str(button))
            print(f"  {name} ({button})")

    def wait_before_grab(self) -> bool:
        """Wait before grabbing the selected mouse."""
        print(
            f"Waiting {GRAB_DELAY} seconds before grabbing the mouse...",
        )
        return not self._stop_requested.wait(GRAB_DELAY)

    def grab_selected_mouse(self) -> bool:
        """Request the helper to grab the selected mouse."""
        print("Grabbing mouse...", flush=True)

        try:
            self._client.grab_selected_mouse()
        except HelperClientError as error:
            print(f"ERROR: Unable to grab mouse: {error}")
            return False

        self._mouse_grabbed = True
        print("MOUSE GRABBED", flush=True)
        return True

    def start_interception(self) -> bool:
        """Start mouse interception in the helper."""
        print("Starting mouse interception...", flush=True)

        try:
            self._client.set_shortcut_configuration(
                self._shortcut_configuration,
            )
            self._client.set_intercepted_mouse_buttons(
                self._intercepted_buttons,
            )
            self._client.set_mouse_interception(True)
        except HelperClientError as error:
            print(f"ERROR: Unable to start mouse interception: {error}")
            return False

        if not self._interception_started.wait(SELECTION_TIMEOUT):
            raise RuntimeError(
                "Timed out waiting for mouse interception to start.",
            )

        if self._helper_error is not None:
            print(
                f"ERROR: Mouse interception failed: {self._helper_error}",
            )
            return False

        self._interception_active = True

        print("MOUSE INTERCEPTION STARTED", flush=True)
        print("Press one of the configured mouse buttons.")
        print("Intercepted buttons will be displayed below.")
        print(f"Testing for {TEST_DURATION} seconds...")

        return True

    def run_test(self) -> None:
        """Keep mouse interception active for the test duration."""
        self._stop_requested.wait(TEST_DURATION)

    def _handle_event(self, event: dict) -> None:
        """Handle events received from the input helper."""
        event_type = event["type"]

        if event_type == EVENT_MOUSE_SELECTED:
            self._selected_mouse_id = event["device_id"]
            self._mouse_selected.set()
            return

        if event_type == EVENT_MOUSE_INTERCEPTION_STARTED:
            self._interception_started.set()
            return

        if event_type == EVENT_MOUSE_INTERCEPTION_STOPPED:
            self._interception_active = False
            self._interception_stopped.set()
            return

        if event_type == EVENT_ERROR:
            print(f"HELPER ERROR: {event}")
            self._helper_error = event.get(
                "message",
                "Unknown helper error",
            )
            self._interception_started.set()
            return

        if event_type == EVENT_SHORTCUT:
            self._handle_shortcut_event(event)

    def _handle_shortcut_event(self, event: dict) -> None:
        """Display the mouse button associated with an intercepted action."""
        action = event["action"]
        mouse_action = self._mouse_actions.get(action)

        if mouse_action is None:
            print(
                f"INTERCEPTED: action={action}",
                flush=True,
            )
            return

        name, code = mouse_action
        print(
            f"INTERCEPTED: {name} ({code}) -> {action}",
            flush=True,
        )

    def _handle_disconnect(self) -> None:
        """Handle an unexpected helper disconnection."""
        if self._stop_requested.is_set():
            return

        self._helper_error = "Input helper connection lost."
        self._stop_requested.set()
        self._mouse_selected.set()
        self._interception_started.set()

    def request_stop(self) -> None:
        """Request termination of the test."""
        self._stop_requested.set()


def main() -> None:
    tester = MouseGrabTester()

    try:
        tester.start()

        if not tester.wait_for_mouse():
            return

        tester.load_configuration()

        if not tester.wait_before_grab():
            return

        if not tester.grab_selected_mouse():
            return

        if not tester.start_interception():
            return

        tester.run_test()

    except KeyboardInterrupt:
        print("\nStopping test...")

    finally:
        tester.request_stop()
        tester.stop()

        if tester._interception_stopped.wait(2):
            print("MOUSE INTERCEPTION STOPPED")

        print("Mouse test stopped.")


if __name__ == "__main__":
    main()
