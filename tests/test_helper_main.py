import os
import socket
from unittest.mock import MagicMock

import pytest

from helper.main import (
    get_client_uid,
    get_listening_socket,
    handle_protocol_error,
    main,
)
from helper.protocol import (
    COMMAND_GRAB_SELECTED_MOUSE,
    COMMAND_HELLO,
    COMMAND_SET_MOUSE_INTERCEPTION,
    COMMAND_START,
    ERROR_INVALID_COMMAND,
    EVENT_ERROR,
    EVENT_HELLO_ACK,
    PROTOCOL_VERSION,
    ProtocolError,
)
from helper.server import ClientDisconnected
from input.classifier import DeviceClass


def build_main_mocks(monkeypatch):
    server_socket = MagicMock()
    client_socket = MagicMock()

    server = MagicMock()

    server.has_pending_command.return_value = False

    connection_state = {"client": client_socket}

    def get_client_socket():
        return connection_state["client"]

    def accept_client(_server_socket):
        connection_state["client"] = client_socket
        return True

    server.get_client_socket.side_effect = get_client_socket
    server.accept_client.side_effect = accept_client

    registry = MagicMock()
    registry.reconcile.return_value = ([], [], [])
    reader = MagicMock()
    mouse_selector = MagicMock()

    selection_state = {"active": False}

    def selector_is_active():
        return selection_state["active"]

    def selector_start(mice):
        selection_state["active"] = bool(mice)

    def selector_stop():
        selection_state["active"] = False

    mouse_selector.is_active.side_effect = selector_is_active
    mouse_selector.start.side_effect = selector_start
    mouse_selector.stop.side_effect = selector_stop
    mouse_selector.remaining_timeout.return_value = None
    mouse_selector.get_watched_fds.return_value = []

    monkeypatch.setattr(
        "helper.main.get_listening_socket",
        MagicMock(return_value=server_socket),
    )
    monkeypatch.setattr(
        "helper.main.get_client_uid",
        MagicMock(return_value=1000),
    )
    monkeypatch.setattr(
        "helper.main.HelperServer",
        MagicMock(return_value=server),
    )
    monkeypatch.setattr(
        "helper.main.DeviceRegistry",
        MagicMock(return_value=registry),
    )
    monkeypatch.setattr(
        "helper.main.InputEventReader",
        MagicMock(return_value=reader),
    )
    monkeypatch.setattr(
        "helper.main.MouseSelector",
        MagicMock(return_value=mouse_selector),
    )

    return (
        server_socket,
        client_socket,
        server,
        registry,
        reader,
        mouse_selector,
        selection_state,
        connection_state,
    )


def configure_commands(server, commands):
    remaining = list(commands)

    def receive_command():
        if not remaining:
            raise KeyboardInterrupt
        return remaining.pop(0)

    server.receive_command.side_effect = receive_command


def run_main_until_interrupt(monkeypatch, select_results):
    results = list(select_results)

    def fake_select(*_args):
        if results:
            return results.pop(0)
        raise KeyboardInterrupt

    monkeypatch.setattr(
        "helper.main.select.select",
        fake_select,
    )

    with pytest.raises(KeyboardInterrupt):
        main()


def test_get_listening_socket_returns_systemd_socket(monkeypatch):
    fake_socket = MagicMock(spec=socket.socket)

    monkeypatch.setattr(os, "getpid", lambda: 1234)
    monkeypatch.setenv("LISTEN_PID", "1234")
    monkeypatch.setenv("LISTEN_FDS", "1")

    monkeypatch.setattr(
        socket,
        "fromfd",
        lambda fd, _family, _socket_type: fake_socket,
    )

    assert get_listening_socket() is fake_socket


def test_get_listening_socket_rejects_invalid_listen_pid(monkeypatch):
    monkeypatch.setattr(os, "getpid", lambda: 1234)
    monkeypatch.setenv("LISTEN_PID", "5678")
    monkeypatch.setenv("LISTEN_FDS", "1")

    with pytest.raises(RuntimeError, match="Invalid LISTEN_PID"):
        get_listening_socket()


def test_get_listening_socket_rejects_missing_listen_pid(monkeypatch):
    monkeypatch.setattr(os, "getpid", lambda: 1234)
    monkeypatch.setenv("LISTEN_FDS", "1")
    monkeypatch.delenv("LISTEN_PID", raising=False)

    with pytest.raises(RuntimeError, match="Invalid LISTEN_PID"):
        get_listening_socket()


