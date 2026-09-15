import json
import socket
import threading

import pytest

from app.helper_client import (
    HelperClient,
    HelperClientError,
)
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
    EVENT_KEYBOARD_EVENT,
    MAX_COMMAND_SIZE,
    PROTOCOL_VERSION,
    ProtocolError,
)


def create_listener(tmp_path):
    socket_path = tmp_path / "helper.sock"

    server_socket = socket.socket(
        socket.AF_UNIX,
        socket.SOCK_STREAM,
    )
    server_socket.bind(str(socket_path))
    server_socket.listen(1)

    return server_socket, socket_path


def receive_message(client_socket):
    buffer = bytearray()

    while b"\n" not in buffer:
        data = client_socket.recv(4096)

        if not data:
            raise RuntimeError("Client disconnected.")

        buffer.extend(data)

    separator = buffer.index(b"\n")

    return json.loads(
        bytes(buffer[:separator]).decode("utf-8"),
    )


def send_event(server_socket, event):
    server_socket.sendall(
        (
            json.dumps(
                event,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8"),
    )


def start_client(
    socket_path,
    on_disconnect=None,
):
    received_events = []
    event_received = threading.Event()

    def on_event(event):
        received_events.append(event)

        if event["type"] != EVENT_HELLO_ACK:
            event_received.set()

    client = HelperClient(
        socket_path=str(socket_path),
        on_event=on_event,
        on_disconnect=on_disconnect,
    )

    return (
        client,
        received_events,
        event_received,
    )


def perform_handshake(client_socket):
    assert receive_message(client_socket) == {
        "type": COMMAND_HELLO,
        "protocol": PROTOCOL_VERSION,
    }

    send_event(
        client_socket,
        {
            "type": EVENT_HELLO_ACK,
            "protocol": PROTOCOL_VERSION,
        },
    )


def test_connect_performs_handshake(tmp_path):
    server_socket, socket_path = create_listener(tmp_path)
    client_socket = None
    client = None

    try:
        client, _, _ = start_client(socket_path)

        def accept_client():
            nonlocal client_socket

            client_socket, _ = server_socket.accept()
            perform_handshake(client_socket)

        server_thread = threading.Thread(
            target=accept_client,
        )
        server_thread.start()

        client.connect()

        server_thread.join()

        assert client.is_ready()
    finally:
        if client is not None:
            client.disconnect()

        if client_socket is not None:
            client_socket.close()

        server_socket.close()


def test_connect_fails_when_helper_is_unavailable(tmp_path):
    socket_path = tmp_path / "missing.sock"

    client = HelperClient(
        socket_path=str(socket_path),
    )

    with pytest.raises(
        HelperClientError,
        match="Unable to connect",
    ):
        client.connect()

    assert not client.is_ready()


def test_connect_fails_when_handshake_times_out(
    tmp_path,
    monkeypatch,
):
    server_socket, socket_path = create_listener(tmp_path)
    client_socket = None

    monkeypatch.setattr(
        "app.helper_client.HANDSHAKE_TIMEOUT",
        0.01,
    )

    client = HelperClient(
        socket_path=str(socket_path),
    )

    def accept_client():
        nonlocal client_socket

        client_socket, _ = server_socket.accept()
        receive_message(client_socket)

    server_thread = threading.Thread(
        target=accept_client,
    )
    server_thread.start()

    try:
        with pytest.raises(
            HelperClientError,
            match="handshake timed out",
        ):
            client.connect()

        assert not client.is_ready()
    finally:
        client.disconnect()
        server_thread.join()

        if client_socket is not None:
            client_socket.close()

        server_socket.close()


def test_disconnect_resets_current_connection():
    disconnected = threading.Event()

    def on_disconnect():
        disconnected.set()

    client = HelperClient(
        on_disconnect=on_disconnect,
    )
    socket_a = socket.socket()

    try:
        with client._state_lock:
            client._socket = socket_a
            client._connected = True
            client._ready = True

        client._ready_event.set()

        client._handle_disconnect(socket_a)

        assert client._socket is None
        assert not client._connected
        assert not client._ready
        assert not client._ready_event.is_set()
        assert disconnected.is_set()
    finally:
        socket_a.close()


def test_stale_connection_cannot_disconnect_current_connection():
    disconnected = threading.Event()

    def on_disconnect():
        disconnected.set()

    client = HelperClient(
        on_disconnect=on_disconnect,
    )
    socket_a = socket.socket()
    socket_b = socket.socket()

    try:
        with client._state_lock:
            client._socket = socket_b
            client._connected = True
            client._ready = True

        client._ready_event.set()

        client._handle_disconnect(socket_a)

        assert client._socket is socket_b
        assert client._connected
        assert client._ready
        assert client._ready_event.is_set()
        assert not disconnected.is_set()
    finally:
        socket_a.close()
        socket_b.close()


def test_commands_require_completed_handshake(tmp_path):
    client = HelperClient(
        socket_path=str(tmp_path / "helper.sock"),
    )

    with pytest.raises(
        HelperClientError,
        match="helper is not ready",
    ):
        client.start()

    with pytest.raises(
        HelperClientError,
        match="helper is not ready",
    ):
        client.stop()

    with pytest.raises(
        HelperClientError,
        match="helper is not ready",
    ):
        client.start_capture(None)

    with pytest.raises(
        HelperClientError,
        match="helper is not ready",
    ):
        client.stop_capture()

    with pytest.raises(
        HelperClientError,
        match="helper is not ready",
    ):
        client.grab_selected_mouse()

    with pytest.raises(
        HelperClientError,
        match="helper is not ready",
    ):
        client.release_selected_mouse()

    with pytest.raises(
        HelperClientError,
        match="helper is not ready",
    ):
        client.set_mouse_interception(True)

    with pytest.raises(
        HelperClientError,
        match="helper is not ready",
    ):
        client.set_intercepted_mouse_buttons({4, 5})

    with pytest.raises(
        HelperClientError,
        match="helper is not ready",
    ):
        client.set_shortcut_configuration({})


def test_start_sends_command(tmp_path):
    server_socket, socket_path = create_listener(tmp_path)
    client_socket = None
    client = None

    try:
        client, _, _ = start_client(socket_path)

        def accept_client():
            nonlocal client_socket

            client_socket, _ = server_socket.accept()
            perform_handshake(client_socket)

            assert receive_message(client_socket) == {
                "type": COMMAND_START,
            }

        server_thread = threading.Thread(
            target=accept_client,
        )
        server_thread.start()

        client.connect()
        client.start()

        server_thread.join()
    finally:
        if client is not None:
            client.disconnect()

        if client_socket is not None:
            client_socket.close()

        server_socket.close()


def test_stop_sends_command(tmp_path):
    server_socket, socket_path = create_listener(tmp_path)
    client_socket = None
    client = None

    try:
        client, _, _ = start_client(socket_path)

        def accept_client():
            nonlocal client_socket

            client_socket, _ = server_socket.accept()
            perform_handshake(client_socket)

            assert receive_message(client_socket) == {
                "type": COMMAND_STOP,
            }

        server_thread = threading.Thread(
            target=accept_client,
        )
        server_thread.start()

        client.connect()
        client.stop()

        server_thread.join()
    finally:
        if client is not None:
            client.disconnect()

        if client_socket is not None:
            client_socket.close()

        server_socket.close()


def test_start_capture_sends_null_mouse_buttons(tmp_path):
    server_socket, socket_path = create_listener(tmp_path)
    client_socket = None
    client = None

    try:
        client, _, _ = start_client(socket_path)

        def accept_client():
            nonlocal client_socket

            client_socket, _ = server_socket.accept()
            perform_handshake(client_socket)

            assert receive_message(client_socket) == {
                "type": COMMAND_START_CAPTURE,
                "allowed_mouse_buttons": None,
            }

        server_thread = threading.Thread(
            target=accept_client,
        )
        server_thread.start()

        client.connect()
        client.start_capture(None)

        server_thread.join()
    finally:
        if client is not None:
            client.disconnect()

        if client_socket is not None:
            client_socket.close()

        server_socket.close()


def test_start_capture_sends_sorted_mouse_buttons(tmp_path):
    server_socket, socket_path = create_listener(tmp_path)
    client_socket = None
    client = None

    try:
        client, _, _ = start_client(socket_path)

        def accept_client():
            nonlocal client_socket

            client_socket, _ = server_socket.accept()
            perform_handshake(client_socket)

            assert receive_message(client_socket) == {
                "type": COMMAND_START_CAPTURE,
                "allowed_mouse_buttons": [275, 276],
            }

        server_thread = threading.Thread(
            target=accept_client,
        )
        server_thread.start()

        client.connect()
        client.start_capture({276, 275})

        server_thread.join()
    finally:
        if client is not None:
            client.disconnect()

        if client_socket is not None:
            client_socket.close()

        server_socket.close()


def test_stop_capture_sends_command(tmp_path):
    server_socket, socket_path = create_listener(tmp_path)
    client_socket = None
    client = None

    try:
        client, _, _ = start_client(socket_path)

        def accept_client():
            nonlocal client_socket

            client_socket, _ = server_socket.accept()
            perform_handshake(client_socket)

            assert receive_message(client_socket) == {
                "type": COMMAND_STOP_CAPTURE,
            }

        server_thread = threading.Thread(
            target=accept_client,
        )
        server_thread.start()

        client.connect()
        client.stop_capture()

        server_thread.join()
    finally:
        if client is not None:
            client.disconnect()

        if client_socket is not None:
            client_socket.close()

        server_socket.close()


def test_grab_selected_mouse_sends_command(tmp_path):
    server_socket, socket_path = create_listener(tmp_path)
    client_socket = None
    client = None

    try:
        client, _, _ = start_client(socket_path)

        def accept_client():
            nonlocal client_socket

            client_socket, _ = server_socket.accept()
            perform_handshake(client_socket)

            assert receive_message(client_socket) == {
                "type": COMMAND_GRAB_SELECTED_MOUSE,
            }

        server_thread = threading.Thread(
            target=accept_client,
        )
        server_thread.start()

        client.connect()
        client.grab_selected_mouse()

        server_thread.join()
    finally:
        if client is not None:
            client.disconnect()

        if client_socket is not None:
            client_socket.close()

        server_socket.close()


def test_release_selected_mouse_sends_command(tmp_path):
    server_socket, socket_path = create_listener(tmp_path)
    client_socket = None
    client = None

    try:
        client, _, _ = start_client(socket_path)

        def accept_client():
            nonlocal client_socket

            client_socket, _ = server_socket.accept()
            perform_handshake(client_socket)

            assert receive_message(client_socket) == {
                "type": COMMAND_RELEASE_SELECTED_MOUSE,
            }

        server_thread = threading.Thread(
            target=accept_client,
        )
        server_thread.start()

        client.connect()
        client.release_selected_mouse()

        server_thread.join()
    finally:
        if client is not None:
            client.disconnect()

        if client_socket is not None:
            client_socket.close()

        server_socket.close()


def test_set_mouse_interception_sends_command(tmp_path):
    server_socket, socket_path = create_listener(tmp_path)
    client_socket = None
    client = None

    try:
        client, _, _ = start_client(socket_path)

        def accept_client():
            nonlocal client_socket

            client_socket, _ = server_socket.accept()
            perform_handshake(client_socket)

            assert receive_message(client_socket) == {
                "type": COMMAND_SET_MOUSE_INTERCEPTION,
                "enabled": True,
            }

        server_thread = threading.Thread(
            target=accept_client,
        )
        server_thread.start()

        client.connect()
        client.set_mouse_interception(True)

        server_thread.join()
    finally:
        if client is not None:
            client.disconnect()

        if client_socket is not None:
            client_socket.close()

        server_socket.close()


def test_set_intercepted_mouse_buttons_sends_sorted_buttons(
    tmp_path,
):
    server_socket, socket_path = create_listener(tmp_path)
    client_socket = None
    client = None

    try:
        client, _, _ = start_client(socket_path)

        def accept_client():
            nonlocal client_socket

            client_socket, _ = server_socket.accept()
            perform_handshake(client_socket)

            assert receive_message(client_socket) == {
                "type": COMMAND_SET_INTERCEPTED_MOUSE_BUTTONS,
                "buttons": [275, 276],
            }

        server_thread = threading.Thread(
            target=accept_client,
        )
        server_thread.start()

        client.connect()
        client.set_intercepted_mouse_buttons({276, 275})

        server_thread.join()
    finally:
        if client is not None:
            client.disconnect()

        if client_socket is not None:
            client_socket.close()

        server_socket.close()


def test_set_shortcut_configuration_sends_command(tmp_path):
    server_socket, socket_path = create_listener(tmp_path)
    client_socket = None
    client = None

    try:
        client, _, _ = start_client(socket_path)

        configuration = {
            "calibration": {
                "primary": {
                    "trigger": "F1",
                    "modifiers": ["CTRL"],
                },
                "alternate": None,
            },
            "next": {
                "primary": {
                    "trigger": "N",
                    "modifiers": ["META"],
                },
                "alternate": {
                    "trigger": "BTN_SIDE",
                    "modifiers": [],
                },
            },
            "previous": {
                "primary": {
                    "trigger": "P",
                    "modifiers": ["ALT", "SHIFT"],
                },
                "alternate": None,
            },
        }

        def accept_client():
            nonlocal client_socket

            client_socket, _ = server_socket.accept()
            perform_handshake(client_socket)

            assert receive_message(client_socket) == {
                "type": COMMAND_SET_SHORTCUT_CONFIGURATION,
                "configuration": configuration,
            }

        server_thread = threading.Thread(
            target=accept_client,
        )
        server_thread.start()

        client.connect()
        client.set_shortcut_configuration(configuration)

        server_thread.join()
    finally:
        if client is not None:
            client.disconnect()

        if client_socket is not None:
            client_socket.close()

        server_socket.close()


def test_receive_loop_dispatches_event(tmp_path):
    server_socket, socket_path = create_listener(tmp_path)
    client_socket = None
    client = None

    try:
        client, received_events, event_received = start_client(
            socket_path,
        )

        def accept_client():
            nonlocal client_socket

            client_socket, _ = server_socket.accept()
            perform_handshake(client_socket)

            send_event(
                client_socket,
                {
                    "type": EVENT_KEYBOARD_EVENT,
                    "device_id": "keyboard-1",
                    "code": 30,
                    "value": 1,
                    "timestamp": 123.456,
                },
            )

        server_thread = threading.Thread(
            target=accept_client,
        )
        server_thread.start()

        client.connect()

        assert event_received.wait(1.0)

        assert received_events[-1] == {
            "type": EVENT_KEYBOARD_EVENT,
            "device_id": "keyboard-1",
            "code": 30,
            "value": 1,
            "timestamp": 123.456,
        }

        server_thread.join()
    finally:
        if client is not None:
            client.disconnect()

        if client_socket is not None:
            client_socket.close()

        server_socket.close()


def test_receive_loop_handles_multiple_events_in_one_read(
    tmp_path,
):
    server_socket, socket_path = create_listener(tmp_path)
    client_socket = None
    client = None

    try:
        client, received_events, event_received = start_client(
            socket_path,
        )

        def accept_client():
            nonlocal client_socket

            client_socket, _ = server_socket.accept()
            perform_handshake(client_socket)

            payload = (
                json.dumps(
                    {
                        "type": EVENT_KEYBOARD_EVENT,
                        "device_id": "keyboard-1",
                        "code": 30,
                        "value": 1,
                        "timestamp": 1.0,
                    },
                    separators=(",", ":"),
                )
                + "\n"
                + json.dumps(
                    {
                        "type": EVENT_KEYBOARD_EVENT,
                        "device_id": "keyboard-1",
                        "code": 30,
                        "value": 0,
                        "timestamp": 2.0,
                    },
                    separators=(",", ":"),
                )
                + "\n"
            )

            client_socket.sendall(payload.encode("utf-8"))

        server_thread = threading.Thread(
            target=accept_client,
        )
        server_thread.start()

        client.connect()

        assert event_received.wait(1.0)

        server_thread.join()

        assert received_events[-2:] == [
            {
                "type": EVENT_KEYBOARD_EVENT,
                "device_id": "keyboard-1",
                "code": 30,
                "value": 1,
                "timestamp": 1.0,
            },
            {
                "type": EVENT_KEYBOARD_EVENT,
                "device_id": "keyboard-1",
                "code": 30,
                "value": 0,
                "timestamp": 2.0,
            },
        ]
    finally:
        if client is not None:
            client.disconnect()

        if client_socket is not None:
            client_socket.close()

        server_socket.close()


def test_receive_loop_handles_fragmented_event(
    tmp_path,
):
    server_socket, socket_path = create_listener(tmp_path)
    client_socket = None
    client = None

    try:
        client, received_events, event_received = start_client(
            socket_path,
        )

        def accept_client():
            nonlocal client_socket

            client_socket, _ = server_socket.accept()
            perform_handshake(client_socket)

            payload = (
                json.dumps(
                    {
                        "type": EVENT_KEYBOARD_EVENT,
                        "device_id": "keyboard-1",
                        "code": 30,
                        "value": 1,
                        "timestamp": 1.0,
                    },
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")

            split = len(payload) // 2

            client_socket.sendall(payload[:split])
            client_socket.sendall(payload[split:])

        server_thread = threading.Thread(
            target=accept_client,
        )
        server_thread.start()

        client.connect()

        assert event_received.wait(1.0)

        server_thread.join()

        assert received_events[-1] == {
            "type": EVENT_KEYBOARD_EVENT,
            "device_id": "keyboard-1",
            "code": 30,
            "value": 1,
            "timestamp": 1.0,
        }
    finally:
        if client is not None:
            client.disconnect()

        if client_socket is not None:
            client_socket.close()

        server_socket.close()


def test_receive_loop_rejects_oversized_incomplete_message(
    tmp_path,
):
    server_socket, socket_path = create_listener(tmp_path)
    client_socket = None
    client = None
    disconnect_event = threading.Event()

    try:
        def on_disconnect():
            disconnect_event.set()

        client = HelperClient(
            socket_path=str(socket_path),
            on_disconnect=on_disconnect,
        )

        def accept_client():
            nonlocal client_socket

            client_socket, _ = server_socket.accept()
            perform_handshake(client_socket)

            client_socket.sendall(
                b"a" * (MAX_COMMAND_SIZE + 1),
            )

        server_thread = threading.Thread(
            target=accept_client,
        )
        server_thread.start()

        client.connect()

        assert disconnect_event.wait(1.0)
        assert not client.is_ready()

        server_thread.join()
    finally:
        if client is not None:
            client.disconnect()

        if client_socket is not None:
            client_socket.close()

        server_socket.close()


def test_receive_loop_rejects_invalid_event(
    tmp_path,
):
    server_socket, socket_path = create_listener(tmp_path)
    client_socket = None
    client = None
    disconnect_event = threading.Event()

    try:
        def on_disconnect():
            disconnect_event.set()

        client = HelperClient(
            socket_path=str(socket_path),
            on_disconnect=on_disconnect,
        )

        def accept_client():
            nonlocal client_socket

            client_socket, _ = server_socket.accept()
            perform_handshake(client_socket)

            client_socket.sendall(
                b'{"type":"invalid-event"}\n',
            )

        server_thread = threading.Thread(
            target=accept_client,
        )
        server_thread.start()

        client.connect()

        assert disconnect_event.wait(1.0)
        assert not client.is_ready()

        server_thread.join()
    finally:
        if client is not None:
            client.disconnect()

        if client_socket is not None:
            client_socket.close()

        server_socket.close()


def test_send_command_translates_protocol_error_to_helper_error(
    monkeypatch,
):
    client = HelperClient()
    client._ready = True

    monkeypatch.setattr(
        client,
        "_get_socket",
        lambda: object(),
    )

    def fail_encode(message):
        raise ProtocolError("invalid command")

    monkeypatch.setattr(
        "app.helper_client.encode_command",
        fail_encode,
    )

    with pytest.raises(
        HelperClientError,
        match="Invalid command",
    ):
        client.start()


def test_send_command_translates_socket_error_and_disconnects(
    monkeypatch,
):
    client = HelperClient()
    client._ready = True

    disconnect_called = threading.Event()

    def handle_disconnect(_client):
        disconnect_called.set()

    monkeypatch.setattr(
        client,
        "_handle_disconnect",
        handle_disconnect,
    )

    class FailingSocket:
        def sendall(self, payload):
            raise OSError("send failed")

    monkeypatch.setattr(
        client,
        "_get_socket",
        lambda: FailingSocket(),
    )

    with pytest.raises(
        HelperClientError,
        match="Communication with the input helper failed",
    ):
        client.start()

    assert disconnect_called.is_set()


def test_unexpected_disconnect_resets_state(tmp_path):
    server_socket, socket_path = create_listener(tmp_path)
    client_socket = None
    disconnect_event = threading.Event()

    def on_disconnect():
        disconnect_event.set()

    client = HelperClient(
        socket_path=str(socket_path),
        on_disconnect=on_disconnect,
    )

    def accept_client():
        nonlocal client_socket

        client_socket, _ = server_socket.accept()
        perform_handshake(client_socket)

    server_thread = threading.Thread(
        target=accept_client,
    )
    server_thread.start()

    try:
        client.connect()

        server_thread.join()

        client_socket.close()
        client_socket = None

        assert disconnect_event.wait(1.0)

        assert not client.is_ready()
    finally:
        client.disconnect()

        if client_socket is not None:
            client_socket.close()

        server_socket.close()


def test_disconnect_is_idempotent(tmp_path):
    client = HelperClient(
        socket_path=str(tmp_path / "helper.sock"),
    )

    client.disconnect()
    client.disconnect()

    assert not client.is_ready()


def test_disconnect_clears_ready_state_before_thread_join(
    tmp_path,
):
    server_socket, socket_path = create_listener(tmp_path)
    client_socket = None
    client = None

    try:
        client, _, _ = start_client(socket_path)

        def accept_client():
            nonlocal client_socket

            client_socket, _ = server_socket.accept()
            perform_handshake(client_socket)

        server_thread = threading.Thread(
            target=accept_client,
        )
        server_thread.start()

        client.connect()

        assert client.is_ready()

        client.disconnect()

        assert not client.is_ready()

        server_thread.join()
    finally:
        if client is not None:
            client.disconnect()

        if client_socket is not None:
            client_socket.close()

        server_socket.close()
