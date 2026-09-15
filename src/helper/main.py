import logging
import os
import select
import socket
import time

import evdev

from .commands import (
    HelperContext,
    handle_command,
    reset_client_state,
)
from .devices import (
    DeviceRegistry,
    HelperDevice,
)
from .events import InputEventReader
from .hotplug import (
    process_device_changes,
    process_keyboard_selector,
    process_mouse_discovery,
    process_mouse_selector,
)
from .input_processing import process_input
from .keyboard import (
    KeyboardSelector,
    KeyboardState,
)
from .mouse import MouseSelector
from .protocol import (
    COMMAND_HELLO,
    ERROR_INVALID_COMMAND,
    EVENT_ERROR,
    EVENT_HELLO_ACK,
    PROTOCOL_VERSION,
    ProtocolError,
)
from .server import ClientDisconnected, HelperServer
from .state import HelperState
from .xkb import Xkb

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def get_listening_socket() -> socket.socket:
    """Return the listening socket provided by systemd."""
    listen_pid = os.environ.get("LISTEN_PID")
    listen_fds = os.environ.get("LISTEN_FDS")

    if listen_pid != str(os.getpid()):
        raise RuntimeError("Invalid LISTEN_PID.")

    if listen_fds != "1":
        raise RuntimeError("Expected exactly one listening socket.")

    return socket.fromfd(
        3,
        socket.AF_UNIX,
        socket.SOCK_STREAM,
    )


def get_client_uid() -> int:
    """Return the configured tray client UID."""
    value = os.environ.get("DOFUS_FOCUS_CLIENT_UID")

    if value is None:
        raise RuntimeError("DOFUS_FOCUS_CLIENT_UID is not set.")

    try:
        uid = int(value)
    except ValueError as exc:
        raise RuntimeError(
            "DOFUS_FOCUS_CLIENT_UID must be an integer."
        ) from exc

    if uid < 0:
        raise RuntimeError("DOFUS_FOCUS_CLIENT_UID must be non-negative.")

    return uid


def send_error(
    server: HelperServer,
    code: str,
    message: str,
) -> None:
    """Send a structured protocol error to the tray."""
    server.send_event(
        {
            "type": EVENT_ERROR,
            "code": code,
            "message": message,
        }
    )


def handle_protocol_error(
    server: HelperServer,
    error: ProtocolError,
) -> None:
    """Report a protocol error and close the connected client."""
    try:
        server.send_event(
            {
                "type": EVENT_ERROR,
                "code": error.code,
                "message": str(error),
            }
        )
    finally:
        server.close_client()


def main() -> None:
    """Run the Dofus Focus input helper."""
    server_socket = get_listening_socket()
    client_uid = get_client_uid()

    server = HelperServer(client_uid)
    registry = DeviceRegistry()
    reader = InputEventReader()
    keyboard_selector = KeyboardSelector()
    mouse_selector = MouseSelector()
    keyboard_state = KeyboardState()
    xkb = Xkb()
    xkb.load_wayland_keymap()

    context = HelperContext(
        server=server,
        registry=registry,
        reader=reader,
        keyboard_selector=keyboard_selector,
        mouse_selector=mouse_selector,
        keyboard_state=keyboard_state,
        xkb=xkb,
    )
    state = HelperState()

    logger.info("Dofus Focus input helper started.")

    while True:
        try:
            new_reader_fds: set[int] = set()
            selected_events: list[
                tuple[HelperDevice, evdev.InputEvent]
            ] = []

            read_sockets: list[int | socket.socket] = [server_socket]

            if state.input_monitoring_active:
                read_sockets.extend(reader.get_watched_fds())

                monitor_fd = reader.get_device_monitor_fd()
                if monitor_fd is not None:
                    read_sockets.append(monitor_fd)

            if keyboard_selector.is_active():
                read_sockets.extend(
                    keyboard_selector.get_watched_fds(),
                )

            if mouse_selector.is_active():
                read_sockets.extend(mouse_selector.get_watched_fds())

            if (
                state.capture_active
                and state.mouse_grabber is not None
                and state.mouse_grabber.is_started()
                and state.mouse_interceptor is None
            ):
                read_sockets.append(state.mouse_grabber.get_device().fileno())

            if (
                state.mouse_interceptor is not None
                and state.mouse_interceptor.is_started()
            ):
                read_sockets.append(state.mouse_interceptor.fileno())

            client_socket = server.get_client_socket()

            if client_socket is not None:
                read_sockets.append(client_socket)

            selector_timeout = mouse_selector.remaining_timeout()

            discovery_timeout = None
            if state.next_mouse_discovery is not None:
                discovery_timeout = max(
                    0.0,
                    state.next_mouse_discovery - time.monotonic(),
                )

            timeouts = [
                timeout
                for timeout in (selector_timeout, discovery_timeout)
                if timeout is not None
            ]

            timeout = min(timeouts) if timeouts else None

            if server.has_pending_command():
                readable = [server.get_client_socket()]
            else:
                readable, _, _ = select.select(
                    read_sockets,
                    [],
                    [],
                    timeout,
                )

            process_mouse_discovery(context, state)

            new_reader_fds = process_keyboard_selector(
                context,
                state,
                readable,
                selected_events,
            )

            process_mouse_selector(
                context,
                state,
                readable,
                selector_timeout,
                selected_events,
            )

            process_device_changes(
                context,
                state,
                readable,
            )

            if server_socket in readable:
                server.accept_client(server_socket)

            client_socket = server.get_client_socket()

            if (
                client_socket is not None
                and client_socket in readable
            ):
                try:
                    command = server.receive_command()
                except ProtocolError as error:
                    handle_protocol_error(
                        server,
                        error,
                    )

                    reset_client_state(
                        context,
                        state,
                    )
                    continue

                if command is None:
                    reset_client_state(
                        context,
                        state,
                    )
                    continue

                if not state.handshake_completed:
                    if command["type"] != COMMAND_HELLO:
                        send_error(
                            server,
                            ERROR_INVALID_COMMAND,
                            "HELLO is required before other commands.",
                        )

                        server.close_client()
                        reset_client_state(
                            context,
                            state,
                        )
                        continue

                    server.send_event(
                        {
                            "type": EVENT_HELLO_ACK,
                            "protocol": PROTOCOL_VERSION,
                        }
                    )

                    state.handshake_completed = True
                    continue

                if handle_command(
                    command,
                    context,
                    state,
                ):
                    continue

            if process_input(
                context,
                state,
                readable,
                new_reader_fds,
                selected_events,
            ):
                continue

        except ClientDisconnected:
            logger.info("Tray client disconnected unexpectedly.")
            reset_client_state(
                context,
                state,
            )
            continue


if __name__ == "__main__":
    main()