@pytest.mark.parametrize("listen_fds", ["0", "2", "10", ""])
def test_get_listening_socket_rejects_wrong_number_of_fds(
    monkeypatch,
    listen_fds,
):
    monkeypatch.setattr(os, "getpid", lambda: 1234)
    monkeypatch.setenv("LISTEN_PID", "1234")
    monkeypatch.setenv("LISTEN_FDS", listen_fds)

    with pytest.raises(
        RuntimeError,
        match="Expected exactly one listening socket",
    ):
        get_listening_socket()


def test_get_client_uid_returns_configured_uid(monkeypatch):
    monkeypatch.setenv("DOFUS_FOCUS_CLIENT_UID", "1000")

    assert get_client_uid() == 1000


def test_get_client_uid_accepts_zero(monkeypatch):
    monkeypatch.setenv("DOFUS_FOCUS_CLIENT_UID", "0")

    assert get_client_uid() == 0


def test_get_client_uid_rejects_missing_value(monkeypatch):
    monkeypatch.delenv("DOFUS_FOCUS_CLIENT_UID", raising=False)

    with pytest.raises(
        RuntimeError,
        match="DOFUS_FOCUS_CLIENT_UID is not set",
    ):
        get_client_uid()


def test_get_client_uid_rejects_non_integer(monkeypatch):
    monkeypatch.setenv("DOFUS_FOCUS_CLIENT_UID", "abc")

    with pytest.raises(
        RuntimeError,
        match="must be an integer",
    ):
        get_client_uid()


@pytest.mark.parametrize("value", ["-1", "-100"])
def test_get_client_uid_rejects_negative_value(monkeypatch, value):
    monkeypatch.setenv("DOFUS_FOCUS_CLIENT_UID", value)

    with pytest.raises(
        RuntimeError,
        match="must be non-negative",
    ):
        get_client_uid()


def test_handle_protocol_error_sends_error_and_closes_client():
    server = MagicMock()
    error = ProtocolError("Invalid message.")

    handle_protocol_error(server, error)

    server.send_event.assert_called_once_with(
        {
            "type": EVENT_ERROR,
            "code": error.code,
            "message": "Invalid message.",
        }
    )
    server.close_client.assert_called_once()


def test_handle_protocol_error_closes_client_when_send_fails():
    server = MagicMock()
    server.send_event.side_effect = OSError("socket closed")

    error = ProtocolError("Invalid message.")

    with pytest.raises(OSError, match="socket closed"):
        handle_protocol_error(server, error)

    server.close_client.assert_called_once()


def test_main_completes_hello_handshake(monkeypatch):
    (
        server_socket,
        client_socket,
        server,
        _registry,
        _reader,
        _selector,
        _selection_state,
        _connection_state,
    ) = build_main_mocks(monkeypatch)

    configure_commands(
        server,
        [
            {
                "type": COMMAND_HELLO,
                "protocol": PROTOCOL_VERSION,
            },
        ],
    )

    run_main_until_interrupt(
        monkeypatch,
        [
            ([server_socket], [], []),
            ([client_socket], [], []),
        ],
    )

    server.accept_client.assert_called_once_with(server_socket)
    server.send_event.assert_called_once_with(
        {
            "type": EVENT_HELLO_ACK,
            "protocol": PROTOCOL_VERSION,
        }
    )


def test_main_rejects_command_before_hello(monkeypatch):
    (
        _server_socket,
        client_socket,
        server,
        _registry,
        _reader,
        _selector,
        _selection_state,
        _connection_state,
    ) = build_main_mocks(monkeypatch)

    configure_commands(
        server,
        [
            {
                "type": COMMAND_START,
            },
        ],
    )

    run_main_until_interrupt(
        monkeypatch,
        [
            ([client_socket], [], []),
        ],
    )

    server.send_event.assert_called_once_with(
        {
            "type": EVENT_ERROR,
            "code": ERROR_INVALID_COMMAND,
            "message": "HELLO is required before other commands.",
        }
    )
    server.close_client.assert_called_once()


