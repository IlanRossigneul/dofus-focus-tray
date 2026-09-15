import json
import socket
import struct
from unittest.mock import MagicMock

import pytest

from helper.protocol import (
    COMMAND_START,
    EVENT_ERROR,
    ProtocolError,
)
from helper.server import ClientDisconnected, HelperServer

CLIENT_UID = 1000


def create_listener(tmp_path):
    socket_path = tmp_path / "helper.sock"

    server_socket = socket.socket(
        socket.AF_UNIX,
        socket.SOCK_STREAM,
    )
    server_socket.bind(str(socket_path))
    server_socket.listen(5)

    return server_socket, socket_path


def connect_client(socket_path):
    client_socket = socket.socket(
        socket.AF_UNIX,
        socket.SOCK_STREAM,
    )
    client_socket.connect(str(socket_path))
    return client_socket


def test_server_starts_without_client():
    server = HelperServer(CLIENT_UID)

    assert not server.has_client()
    assert server.get_client_socket() is None


def test_authorized_client_is_accepted(tmp_path):
    server = HelperServer(CLIENT_UID)
    server_socket, socket_path = create_listener(tmp_path)
    client_socket = connect_client(socket_path)

    try:
        server._get_peer_uid = lambda client: CLIENT_UID

        accepted = server.accept_client(server_socket)

        assert accepted
        assert server.has_client()
        assert server.get_client_socket() is not None
    finally:
        server.close_client()
        client_socket.close()
        server_socket.close()


def test_unauthorized_client_is_rejected(tmp_path):
    server = HelperServer(CLIENT_UID)
    server_socket, socket_path = create_listener(tmp_path)
    client_socket = connect_client(socket_path)

    try:
        server._get_peer_uid = lambda client: CLIENT_UID + 1

        accepted = server.accept_client(server_socket)

        assert not accepted
        assert not server.has_client()
        assert server.get_client_socket() is None
    finally:
        server.close_client()
        client_socket.close()
        server_socket.close()


def test_second_client_is_rejected(tmp_path):
    server = HelperServer(CLIENT_UID)
    server_socket, socket_path = create_listener(tmp_path)

    first_client = connect_client(socket_path)
    try:
        server._get_peer_uid = lambda client: CLIENT_UID

        assert server.accept_client(server_socket)
        assert server.has_client()

        second_client = connect_client(socket_path)

        try:
            accepted = server.accept_client(server_socket)

            assert not accepted
            assert server.get_client_socket() is not None
        finally:
            second_client.close()
    finally:
        server.close_client()
        first_client.close()
        server_socket.close()


def test_new_client_can_connect_after_previous_client_closes(tmp_path):
    server = HelperServer(CLIENT_UID)
    server_socket, socket_path = create_listener(tmp_path)

    first_client = connect_client(socket_path)

    try:
        server._get_peer_uid = lambda client: CLIENT_UID

        assert server.accept_client(server_socket)
        assert server.has_client()

        server.close_client()

        second_client = connect_client(socket_path)

        try:
            assert server.accept_client(server_socket)
            assert server.has_client()
        finally:
            server.close_client()
            second_client.close()
    finally:
        first_client.close()
        server_socket.close()


def test_receive_command_returns_decoded_command(tmp_path):
    server = HelperServer(CLIENT_UID)
    server_socket, socket_path = create_listener(tmp_path)
    client_socket = connect_client(socket_path)

    try:
        server._get_peer_uid = lambda client: CLIENT_UID
        assert server.accept_client(server_socket)

        client_socket.sendall(b'{"type":"start"}\n')

        assert server.receive_command() == {
            "type": COMMAND_START,
        }
    finally:
        server.close_client()
        client_socket.close()
        server_socket.close()


def test_receive_command_handles_fragmented_message(tmp_path):
    server = HelperServer(CLIENT_UID)
    server_socket, socket_path = create_listener(tmp_path)
    client_socket = connect_client(socket_path)

    try:
        server._get_peer_uid = lambda client: CLIENT_UID
        assert server.accept_client(server_socket)

        client_socket.sendall(b'{"type":"sta')
        client_socket.sendall(b'rt"}\n')

        assert server.receive_command() == {
            "type": COMMAND_START,
        }
    finally:
        server.close_client()
        client_socket.close()
        server_socket.close()


def test_receive_command_handles_multiple_commands(tmp_path):
    server = HelperServer(CLIENT_UID)
    server_socket, socket_path = create_listener(tmp_path)
    client_socket = connect_client(socket_path)

    try:
        server._get_peer_uid = lambda client: CLIENT_UID
        assert server.accept_client(server_socket)

        client_socket.sendall(b'{"type":"start"}\n{"type":"stop"}\n')

        assert server.receive_command() == {
            "type": "start",
        }

        assert server.receive_command() == {
            "type": "stop",
        }
    finally:
        server.close_client()
        client_socket.close()
        server_socket.close()


