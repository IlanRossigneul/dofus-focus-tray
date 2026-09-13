import threading

from app.helper_client import HelperClient

mouse_selected_event = threading.Event()


def handle_event(event: dict) -> None:
    """Display an event received from the input helper."""

    event_type = event["type"]

    if event_type == "mouse_selected":
        mouse_selected_event.set()
        return

    if event_type in {
        "keyboard_event",
        "mouse_relative_event",
        "mouse_button_event",
    }:
        print(event)


def main() -> int:
    """Inspect keyboard and mouse input events from the input helper."""

    client = HelperClient(on_event=handle_event)

    try:
        client.connect()
        client.start()

        print("Connected to input helper.")
        print("Waiting for mouse selection...")

        if not mouse_selected_event.wait():
            return 1

        print("Mouse selected.")
        print("Starting input capture.")
        client.start_capture(None)

        print("Monitoring input events. Press Ctrl+C to stop.")

        while True:
            try:
                input()
            except EOFError:
                break

    except KeyboardInterrupt:
        print("\nStopped.")

    finally:
        if client.is_ready():
            client.stop_capture()
            client.stop()

        client.disconnect()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