def test_main_closes_client_after_protocol_error(monkeypatch):
    (
        _server_socket,
        client_socket,
        server,
        _registry,
        reader,
        selector,
        _selection_state,
        _connection_state,
    ) = build_main_mocks(monkeypatch)

    server.receive_command.side_effect = ProtocolError(
        "Invalid command.",
    )

    run_main_until_interrupt(
        monkeypatch,
        [
            ([client_socket], [], []),
        ],
    )

    server.send_event.assert_called_once_with(
        {
            "type": EVENT_ERROR,
            "code": "invalid_message",
            "message": "Invalid command.",
        }
    )
    server.close_client.assert_called_once()
    reader.close.assert_called_once()
    selector.stop.assert_called_once()


def test_main_accepts_new_client_when_no_client_is_connected(
    monkeypatch,
):
    server_socket = MagicMock()
    client_socket = MagicMock()

    server = MagicMock()

    server.has_pending_command.return_value = False

    connection_state = {"client": None}

    def get_client_socket():
        return connection_state["client"]

    def accept_client(_server_socket):
        connection_state["client"] = client_socket
        return True

    server.get_client_socket.side_effect = get_client_socket
    server.accept_client.side_effect = accept_client

    monkeypatch.setattr(
        "helper.main.get_listening_socket",
        MagicMock(return_value=server_socket),
    )
    monkeypatch.setattr(
        "helper.main.get_client_uid",
        MagicMock(return_value=1000),
    )
    monkeypatch.setattr(
        "helper.main.HelperServer",
        MagicMock(return_value=server),
    )

    run_main_until_interrupt(
        monkeypatch,
        [
            ([server_socket], [], []),
        ],
    )

    server.accept_client.assert_called_once_with(server_socket)


def test_main_stops_interceptor_on_client_disconnect(monkeypatch):
    (
        server_socket,
        client_socket,
        server,
        _registry,
        reader,
        _selector,
        _selection_state,
        connection_state,
    ) = build_main_mocks(monkeypatch)

    mouse = MagicMock()
    mouse.device_class = DeviceClass.MOUSE
    mouse.device_id = "mouse-1"

    def select_mouse(
        _context,
        state,
        _readable,
        _selector_timeout,
        _selected_events,
    ):
        state.selected_mouse = mouse

    monkeypatch.setattr(
        "helper.main.process_mouse_selector",
        select_mouse,
    )

    interceptor = MagicMock()
    interceptor.is_started.return_value = True
    interceptor.fileno.return_value = 99

    monkeypatch.setattr(
        "helper.commands.start_mouse_interceptor",
        MagicMock(return_value=interceptor),
    )

    grabber = MagicMock()
    grabber.is_started.return_value = True

    monkeypatch.setattr(
        "helper.commands.MouseGrabber",
        MagicMock(return_value=grabber),
    )

    commands = [
        {
            "type": COMMAND_HELLO,
            "protocol": PROTOCOL_VERSION,
        },
        {
            "type": COMMAND_START,
        },
        {
            "type": COMMAND_GRAB_SELECTED_MOUSE,
        },
        {
            "type": COMMAND_SET_MOUSE_INTERCEPTION,
            "enabled": True,
        },
        ClientDisconnected,
    ]

    def receive_command():
        command = commands.pop(0)

        if command is ClientDisconnected:
            connection_state["client"] = None
            raise ClientDisconnected

        return command

    server.receive_command.side_effect = receive_command

    run_main_until_interrupt(
        monkeypatch,
        [
            ([server_socket], [], []),
            ([client_socket], [], []),  # HELLO
            ([client_socket], [], []),  # START
            ([client_socket], [], []),  # GRAB_SELECTED_MOUSE
            ([client_socket], [], []),  # ENABLE
            ([client_socket], [], []),  # client disconnect
        ],
    )

    interceptor.stop.assert_called_once()
    reader.close.assert_called_once()
    _selector.stop.assert_called_once()


def test_main_uses_pending_command_without_select(monkeypatch):
    (
        _server_socket,
        _client_socket,
        server,
        _registry,
        _reader,
        _selector,
        _selection_state,
        _connection_state,
    ) = build_main_mocks(monkeypatch)

    server.has_pending_command.return_value = True

    def receive_command():
        raise KeyboardInterrupt

    server.receive_command.side_effect = receive_command

    def fail_select(*_args):
        raise AssertionError(
            "select.select() must not be called while a command is pending."
        )

    monkeypatch.setattr(
        "helper.main.select.select",
        fail_select,
    )

    with pytest.raises(KeyboardInterrupt):
        main()

    server.has_pending_command.assert_called_once()
    server.receive_command.assert_called_once_with()
