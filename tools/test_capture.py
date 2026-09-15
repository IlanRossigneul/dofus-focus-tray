import threading
import time

from config.paths import SHORTCUTS_FILE
from helper.xkb import Xkb
from shortcuts.service import ShortcutService
from shortcuts.storage import ShortcutStorage


class CaptureTester:
    """Run interactive shortcut capture tests through the real shortcut service."""

    def __init__(
        self,
        calibration: bool,
    ) -> None:
        self._calibration = calibration
        self._stop_event = threading.Event()
        self._service_ready = threading.Event()
        self._capture_done = threading.Event()

        self._xkb = Xkb()
        self._shortcut_service: ShortcutService | None = None
        self._shortcut_thread: threading.Thread | None = None

        self._last_shortcut = None
        self._last_error: Exception | None = None
        self._last_rejection: str | None = None

    def start(self) -> None:
        """Start the XKB resources and shortcut service."""
        self._xkb.load_wayland_keymap()

        configuration = ShortcutStorage(
            SHORTCUTS_FILE,
        ).load()

        self._shortcut_thread = threading.Thread(
            target=self._run_service,
            args=(configuration,),
            name="CaptureTestShortcutThread",
            daemon=True,
        )
        self._shortcut_thread.start()

        if not self._service_ready.wait(5):
            raise RuntimeError(
                "Shortcut service did not become ready.",
            )

        deadline = time.monotonic() + 5

        while (
            self._shortcut_service is None
            or not self._shortcut_service._helper_client.is_ready()
        ):
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "Input helper did not become ready.",
                )

            time.sleep(0.05)

        deadline = time.monotonic() + 5

        while (
            self._shortcut_service is not None
            and self._shortcut_service._selected_mouse is None
        ):
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "Input helper did not select a mouse.",
                )

            time.sleep(0.05)

    def stop(self) -> None:
        """Stop the shortcut service and free the XKB resources."""
        self._stop_event.set()

        if self._shortcut_thread is not None:
            self._shortcut_thread.join()

        self._xkb.close()

    def capture(self) -> None:
        """Capture and display one shortcut."""
        service = self._shortcut_service

        if service is None:
            raise RuntimeError(
                "Shortcut service is not ready.",
            )

        self._last_shortcut = None
        self._last_error = None
        self._last_rejection = None
        self._capture_done.clear()

        allowed_mouse_buttons = set() if self._calibration else None

        service.start_capture(
            allowed_mouse_buttons=allowed_mouse_buttons,
            callback=self._handle_shortcut,
            error_callback=self._handle_error,
            rejected_callback=self._handle_rejection,
        )

        print()
        print("Press a shortcut...")

        try:
            while not self._capture_done.wait(0.1):
                if self._stop_event.is_set():
                    return
        finally:
            service.stop_capture()

        if self._last_shortcut is not None:
            print(
                f"Captured: {self._last_shortcut}",
            )
            return

        if self._last_rejection is not None:
            print(
                f"Rejected: {self._last_rejection}",
            )
            return

        if self._last_error is not None:
            print(
                f"Capture failed: {self._last_error}",
            )

    def _handle_shortcut(
        self,
        shortcut,
    ) -> None:
        """Store and display a captured shortcut."""
        self._last_shortcut = shortcut
        self._capture_done.set()

    def _handle_error(
        self,
        error: Exception,
    ) -> None:
        """Store and display a capture error."""
        self._last_error = error
        self._capture_done.set()

    def _handle_rejection(
        self,
        trigger: str,
    ) -> None:
        """Store and display a rejected mouse trigger."""
        self._last_rejection = trigger
        self._capture_done.set()

    def _run_service(
        self,
        configuration,
    ) -> None:
        """Create and run the shortcut service."""
        self._shortcut_service = ShortcutService(
            xkb=self._xkb,
            configuration=configuration,
            on_action=lambda _action: None,
            stop_requested=self._stop_event.is_set,
        )

        self._service_ready.set()

        self._shortcut_service.run()


def choose_capture_mode() -> bool:
    """Ask which shortcut capture mode should be tested."""
    print("Shortcut capture test")
    print("=====================")
    print("1. Regular shortcuts")
    print("2. Calibration shortcuts")

    while True:
        choice = input("Select mode [1/2]: ").strip()

        if choice == "1":
            return False

        if choice == "2":
            return True

        print("Invalid choice.")


def main() -> int:
    calibration = choose_capture_mode()
    tester = CaptureTester(calibration)

    try:
        tester.start()

        print()
        print("Capture tester ready.")
        print("Each capture accepts exactly one shortcut.")
        print("Press Ctrl+C to stop.")

        while True:
            tester.capture()

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        tester.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