def test_receive_command_preserves_partial_next_command(tmp_path):
    server = HelperServer(CLIENT_UID)
    server_socket, socket_path = create_listener(tmp_path)
    client_socket = connect_client(socket_path)

    try:
        server._get_peer_uid = lambda client: CLIENT_UID
        assert server.accept_client(server_socket)

        client_socket.sendall(b'{"type":"start"}\n{"type":"sto')

        assert server.receive_command() == {
            "type": "start",
        }

        client_socket.sendall(b'p"}\n')

        assert server.receive_command() == {
            "type": "stop",
        }
    finally:
        server.close_client()
        client_socket.close()
        server_socket.close()


def test_receive_command_returns_none_on_disconnect(tmp_path):
    server = HelperServer(CLIENT_UID)
    server_socket, socket_path = create_listener(tmp_path)
    client_socket = connect_client(socket_path)

    try:
        server._get_peer_uid = lambda client: CLIENT_UID
        assert server.accept_client(server_socket)

        client_socket.close()

        assert server.receive_command() is None
        assert not server.has_client()
    finally:
        server.close_client()
        server_socket.close()


def test_receive_command_rejects_invalid_message(tmp_path):
    server = HelperServer(CLIENT_UID)
    server_socket, socket_path = create_listener(tmp_path)
    client_socket = connect_client(socket_path)

    try:
        server._get_peer_uid = lambda client: CLIENT_UID
        assert server.accept_client(server_socket)

        client_socket.sendall(b'{"type":start}\n')

        with pytest.raises(ProtocolError):
            server.receive_command()
    finally:
        server.close_client()
        client_socket.close()
        server_socket.close()


def test_receive_command_rejects_oversized_message(tmp_path):
    server = HelperServer(CLIENT_UID)
    server_socket, socket_path = create_listener(tmp_path)
    client_socket = connect_client(socket_path)

    try:
        server._get_peer_uid = lambda client: CLIENT_UID
        assert server.accept_client(server_socket)

        client_socket.sendall(b"a" * (64 * 1024 + 1))

        with pytest.raises(ProtocolError):
            server.receive_command()
    finally:
        server.close_client()
        client_socket.close()
        server_socket.close()


def test_receive_command_returns_none_without_client():
    server = HelperServer(CLIENT_UID)

    assert server.receive_command() is None


def test_send_event_raises_without_client():
    server = HelperServer(CLIENT_UID)

    with pytest.raises(ClientDisconnected):
        server.send_event(
            {
                "type": EVENT_ERROR,
                "code": "invalid_message",
                "message": "Test.",
            }
        )


def test_send_event_sends_encoded_event(tmp_path):
    server = HelperServer(CLIENT_UID)
    server_socket, socket_path = create_listener(tmp_path)
    client_socket = connect_client(socket_path)

    try:
        server._get_peer_uid = lambda client: CLIENT_UID
        assert server.accept_client(server_socket)

        event = {
            "type": EVENT_ERROR,
            "code": "invalid_message",
            "message": "Test.",
        }

        assert server.send_event(event)

        received = client_socket.recv(4096)

        assert json.loads(received.decode("utf-8")) == event
        assert received.endswith(b"\n")
    finally:
        server.close_client()
        client_socket.close()
        server_socket.close()


def test_close_client_resets_connection_state(tmp_path):
    server = HelperServer(CLIENT_UID)
    server_socket, socket_path = create_listener(tmp_path)
    client_socket = connect_client(socket_path)

    try:
        server._get_peer_uid = lambda client: CLIENT_UID
        assert server.accept_client(server_socket)

        server._receive_buffer.extend(b"partial message")

        server.close_client()

        assert not server.has_client()
        assert server.get_client_socket() is None
        assert server._receive_buffer == bytearray()
    finally:
        server.close_client()
        client_socket.close()
        server_socket.close()


def test_close_client_is_idempotent():
    server = HelperServer(CLIENT_UID)

    server.close_client()
    server.close_client()

    assert not server.has_client()
    assert server.get_client_socket() is None


def test_receive_command_clears_buffer_when_new_client_connects(tmp_path):
    server = HelperServer(CLIENT_UID)
    server_socket, socket_path = create_listener(tmp_path)

    first_client = connect_client(socket_path)

    try:
        server._get_peer_uid = lambda client: CLIENT_UID
        assert server.accept_client(server_socket)

        server._receive_buffer.extend(b"stale data")

        server.close_client()
        first_client.close()

        second_client = connect_client(socket_path)

        try:
            assert server.accept_client(server_socket)
            assert server._receive_buffer == bytearray()
        finally:
            server.close_client()
            second_client.close()
    finally:
        server_socket.close()


def test_get_peer_uid_unpacks_pid_uid_gid():
    server = HelperServer(CLIENT_UID)

    mock_socket = MagicMock()
    credentials = struct.pack("3i", 123, CLIENT_UID, 456)
    mock_socket.getsockopt.return_value = credentials

    assert server._get_peer_uid(mock_socket) == CLIENT_UID

    mock_socket.getsockopt.assert_called_once_with(
        socket.SOL_SOCKET,
        socket.SO_PEERCRED,
        struct.calcsize("3i"),
    )
