import threading
import time

import evdev

from app.helper_client import HelperClient, HelperClientError
from config.paths import SHORTCUTS_FILE
from helper.protocol import (
    EVENT_KEYBOARD_SELECTED,
    EVENT_KEYBOARD_SELECTED_LOST,
    EVENT_MOUSE_INTERCEPTION_STARTED,
    EVENT_MOUSE_INTERCEPTION_STOPPED,
    EVENT_MOUSE_SELECTED,
    EVENT_MOUSE_SELECTED_LOST,
)
from shortcuts.capture import get_configured_mouse_buttons
from shortcuts.storage import ShortcutStorage

STEP_DELAY = 1.0
SELECTION_TIMEOUT = 10.0
LOSS_TIMEOUT = 5.0
LOSS_RETRIES = 10
LOSS_RETRY_DELAY = 1.0
INTERCEPTION_TIMEOUT = 10.0
STOP_DELAY = 1.0


class HotplugTester:
    """Validate keyboard and mouse hotplug through the input helper."""

    def __init__(self) -> None:
        self._selected_mouse_event = threading.Event()
        self._selected_mouse_lost_event = threading.Event()
        self._keyboard_selected_event = threading.Event()
        self._keyboard_selected_lost_event = threading.Event()
        self._interception_started_event = threading.Event()
        self._interception_stopped_event = threading.Event()

        self._selected_mouse_ids: list[str] = []
        self._keyboard_selected_ids: list[str] = []

        self._mouse_grabbed = False
        self._interception_active = False

        self._client = HelperClient(
            on_event=self._handle_event,
        )

    def _handle_event(self, event: dict) -> None:
        """Handle events required by the hotplug tests."""

        event_type = event["type"]

        if event_type == EVENT_MOUSE_SELECTED:
            self._selected_mouse_ids.append(
                event["device_id"],
            )
            self._selected_mouse_event.set()
            return

        if event_type == EVENT_MOUSE_SELECTED_LOST:
            self._selected_mouse_lost_event.set()
            return

        if event_type == EVENT_KEYBOARD_SELECTED:
            self._keyboard_selected_ids.append(
                event["device_id"],
            )
            self._keyboard_selected_event.set()
            return

        if event_type == EVENT_KEYBOARD_SELECTED_LOST:
            self._keyboard_selected_lost_event.set()
            return

        if event_type == EVENT_MOUSE_INTERCEPTION_STARTED:
            self._interception_active = True
            self._interception_started_event.set()
            return

        if event_type == EVENT_MOUSE_INTERCEPTION_STOPPED:
            self._interception_active = False
            self._interception_stopped_event.set()

    def _wait_for_selection(
        self,
        selected_ids: list[str],
        selection_event: threading.Event,
        selection_number: int,
        device_name: str,
    ) -> str:
        """Wait for the requested input device selection."""

        deadline = time.monotonic() + SELECTION_TIMEOUT

        while len(selected_ids) < selection_number:
            remaining = deadline - time.monotonic()

            if remaining <= 0:
                raise RuntimeError(
                    f"Timed out waiting for {device_name} selection.",
                )

            selection_event.wait(remaining)
            selection_event.clear()

        return selected_ids[selection_number - 1]

    def _wait_for_mouse_loss(self) -> None:
        """Wait for the selected mouse loss event."""

        if not self._selected_mouse_lost_event.wait(
            LOSS_TIMEOUT,
        ):
            raise RuntimeError(
                "Timed out waiting for selected mouse loss.",
            )

        self._selected_mouse_lost_event.clear()

    def _wait_for_keyboard_loss(self) -> None:
        """Wait for the selected keyboard loss event."""

        for attempt in range(1, LOSS_RETRIES + 1):
            if self._keyboard_selected_lost_event.wait(
                LOSS_TIMEOUT,
            ):
                self._keyboard_selected_lost_event.clear()
                return

            if attempt < LOSS_RETRIES:
                print(
                    f"Keyboard loss not detected "
                    f"(attempt {attempt}/{LOSS_RETRIES}), "
                    "retrying...",
                )
                time.sleep(LOSS_RETRY_DELAY)

        raise RuntimeError(
            "Timed out waiting for selected keyboard loss.",
        )

    def _wait_for_interception_started(self) -> None:
        """Wait for mouse interception to start."""

        if not self._interception_started_event.wait(
            INTERCEPTION_TIMEOUT,
        ):
            raise RuntimeError(
                "Timed out waiting for mouse interception to start.",
            )

        self._interception_started_event.clear()

    def _wait_for_interception_stopped(self) -> None:
        """Wait for mouse interception to stop."""

        if not self._interception_stopped_event.wait(
            INTERCEPTION_TIMEOUT,
        ):
            raise RuntimeError(
                "Timed out waiting for mouse interception to stop.",
            )

        self._interception_stopped_event.clear()

    def _get_intercepted_mouse_buttons(self) -> set[int]:
        """Return the configured mouse buttons used for interception."""

        configuration = ShortcutStorage(
            SHORTCUTS_FILE,
        ).load()

        return get_configured_mouse_buttons(configuration)

    def _format_mouse_buttons(self, buttons: set[int]) -> str:
        """Format intercepted mouse buttons for display."""

        return ", ".join(
            evdev.ecodes.BTN.get(
                button,
                str(button),
            )
            for button in sorted(buttons)
        )

    def _start_mouse_interception(self) -> None:
        """Grab the selected mouse and start interception."""

        buttons = self._get_intercepted_mouse_buttons()

        if not buttons:
            raise RuntimeError(
                "No mouse buttons are configured for interception.",
            )

        print("Grabbing the selected mouse...")
        self._client.grab_selected_mouse()
        self._mouse_grabbed = True
        print("☑ Mouse grabbed")

        print(
            "Starting mouse interception for: "
            f"{self._format_mouse_buttons(buttons)}...",
        )
        self._client.set_intercepted_mouse_buttons(buttons)
        self._client.set_mouse_interception(True)
        self._wait_for_interception_started()
        print("☑ Mouse interception started")

    def _stop_mouse_interception(self) -> None:
        """Stop mouse interception if it is active."""

        if not self._interception_active:
            return

        self._client.set_mouse_interception(False)
        self._wait_for_interception_stopped()
        print("☑ Mouse interception stopped")

    def _release_selected_mouse(self) -> None:
        """Release the selected mouse if it is grabbed."""

        if not self._mouse_grabbed:
            return

        self._client.release_selected_mouse()
        self._mouse_grabbed = False

    def _start_mouse_interception_again(self) -> None:
        """Restart mouse interception after mouse reselection."""

        buttons = self._get_intercepted_mouse_buttons()

        if not buttons:
            raise RuntimeError(
                "No mouse buttons are configured for interception.",
            )

        print(
            "Starting mouse interception again for: "
            f"{self._format_mouse_buttons(buttons)}...",
        )
        self._client.grab_selected_mouse()
        self._mouse_grabbed = True
        self._client.set_intercepted_mouse_buttons(buttons)
        self._client.set_mouse_interception(True)
        self._wait_for_interception_started()
        print("☑ Mouse interception started again")

    def _test_mouse(self, grab: bool) -> None:
        """Run the selected mouse hotplug test."""

        print("Dofus Focus — Mouse hotplug test")
        print()

        print("Move the mouse to trigger its selection.")
        first_device_id = self._wait_for_selection(
            self._selected_mouse_ids,
            self._selected_mouse_event,
            1,
            "mouse",
        )
        print("☑ Mouse detected and selected")

        if grab:
            print()
            self._start_mouse_interception()

        print()
        print("Unplug the selected mouse, then press ENTER.")
        input()

        self._wait_for_mouse_loss()

        if grab:
            self._stop_mouse_interception()

        print("☑ Mouse removed from helper state")

        time.sleep(STEP_DELAY)

        print()
        print("Plug the mouse back in, then press ENTER.")
        input()

        print()
        print("Move the mouse to trigger its reselection.")
        second_device_id = self._wait_for_selection(
            self._selected_mouse_ids,
            self._selected_mouse_event,
            2,
            "mouse",
        )

        if second_device_id == first_device_id:
            raise RuntimeError(
                "Mouse was selected again with the same device_id.",
            )

        print("☑ Mouse detected and selected again")

        if grab:
            self._start_mouse_interception_again()

        print()
        print("☑ Mouse hotplug test passed.")

    def _test_keyboard(self) -> None:
        """Run the keyboard hotplug test."""

        print("Dofus Focus — Keyboard hotplug test")
        print()

        print("Press a key to trigger keyboard selection.")
        first_device_id = self._wait_for_selection(
            self._keyboard_selected_ids,
            self._keyboard_selected_event,
            1,
            "keyboard",
        )
        print("☑ Keyboard detected and selected")

        print()
        print("Unplug the selected keyboard.")
        self._wait_for_keyboard_loss()
        print("☑ Keyboard removed from helper state")

        time.sleep(STEP_DELAY)

        print()
        print("Plug the keyboard back in, then press ENTER.")
        input()

        print()
        print("Press a key on the reconnected keyboard.")
        second_device_id = self._wait_for_selection(
            self._keyboard_selected_ids,
            self._keyboard_selected_event,
            2,
            "keyboard",
        )

        if second_device_id == first_device_id:
            raise RuntimeError(
                "Keyboard was selected again with the same device_id.",
            )

        print("☑ Keyboard detected and selected again")

        print()
        print("☑ Keyboard hotplug test passed.")

    def start(self) -> None:
        """Run the interactive hotplug test."""

        try:
            print("Dofus Focus — Input hotplug test")
            print()

            print("Connecting to input helper...")
            self._client.connect()
            print("☑ Connected to input helper")

            print()
            print("Starting input monitoring...")
            self._client.start()
            print("☑ Input monitoring started")

            print()
            print("1. Mouse")
            print("2. Keyboard")
            print()
            choice = input("Select input device: ").strip()

            if choice == "1":
                print()
                print("1. Regular")
                print("2. Grabbed")
                print()
                mode = input("Select test mode: ").strip()

                if mode == "1":
                    self._test_mouse(grab=False)
                elif mode == "2":
                    self._test_mouse(grab=True)
                else:
                    raise RuntimeError("Invalid test mode.")

            elif choice == "2":
                self._test_keyboard()

            else:
                raise RuntimeError("Invalid input device.")

        finally:
            if self._client.is_ready():
                try:
                    self._stop_mouse_interception()
                    self._release_selected_mouse()
                    self._client.stop()
                    time.sleep(STOP_DELAY)
                except HelperClientError:
                    pass

            self._client.disconnect()


def main() -> int:
    """Run the input hotplug test."""

    tester = HotplugTester()

    try:
        tester.start()
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0
    except (HelperClientError, RuntimeError) as error:
        print(f"\n✗ Input hotplug test failed: {error}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
