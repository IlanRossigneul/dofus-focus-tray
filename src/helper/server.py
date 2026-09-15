import logging
import socket
import struct
from typing import Any

from .protocol import (
    MAX_COMMAND_SIZE,
    ProtocolError,
    decode_command,
    encode_event,
)

logger = logging.getLogger(__name__)


class ClientDisconnected(Exception):
    """Raised when the tray client disconnects unexpectedly."""


class HelperServer:
    """Handle the IPC connection between the tray and the helper."""

    def __init__(self, client_uid: int) -> None:
        self._client_uid = client_uid
        self._client: socket.socket | None = None
        self._receive_buffer = bytearray()

    def _get_peer_uid(self, client: socket.socket) -> int:
        """Return the peer UID from the connected Unix socket."""
        credentials = client.getsockopt(
            socket.SOL_SOCKET,
            socket.SO_PEERCRED,
            struct.calcsize("3i"),
        )

        _, uid, _ = struct.unpack("3i", credentials)
        return uid

    def accept_client(self, server_socket: socket.socket) -> bool:
        """Accept one authorized IPC client."""
        client, _ = server_socket.accept()

        if self._client is not None:
            client.close()
            return False

        try:
            peer_uid = self._get_peer_uid(client)

            if peer_uid != self._client_uid:
                return False

            self._receive_buffer.clear()
            self._client = client
            return True

        finally:
            if self._client is not client:
                client.close()

    def receive_command(self) -> dict[str, Any] | None:
        """Receive and decode one command from the connected client."""
        if self._client is None:
            return None

        while True:
            separator = self._receive_buffer.find(b"\n")

            if separator != -1:
                line = bytes(self._receive_buffer[: separator + 1])
                del self._receive_buffer[: separator + 1]
                return decode_command(line)

            try:
                chunk = self._client.recv(4096)
            except OSError as error:
                self.close_client()
                raise ClientDisconnected from error

            if not chunk:
                self.close_client()
                return None

            self._receive_buffer.extend(chunk)

            if len(self._receive_buffer) > MAX_COMMAND_SIZE:
                raise ProtocolError("Message exceeds maximum size.")

    def has_pending_command(self) -> bool:
        """Return whether a complete command is already buffered."""
        return b"\n" in self._receive_buffer

    def send_event(self, event: dict[str, Any]) -> bool:
        """Encode and send one event to the connected client."""
        if self._client is None:
            raise ClientDisconnected

        try:
            self._client.sendall(encode_event(event))
        except OSError as error:
            logger.exception("Failed to send event to tray.")
            self.close_client()
            raise ClientDisconnected from error

        return True

    def close_client(self) -> None:
        """Close the connected client and reset the connection state."""
        if self._client is None:
            return

        self._client.close()
        self._client = None
        self._receive_buffer.clear()

    def get_client_socket(self) -> socket.socket | None:
        """Return the connected client socket."""
        return self._client

    def has_client(self) -> bool:
        """Return whether a client is currently connected."""
        return self._client is not None
