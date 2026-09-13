import logging
import socket
import threading
from collections.abc import Callable
from typing import Any

from helper.protocol import (
    COMMAND_GRAB_SELECTED_MOUSE,
    COMMAND_HELLO,
    COMMAND_RELEASE_SELECTED_MOUSE,
    COMMAND_SET_INTERCEPTED_MOUSE_BUTTONS,
    COMMAND_SET_MOUSE_INTERCEPTION,
    COMMAND_SET_SHORTCUT_CONFIGURATION,
    COMMAND_START,
    COMMAND_START_CAPTURE,
    COMMAND_STOP,
    COMMAND_STOP_CAPTURE,
    EVENT_HELLO_ACK,
    MAX_COMMAND_SIZE,
    PROTOCOL_VERSION,
    ProtocolError,
    decode_event,
    encode_command,
)

logger = logging.getLogger(__name__)

SOCKET_PATH = "/run/dofus-focus-input.sock"
HANDSHAKE_TIMEOUT = 5.0


class HelperClientError(Exception):
    """Raised when communication with the input helper fails."""


class HelperClient:
    """Communicate with the privileged input helper."""

    def __init__(
        self,
        socket_path: str = SOCKET_PATH,
        on_event: Callable[[dict[str, Any]], None] | None = None,
        on_disconnect: Callable[[], None] | None = None,
    ) -> None:
        self._socket_path = socket_path
        self._on_event = on_event
        self._on_disconnect = on_disconnect

        self._socket: socket.socket | None = None
        self._receive_thread: threading.Thread | None = None

        self._stop_event = threading.Event()
        self._send_lock = threading.Lock()
        self._state_lock = threading.Lock()

        self._connected = False
        self._ready = False

        self._ready_event = threading.Event()

    def connect(self) -> None:
        """Connect to the helper and start the protocol handshake."""
        with self._state_lock:
            if self._connected:
                return

        client = socket.socket(
            socket.AF_UNIX,
            socket.SOCK_STREAM,
        )

        try:
            client.connect(self._socket_path)
        except OSError as error:
            client.close()

            raise HelperClientError(
                "Unable to connect to the input helper.",
            ) from error

        with self._state_lock:
            self._socket = client
            self._connected = True
            self._ready = False

        self._stop_event.clear()
        self._ready_event.clear()

        self._receive_thread = threading.Thread(
            target=self._receive_loop,
            name="HelperClient",
            daemon=True,
        )
        self._receive_thread.start()

        try:
            self._send_message(
                {
                    "type": COMMAND_HELLO,
                    "protocol": PROTOCOL_VERSION,
                },
            )
        except HelperClientError:
            self.disconnect()
            raise

        if not self._ready_event.wait(HANDSHAKE_TIMEOUT):
            self.disconnect()

            raise HelperClientError(
                "Input helper handshake timed out.",
            )

    def disconnect(self) -> None:
        """Disconnect from the helper."""
        self._stop_event.set()
        self._ready_event.clear()

        with self._state_lock:
            client = self._socket
            self._socket = None
            self._connected = False
            self._ready = False

        if client is not None:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

            client.close()

        thread = self._receive_thread

        if (
            thread is not None
            and thread is not threading.current_thread()
        ):
            thread.join()

        self._receive_thread = None

    def start(self) -> None:
        """Start input monitoring in the helper."""
        self._send_command(COMMAND_START)

    def stop(self) -> None:
        """Stop input monitoring in the helper."""
        self._send_command(COMMAND_STOP)

    def start_capture(
        self,
        allowed_mouse_buttons: set[int] | None,
    ) -> None:
        """Start shortcut capture in the helper."""

        self._send_command(
            COMMAND_START_CAPTURE,
            allowed_mouse_buttons=(
                sorted(allowed_mouse_buttons)
                if allowed_mouse_buttons is not None
                else None
            ),
        )

    def stop_capture(self) -> None:
        """Stop shortcut capture in the helper."""
        self._send_command(COMMAND_STOP_CAPTURE)

    def grab_selected_mouse(self) -> None:
        """Grab the currently selected mouse in the helper."""
        self._send_command(COMMAND_GRAB_SELECTED_MOUSE)

    def release_selected_mouse(self) -> None:
        """Release the currently grabbed mouse in the helper."""
        self._send_command(COMMAND_RELEASE_SELECTED_MOUSE)

    def set_mouse_interception(
        self,
        enabled: bool,
    ) -> None:
        """Enable or disable mouse interception."""
        self._send_command(
            COMMAND_SET_MOUSE_INTERCEPTION,
            enabled=enabled,
        )

    def set_intercepted_mouse_buttons(
        self,
        buttons: set[int],
    ) -> None:
        """Set the mouse buttons intercepted by the helper."""
        self._send_command(
            COMMAND_SET_INTERCEPTED_MOUSE_BUTTONS,
            buttons=sorted(buttons),
        )

    def set_shortcut_configuration(
        self,
        configuration: dict,
    ) -> None:
        """Send the shortcut configuration to the input helper."""

        self._send_command(
            COMMAND_SET_SHORTCUT_CONFIGURATION,
            configuration=configuration,
        )

    def is_connected(self) -> bool:
        """Return whether the helper is connected."""
        with self._state_lock:
            return self._connected

    def is_ready(self) -> bool:
        """Return whether the helper handshake has completed."""
        with self._state_lock:
            return self._ready

    def _send_command(
        self,
        command: str,
        **arguments: Any,
    ) -> None:
        """Send one validated command to the helper."""
        if not self.is_ready():
            raise HelperClientError(
                "The input helper is not ready.",
            )

        message = {
            "type": command,
            **arguments,
        }

        self._send_message(message)

    def _send_message(
        self,
        message: dict[str, Any],
    ) -> None:
        """Encode and send one command to the helper."""
        client = self._get_socket()

        if client is None:
            raise HelperClientError(
                "The input helper is not connected.",
            )

        try:
            payload = encode_command(message)

            with self._send_lock:
                client.sendall(payload)

        except ProtocolError as error:
            raise HelperClientError(
                "Invalid command for the input helper.",
            ) from error

        except OSError as error:
            self._handle_disconnect()

            raise HelperClientError(
                "Communication with the input helper failed.",
            ) from error

    def _receive_loop(self) -> None:
        """Receive and dispatch events from the helper."""
        client = self._get_socket()

        if client is None:
            return

        buffer = bytearray()

        try:
            while not self._stop_event.is_set():
                data = client.recv(4096)

                if not data:
                    break

                buffer.extend(data)

                while True:
                    separator = buffer.find(b"\n")

                    if separator == -1:
                        if len(buffer) > MAX_COMMAND_SIZE:
                            raise HelperClientError(
                                "Helper message exceeds maximum size.",
                            )

                        break

                    line = bytes(
                        buffer[:separator + 1],
                    )
                    del buffer[:separator + 1]

                    try:
                        event = decode_event(line)
                    except ProtocolError as error:
                        raise HelperClientError(
                            "Invalid event received from input helper.",
                        ) from error

                    self._handle_event(event)

        except HelperClientError:
            logger.exception(
                "Input helper communication failed.",
            )

        except OSError:
            if not self._stop_event.is_set():
                logger.exception(
                    "Input helper connection failed.",
                )

        finally:
            if not self._stop_event.is_set():
                self._handle_disconnect()

    def _handle_event(
        self,
        event: dict[str, Any],
    ) -> None:
        """Handle one validated event from the helper."""
        if event["type"] == EVENT_HELLO_ACK:
            with self._state_lock:
                self._ready = True

            self._ready_event.set()

            logger.info("Input helper handshake completed.")
            return

        if self._on_event is not None:
            self._on_event(event)

    def _handle_disconnect(self) -> None:
        """Reset the connection after an unexpected disconnect."""
        with self._state_lock:
            if not self._connected:
                return

            self._socket = None
            self._connected = False
            self._ready = False

            self._ready_event.clear()

        logger.error("Input helper disconnected.")

        if self._on_disconnect is not None:
            self._on_disconnect()

    def _get_socket(self) -> socket.socket | None:
        """Return the current helper socket."""
        with self._state_lock:
            return self._socket
