import json
import socket
import threading
import time

import evdev

from app.helper_client import HelperClient, HelperClientError
from helper.protocol import (
    COMMAND_GRAB_SELECTED_MOUSE,
    EVENT_ERROR,
    EVENT_MOUSE_INTERCEPTION_STARTED,
    EVENT_MOUSE_INTERCEPTION_STOPPED,
    EVENT_MOUSE_SELECTED,
    EVENT_SHORTCUT,
)
from input.discovery import InputDeviceInfo
from shortcuts.model import Shortcut
from shortcuts.service import ShortcutService
from shortcuts.storage import ShortcutConfiguration


def make_device(path, name="Test device"):
    return InputDeviceInfo(
        path=path,
        name=name,
        phys="",
        uniq="",
        vendor=0,
        product=0,
        bus=0,
        capabilities={},
    )


class FakeXkb:
    def keycode_to_key(self, keycode):
        return {
            evdev.ecodes.KEY_N: "N",
        }.get(keycode)


def make_shortcut(trigger, modifiers=None):
    return Shortcut(
        trigger=trigger,
        modifiers=frozenset(modifiers or []),
    )


def make_configuration():
    return {
        "calibration": ShortcutConfiguration(
            primary=make_shortcut("F1"),
            alternate=None,
        ),
        "next": ShortcutConfiguration(
            primary=make_shortcut("N", ["META"]),
            alternate=None,
        ),
        "previous": ShortcutConfiguration(
            primary=make_shortcut("P", ["META"]),
            alternate=None,
        ),
    }


def make_service(
    configuration=None,
    on_action=None,
):
    return ShortcutService(
        xkb=FakeXkb(),
        configuration=(
            make_configuration() if configuration is None else configuration
        ),
        on_action=((lambda _action: None) if on_action is None else on_action),
        stop_requested=lambda: False,
    )


def test_service_executes_helper_shortcut_action():
    executed_actions = []

    service = make_service(
        on_action=executed_actions.append,
    )

    service._handle_helper_shortcut(
        {
            "type": EVENT_SHORTCUT,
            "action": "next",
        },
    )

    assert executed_actions == ["next"]


def test_service_executes_multiple_helper_shortcut_actions():
    executed_actions = []

    service = make_service(
        on_action=executed_actions.append,
    )

    service._handle_helper_shortcut(
        {
            "type": EVENT_SHORTCUT,
            "action": "next",
        },
    )
    service._handle_helper_shortcut(
        {
            "type": EVENT_SHORTCUT,
            "action": "previous",
        },
    )

    assert executed_actions == [
        "next",
        "previous",
    ]


def test_service_processes_helper_keyboard_event(monkeypatch):
    captured_events = []

    service = make_service(
        configuration={
            "next": ShortcutConfiguration(
                primary=make_shortcut("N", ["CTRL"]),
            ),
        },
    )

    monkeypatch.setattr(
        service,
        "_process_capture_event",
        captured_events.append,
    )

    service._handle_helper_event(
        {
            "type": "keyboard_event",
            "device_id": "keyboard-1",
            "code": evdev.ecodes.KEY_N,
            "value": 1,
            "timestamp": 123.456,
            "modifiers": ["CTRL"],
        },
    )

    assert len(captured_events) == 1

    event = captured_events[0]

    assert event.event_type == evdev.ecodes.EV_KEY
    assert event.event_code == evdev.ecodes.KEY_N
    assert event.value == 1
    assert event.timestamp == 123.456
    assert event.modifiers == frozenset({"CTRL"})


def test_service_processes_helper_keyboard_event_from_socket(
    monkeypatch,
    tmp_path,
):
    socket_path = tmp_path / "helper.sock"
    server_socket = socket.socket(
        socket.AF_UNIX,
        socket.SOCK_STREAM,
    )
    server_socket.bind(str(socket_path))
    server_socket.listen(1)

    service = make_service(
        configuration={
            "next": ShortcutConfiguration(
                primary=make_shortcut("N", ["CTRL"]),
            ),
        },
    )

    captured_shortcuts = []

    helper_client = HelperClient(
        socket_path=str(socket_path),
        on_event=service._handle_helper_event,
        on_disconnect=service._handle_helper_disconnect,
    )
    service._helper_client = helper_client

    client_socket = None

    def fake_helper():
        nonlocal client_socket

        client_socket, _ = server_socket.accept()

        client_socket.sendall(
            b'{"type":"hello_ack","protocol":1}\n',
        )

        buffer = bytearray()

        while True:
            separator = buffer.find(b"\n")
            if separator == -1:
                buffer.extend(client_socket.recv(4096))
                continue

            line = bytes(buffer[:separator])
            del buffer[: separator + 1]

            message = json.loads(line)

            if message["type"] == "start_capture":
                break

        client_socket.sendall(
            (
                '{"type":"keyboard_event",'
                '"device_id":"keyboard-1",'
                '"code":'
                f"{evdev.ecodes.KEY_N},"
                '"value":1,'
                '"timestamp":123.456,'
                '"modifiers":["CTRL"]}\n'
            ).encode(),
        )

    server_thread = threading.Thread(target=fake_helper)
    server_thread.start()

    try:
        helper_client.connect()

        service.start_capture(
            allowed_mouse_buttons=None,
            callback=captured_shortcuts.append,
            error_callback=lambda error: None,
            rejected_callback=lambda _reason: None,
        )

        server_thread.join(timeout=1)

        for _ in range(100):
            if captured_shortcuts == [
                make_shortcut("N", ["CTRL"]),
            ]:
                break
            time.sleep(0.01)

        assert captured_shortcuts == [
            make_shortcut("N", ["CTRL"]),
        ]
    finally:
        helper_client.disconnect()

        if client_socket is not None:
            client_socket.close()

        server_socket.close()

    assert not server_thread.is_alive()


def test_service_processes_helper_mouse_button_event(monkeypatch):
    captured_events = []

    service = make_service(
        configuration={
            "next": ShortcutConfiguration(
                primary=make_shortcut("BTN_SIDE"),
            ),
        },
    )

    monkeypatch.setattr(
        service,
        "_process_capture_event",
        captured_events.append,
    )

    service._handle_helper_event(
        {
            "type": "mouse_button_event",
            "device_id": "mouse-1",
            "code": evdev.ecodes.BTN_SIDE,
            "value": 1,
            "timestamp": 123.456,
        },
    )

    assert len(captured_events) == 1

    event = captured_events[0]

    assert event.event_type == evdev.ecodes.EV_KEY
    assert event.event_code == evdev.ecodes.BTN_SIDE
    assert event.value == 1
    assert event.timestamp == 123.456
    assert event.modifiers == frozenset()


def test_service_processes_helper_mouse_extra_button_event(monkeypatch):
    captured_events = []

    service = make_service(
        configuration={
            "previous": ShortcutConfiguration(
                primary=make_shortcut("BTN_EXTRA"),
            ),
        },
    )

    monkeypatch.setattr(
        service,
        "_process_capture_event",
        captured_events.append,
    )

    service._handle_helper_event(
        {
            "type": "mouse_button_event",
            "device_id": "mouse-1",
            "code": evdev.ecodes.BTN_EXTRA,
            "value": 1,
            "timestamp": 123.456,
        },
    )

    assert len(captured_events) == 1

    event = captured_events[0]

    assert event.event_type == evdev.ecodes.EV_KEY
    assert event.event_code == evdev.ecodes.BTN_EXTRA
    assert event.value == 1
    assert event.timestamp == 123.456
    assert event.modifiers == frozenset()


def test_service_ignores_helper_mouse_relative_event():
    executed_actions = []

    service = make_service(
        configuration={
            "next": ShortcutConfiguration(
                primary=make_shortcut("BTN_SIDE"),
            ),
        },
        on_action=executed_actions.append,
    )

    service._handle_helper_event(
        {
            "type": "mouse_relative_event",
            "device_id": "mouse-1",
            "code": evdev.ecodes.REL_X,
            "value": 100,
            "timestamp": 123.456,
        },
    )

    assert executed_actions == []


def test_service_processes_helper_mouse_button_event_from_socket(
    tmp_path,
):
    socket_path = tmp_path / "helper.sock"
    server_socket = socket.socket(
        socket.AF_UNIX,
        socket.SOCK_STREAM,
    )
    server_socket.bind(str(socket_path))
    server_socket.listen(1)

    service = make_service(
        configuration={
            "next": ShortcutConfiguration(
                primary=make_shortcut("BTN_SIDE"),
            ),
        },
    )

    captured_shortcuts = []

    helper_client = HelperClient(
        socket_path=str(socket_path),
        on_event=service._handle_helper_event,
        on_disconnect=service._handle_helper_disconnect,
    )
    service._helper_client = helper_client

    client_socket = None

    def fake_helper():
        nonlocal client_socket

        client_socket, _ = server_socket.accept()

        client_socket.sendall(
            b'{"type":"hello_ack","protocol":1}\n',
        )

        buffer = bytearray()

        while True:
            separator = buffer.find(b"\n")
            if separator == -1:
                buffer.extend(client_socket.recv(4096))
                continue

            line = bytes(buffer[:separator])
            del buffer[: separator + 1]

            message = json.loads(line)

            if message["type"] == "start_capture":
                break

        client_socket.sendall(
            (
                '{"type":"mouse_button_event",'
                '"device_id":"mouse-1",'
                '"code":'
                f"{evdev.ecodes.BTN_SIDE},"
                '"value":1,'
                '"timestamp":123.456}\n'
            ).encode(),
        )

    server_thread = threading.Thread(target=fake_helper)
    server_thread.start()

    try:
        helper_client.connect()

        service.start_capture(
            allowed_mouse_buttons={evdev.ecodes.BTN_SIDE},
            callback=captured_shortcuts.append,
            error_callback=lambda error: None,
            rejected_callback=lambda _reason: None,
        )

        server_thread.join(timeout=1)

        for _ in range(100):
            if captured_shortcuts == [
                make_shortcut("BTN_SIDE"),
            ]:
                break
            time.sleep(0.01)

        assert captured_shortcuts == [
            make_shortcut("BTN_SIDE"),
        ]
    finally:
        helper_client.disconnect()

        if client_socket is not None:
            client_socket.close()

        server_socket.close()

    assert not server_thread.is_alive()


def test_service_stores_helper_selected_mouse():
    service = make_service(
        configuration={},
    )

    service._handle_helper_event(
        {
            "type": EVENT_MOUSE_SELECTED,
            "device_id": "mouse-1",
        },
    )

    assert service._selected_mouse == "mouse-1"


def test_service_handles_helper_mouse_interception_started(
    caplog,
):
    service = make_service(
        configuration={},
    )

    with caplog.at_level("INFO"):
        service._handle_helper_event(
            {
                "type": EVENT_MOUSE_INTERCEPTION_STARTED,
                "device_id": "mouse-1",
            },
        )

    assert "Mouse interception started: device_id=mouse-1" in caplog.text


def test_service_handles_helper_mouse_interception_stopped(
    caplog,
):
    service = make_service(
        configuration={},
    )

    with caplog.at_level("INFO"):
        service._handle_helper_event(
            {
                "type": EVENT_MOUSE_INTERCEPTION_STOPPED,
                "device_id": "mouse-1",
            },
        )

    assert "Mouse interception stopped: device_id=mouse-1" in caplog.text


def test_service_requests_helper_mouse_interception(
    monkeypatch,
):
    service = make_service(
        configuration={},
    )

    calls = []

    monkeypatch.setattr(
        service._helper_client,
        "set_mouse_interception",
        calls.append,
    )

    service._set_helper_mouse_interception(True)

    assert calls == [True]


def test_service_handles_helper_mouse_interception_error(
    monkeypatch,
    caplog,
):
    service = make_service(
        configuration={},
    )

    def fail(_enabled):
        raise HelperClientError

    monkeypatch.setattr(
        service._helper_client,
        "set_mouse_interception",
        fail,
    )

    with caplog.at_level("ERROR"):
        service._set_helper_mouse_interception(True)

    assert "Unable to update mouse interception through input helper" in caplog.text


def test_service_syncs_helper_mouse_interception_when_mouse_is_selected(
    monkeypatch,
):
    service = make_service(
        configuration={},
    )

    service._calibrated = True
    service._mouse_interception_enabled = True

    button_calls = []
    grab_calls = []
    interception_calls = []

    monkeypatch.setattr(
        service,
        "_set_helper_intercepted_mouse_buttons",
        button_calls.append,
    )
    monkeypatch.setattr(
        service._helper_client,
        "grab_selected_mouse",
        lambda: grab_calls.append(True),
    )
    monkeypatch.setattr(
        service,
        "_set_helper_mouse_interception",
        interception_calls.append,
    )

    service._handle_helper_event(
        {
            "type": EVENT_MOUSE_SELECTED,
            "device_id": "mouse-1",
        },
    )

    assert service._selected_mouse == "mouse-1"
    assert grab_calls == [True]
    assert button_calls == [
        set(),
        set(),
    ]
    assert interception_calls == [True]


def test_service_does_not_enable_helper_mouse_interception_before_calibration(
    monkeypatch,
):
    service = make_service(
        configuration={},
    )

    service._mouse_interception_enabled = True

    calls = []

    monkeypatch.setattr(
        service,
        "_set_helper_mouse_interception",
        calls.append,
    )

    service._handle_helper_event(
        {
            "type": EVENT_MOUSE_SELECTED,
            "device_id": "mouse-1",
        },
    )

    assert calls == [False]


def test_service_syncs_helper_mouse_interception_when_calibration_becomes_valid(
    monkeypatch,
):
    service = make_service(
        configuration={},
    )

    service._selected_mouse = make_device(
        "/dev/input/event0",
        "Mouse",
    )
    service._mouse_interception_enabled = True

    button_calls = []
    grab_calls = []
    interception_calls = []

    monkeypatch.setattr(
        service,
        "_set_helper_intercepted_mouse_buttons",
        button_calls.append,
    )
    monkeypatch.setattr(
        service._helper_client,
        "grab_selected_mouse",
        lambda: grab_calls.append(True),
    )
    monkeypatch.setattr(
        service,
        "_set_helper_mouse_interception",
        interception_calls.append,
    )

    service.set_calibration_valid(True)

    assert grab_calls == [True]
    assert button_calls == [set()]
    assert interception_calls == [True]


def test_service_syncs_helper_mouse_interception_when_enabled_state_changes(
    monkeypatch,
):
    service = make_service(
        configuration={},
    )

    service._calibrated = True
    service._selected_mouse = make_device(
        "/dev/input/event0",
        "Mouse",
    )

    grab_calls = []
    interception_calls = []

    monkeypatch.setattr(
        service._helper_client,
        "grab_selected_mouse",
        lambda: grab_calls.append(True),
    )
    monkeypatch.setattr(
        service,
        "_set_helper_intercepted_mouse_buttons",
        lambda buttons: None,
    )
    monkeypatch.setattr(
        service,
        "_set_helper_mouse_interception",
        interception_calls.append,
    )

    service.set_mouse_interception_enabled(False)
    service.set_mouse_interception_enabled(True)

    assert grab_calls == [True]
    assert interception_calls == [False, True]


def test_service_does_not_enable_helper_mouse_interception_without_calibration(
    monkeypatch,
):
    service = make_service(
        configuration={},
    )

    service._selected_mouse = make_device(
        "/dev/input/event0",
        "Mouse",
    )

    calls = []

    monkeypatch.setattr(
        service,
        "_set_helper_mouse_interception",
        calls.append,
    )

    service.set_mouse_interception_enabled(False)

    assert calls == [False]


def test_service_updates_helper_intercepted_mouse_buttons(
    monkeypatch,
):
    service = make_service(
        configuration={},
    )

    service._mouse_interception_enabled = True

    calls = []

    monkeypatch.setattr(
        service._helper_client,
        "set_intercepted_mouse_buttons",
        calls.append,
    )

    configuration = {
        "next": ShortcutConfiguration(
            primary=make_shortcut("BTN_SIDE"),
        ),
        "previous": ShortcutConfiguration(
            primary=make_shortcut("BTN_EXTRA"),
        ),
    }

    service.update_configuration(configuration)

    assert calls == [
        {
            evdev.ecodes.BTN_SIDE,
            evdev.ecodes.BTN_EXTRA,
        },
    ]


def test_service_clears_helper_intercepted_mouse_buttons_when_interception_disabled(
    monkeypatch,
):
    service = make_service(
        configuration={},
    )

    service._mouse_interception_enabled = False

    calls = []

    monkeypatch.setattr(
        service._helper_client,
        "set_intercepted_mouse_buttons",
        calls.append,
    )

    configuration = {
        "next": ShortcutConfiguration(
            primary=make_shortcut("BTN_SIDE"),
        ),
    }

    service.update_configuration(configuration)

    assert calls == [set()]


def test_service_handles_helper_mouse_button_configuration_error(
    monkeypatch,
    caplog,
):
    service = make_service(
        configuration={},
    )

    def fail(_buttons):
        raise HelperClientError

    monkeypatch.setattr(
        service._helper_client,
        "set_intercepted_mouse_buttons",
        fail,
    )

    with caplog.at_level("ERROR"):
        service._set_helper_intercepted_mouse_buttons(
            {evdev.ecodes.BTN_SIDE},
        )

    assert (
        "Unable to update intercepted mouse buttons through input helper" in caplog.text
    )


def test_service_syncs_helper_mouse_buttons_when_mouse_is_selected(
    monkeypatch,
):
    service = make_service(
        configuration={},
    )

    service._mouse_interception_enabled = True

    button_calls = []
    interception_calls = []

    monkeypatch.setattr(
        service,
        "_set_helper_intercepted_mouse_buttons",
        button_calls.append,
    )
    monkeypatch.setattr(
        service,
        "_sync_helper_mouse_interception",
        lambda: interception_calls.append(True),
    )

    service._configuration = {
        "next": ShortcutConfiguration(
            primary=make_shortcut("BTN_SIDE"),
        ),
        "previous": ShortcutConfiguration(
            primary=make_shortcut("BTN_EXTRA"),
        ),
    }

    service._handle_helper_mouse_selected(
        {
            "type": EVENT_MOUSE_SELECTED,
            "device_id": "mouse-1",
        },
    )

    assert service._selected_mouse == "mouse-1"
    assert button_calls == [
        {
            evdev.ecodes.BTN_SIDE,
            evdev.ecodes.BTN_EXTRA,
        },
    ]
    assert interception_calls == [True]


def test_service_serializes_shortcut_configuration_for_helper(
    monkeypatch,
):
    service = make_service(
        configuration={},
    )

    calls = []

    monkeypatch.setattr(
        service._helper_client,
        "set_shortcut_configuration",
        calls.append,
    )

    configuration = {
        "calibration": ShortcutConfiguration(
            primary=make_shortcut("F1", ["SHIFT", "CTRL"]),
            alternate=None,
        ),
        "next": ShortcutConfiguration(
            primary=make_shortcut("N", ["META"]),
            alternate=make_shortcut("BTN_SIDE"),
        ),
        "previous": ShortcutConfiguration(
            primary=None,
            alternate=make_shortcut("P", ["ALT", "CTRL"]),
        ),
    }

    service.update_configuration(configuration)

    assert calls == [
        {
            "calibration": {
                "primary": {
                    "trigger": "F1",
                    "modifiers": ["CTRL", "SHIFT"],
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
                "primary": None,
                "alternate": {
                    "trigger": "P",
                    "modifiers": ["ALT", "CTRL"],
                },
            },
        },
    ]


def test_service_updates_configuration_when_helper_accepts_it(
    monkeypatch,
):
    service = make_service()

    monkeypatch.setattr(
        service._helper_client,
        "set_shortcut_configuration",
        lambda configuration: None,
    )

    new_configuration = {
        "calibration": ShortcutConfiguration(
            primary=make_shortcut("F2", ["CTRL"]),
        ),
        "next": ShortcutConfiguration(
            primary=make_shortcut("N", ["META"]),
        ),
        "previous": ShortcutConfiguration(),
    }

    service.update_configuration(new_configuration)

    assert service._configuration == new_configuration


def test_service_keeps_configuration_when_helper_update_fails(
    monkeypatch,
):
    service = make_service()

    def fail(_configuration):
        raise HelperClientError

    monkeypatch.setattr(
        service._helper_client,
        "set_shortcut_configuration",
        fail,
    )

    new_configuration = {
        "calibration": ShortcutConfiguration(
            primary=make_shortcut("F2", ["CTRL"]),
        ),
        "next": ShortcutConfiguration(
            primary=make_shortcut("N", ["META"]),
        ),
        "previous": ShortcutConfiguration(),
    }

    service.update_configuration(new_configuration)

    assert service._configuration == new_configuration


def test_service_clears_capture_state_when_helper_capture_stop_fails(
    monkeypatch,
    caplog,
):
    service = make_service()

    capture = object()
    callback = lambda _shortcut: None
    error_callback = lambda _error: None
    rejected_callback = lambda _reason: None

    service._capture = capture
    service._capture_callback = callback
    service._capture_error_callback = error_callback
    service._capture_rejected_callback = rejected_callback

    def fail():
        raise HelperClientError

    monkeypatch.setattr(
        service._helper_client,
        "stop_capture",
        fail,
    )
    monkeypatch.setattr(
        service,
        "_sync_helper_mouse_interception",
        lambda: None,
    )

    with caplog.at_level("WARNING"):
        service.stop_capture()

    assert service._capture is None
    assert service._capture_callback is None
    assert service._capture_error_callback is None
    assert service._capture_rejected_callback is None

    assert "Unable to stop input helper capture cleanly" in caplog.text


def test_service_can_start_capture_again_after_helper_disconnect(
    monkeypatch,
):
    service = make_service()

    service._capture = object()
    service._capture_callback = lambda _shortcut: None
    service._capture_error_callback = lambda _error: None
    service._capture_rejected_callback = lambda _reason: None

    service._handle_helper_disconnect()

    start_calls = []

    monkeypatch.setattr(
        service._helper_client,
        "start_capture",
        start_calls.append,
    )

    callback = lambda _shortcut: None
    error_callback = lambda _error: None
    rejected_callback = lambda _reason: None

    service.start_capture(
        allowed_mouse_buttons=None,
        callback=callback,
        error_callback=error_callback,
        rejected_callback=rejected_callback,
    )

    assert start_calls == [None]
    assert service._capture is not None
    assert service._capture_callback is callback
    assert service._capture_error_callback is error_callback
    assert service._capture_rejected_callback is rejected_callback


def test_service_clears_mouse_grabbed_on_helper_grab_error(
    caplog,
):
    service = make_service(
        configuration={},
    )

    service._mouse_grabbed = True

    with caplog.at_level("ERROR"):
        service._handle_helper_event(
            {
                "type": EVENT_ERROR,
                "code": "device_error",
                "message": "Mouse is already grabbed.",
                "command": COMMAND_GRAB_SELECTED_MOUSE,
            },
        )

    assert service._mouse_grabbed is False
    assert "Input helper error" in caplog.text


def test_service_does_not_clear_mouse_grabbed_on_unrelated_helper_error():
    service = make_service(
        configuration={},
    )

    service._mouse_grabbed = True

    service._handle_helper_event(
        {
            "type": EVENT_ERROR,
            "code": "device_error",
            "message": "Failed to read the selected mouse.",
        },
    )

    assert service._mouse_grabbed is True


def test_service_does_not_clear_mouse_grabbed_on_unrelated_command_error():
    service = make_service(
        configuration={},
    )

    service._mouse_grabbed = True

    service._handle_helper_event(
        {
            "type": EVENT_ERROR,
            "code": "invalid_argument",
            "message": "Invalid shortcut configuration.",
            "command": "set_shortcut_configuration",
        },
    )

    assert service._mouse_grabbed is True


def test_service_resets_helper_state_on_disconnect():
    service = make_service()

    service._selected_mouse = "mouse-1"
    service._mouse_grabbed = True
    service._capture = object()
    service._capture_callback = lambda _shortcut: None
    service._capture_error_callback = lambda _error: None
    service._capture_rejected_callback = lambda _reason: None

    service._handle_helper_disconnect()

    assert service._selected_mouse is None
    assert not service._mouse_grabbed
    assert service._capture is None
    assert service._capture_callback is None
    assert service._capture_error_callback is None
    assert service._capture_rejected_callback is None


def test_service_run_starts_helper_with_current_configuration(
    monkeypatch,
):
    configuration = make_configuration()
    service = make_service(configuration=configuration)

    calls = []
    stop = threading.Event()

    monkeypatch.setattr(
        service._helper_client,
        "connect",
        lambda: calls.append("connect"),
    )
    monkeypatch.setattr(
        service._helper_client,
        "start",
        lambda: calls.append("start"),
    )
    monkeypatch.setattr(
        service._helper_client,
        "set_shortcut_configuration",
        lambda configuration: calls.append(
            ("configuration", configuration),
        ),
    )
    monkeypatch.setattr(
        service._helper_client,
        "is_ready",
        lambda: False,
    )
    monkeypatch.setattr(
        service._helper_client,
        "stop",
        lambda: calls.append("stop"),
    )
    monkeypatch.setattr(
        service._helper_client,
        "disconnect",
        lambda: calls.append("disconnect"),
    )

    service._stop_requested = stop.is_set

    thread = threading.Thread(target=service.run)
    thread.start()

    for _ in range(100):
        if calls[:3] == [
            "connect",
            "start",
            (
                "configuration",
                service._serialize_configuration(configuration),
            ),
        ]:
            break
        time.sleep(0.01)

    stop.set()
    thread.join(timeout=1)

    assert calls[:3] == [
        "connect",
        "start",
        (
            "configuration",
            service._serialize_configuration(configuration),
        ),
    ]
    assert "stop" in calls
    assert "disconnect" in calls


def test_service_run_reconnects_after_helper_disconnect(
    monkeypatch,
):
    configuration = make_configuration()
    service = make_service(configuration=configuration)

    calls = []
    stop = threading.Event()
    first_connection = threading.Event()
    second_connection = threading.Event()
    helper_ready = threading.Event()

    connection_count = 0

    def connect():
        nonlocal connection_count

        connection_count += 1
        calls.append("connect")

        helper_ready.set()

        if connection_count == 1:
            first_connection.set()
        else:
            second_connection.set()

    def start():
        calls.append("start")

    def set_shortcut_configuration(configuration):
        calls.append(
            (
                "configuration",
                configuration,
            ),
        )

    monkeypatch.setattr(
        service._helper_client,
        "connect",
        connect,
    )
    monkeypatch.setattr(
        service._helper_client,
        "start",
        start,
    )
    monkeypatch.setattr(
        service._helper_client,
        "set_shortcut_configuration",
        set_shortcut_configuration,
    )
    monkeypatch.setattr(
        service._helper_client,
        "is_ready",
        helper_ready.is_set,
    )
    monkeypatch.setattr(
        service._helper_client,
        "stop",
        lambda: calls.append("stop"),
    )
    monkeypatch.setattr(
        service._helper_client,
        "disconnect",
        lambda: calls.append("disconnect"),
    )

    service._stop_requested = stop.is_set

    thread = threading.Thread(target=service.run)
    thread.start()

    try:
        assert first_connection.wait(timeout=1)

        expected_configuration = service._serialize_configuration(
            configuration,
        )

        assert calls[:3] == [
            "connect",
            "start",
            ("configuration", expected_configuration),
        ]

        helper_ready.clear()
        service._handle_helper_disconnect()

        assert second_connection.wait(timeout=2)

        assert calls[:6] == [
            "connect",
            "start",
            ("configuration", expected_configuration),
            "connect",
            "start",
            ("configuration", expected_configuration),
        ]
    finally:
        stop.set()
        thread.join(timeout=1)

    assert not thread.is_alive()
    assert calls[-2:] == [
        "stop",
        "disconnect",
    ]


def test_service_run_replays_latest_configuration_after_helper_reconnect(
    monkeypatch,
):
    initial_configuration = make_configuration()
    service = make_service(
        configuration=initial_configuration,
    )

    updated_configuration = {
        "calibration": ShortcutConfiguration(
            primary=make_shortcut("F2", ["CTRL"]),
        ),
        "next": ShortcutConfiguration(
            primary=make_shortcut("N", ["ALT"]),
        ),
        "previous": ShortcutConfiguration(
            primary=make_shortcut("P", ["SHIFT"]),
        ),
    }

    calls = []
    stop = threading.Event()
    first_connection = threading.Event()
    second_connection = threading.Event()
    helper_ready = threading.Event()

    connection_count = 0

    def connect():
        nonlocal connection_count

        connection_count += 1
        calls.append("connect")

        helper_ready.set()

        if connection_count == 1:
            first_connection.set()
        else:
            second_connection.set()

    def start():
        calls.append("start")

    def set_shortcut_configuration(configuration):
        calls.append(
            (
                "configuration",
                configuration,
            ),
        )

    monkeypatch.setattr(
        service._helper_client,
        "connect",
        connect,
    )
    monkeypatch.setattr(
        service._helper_client,
        "start",
        start,
    )
    monkeypatch.setattr(
        service._helper_client,
        "set_shortcut_configuration",
        set_shortcut_configuration,
    )
    monkeypatch.setattr(
        service._helper_client,
        "is_ready",
        helper_ready.is_set,
    )
    monkeypatch.setattr(
        service._helper_client,
        "stop",
        lambda: calls.append("stop"),
    )
    monkeypatch.setattr(
        service._helper_client,
        "disconnect",
        lambda: calls.append("disconnect"),
    )

    service._stop_requested = stop.is_set

    thread = threading.Thread(target=service.run)
    thread.start()

    try:
        assert first_connection.wait(timeout=1)

        initial_serialized = service._serialize_configuration(
            initial_configuration,
        )

        assert calls[:3] == [
            "connect",
            "start",
            ("configuration", initial_serialized),
        ]

        helper_ready.clear()
        service._handle_helper_disconnect()

        service._configuration = updated_configuration

        assert second_connection.wait(timeout=2)

        updated_serialized = service._serialize_configuration(
            updated_configuration,
        )

        assert calls[:6] == [
            "connect",
            "start",
            ("configuration", initial_serialized),
            "connect",
            "start",
            ("configuration", updated_serialized),
        ]
    finally:
        stop.set()
        thread.join(timeout=1)

    assert not thread.is_alive()


def test_service_run_retries_when_helper_is_unavailable(
    monkeypatch,
):
    configuration = make_configuration()
    service = make_service(configuration=configuration)

    calls = []
    stop = threading.Event()
    helper_available = threading.Event()

    connection_attempts = 0

    def connect():
        nonlocal connection_attempts

        connection_attempts += 1
        calls.append("connect")

        if connection_attempts == 1:
            raise HelperClientError(
                "Helper unavailable",
            )

        helper_available.set()

    def start():
        calls.append("start")

    def set_shortcut_configuration(configuration):
        calls.append(
            (
                "configuration",
                configuration,
            ),
        )

    monkeypatch.setattr(
        service._helper_client,
        "connect",
        connect,
    )
    monkeypatch.setattr(
        service._helper_client,
        "start",
        start,
    )
    monkeypatch.setattr(
        service._helper_client,
        "set_shortcut_configuration",
        set_shortcut_configuration,
    )
    monkeypatch.setattr(
        service._helper_client,
        "is_ready",
        lambda: False,
    )
    monkeypatch.setattr(
        service._helper_client,
        "stop",
        lambda: calls.append("stop"),
    )
    monkeypatch.setattr(
        service._helper_client,
        "disconnect",
        lambda: calls.append("disconnect"),
    )

    service._stop_requested = stop.is_set

    thread = threading.Thread(target=service.run)
    thread.start()

    try:
        for _ in range(100):
            if helper_available.is_set():
                break

            time.sleep(0.01)

        assert helper_available.is_set()

        expected_configuration = service._serialize_configuration(
            configuration,
        )

        assert calls[:4] == [
            "connect",
            "connect",
            "start",
            ("configuration", expected_configuration),
        ]
    finally:
        stop.set()
        thread.join(timeout=1)

    assert not thread.is_alive()


def test_service_resyncs_mouse_state_after_helper_disconnect(
    monkeypatch,
):
    service = make_service(
        configuration={
            "next": ShortcutConfiguration(
                primary=make_shortcut("BTN_SIDE"),
            ),
        },
    )

    service._calibrated = True
    service._mouse_interception_enabled = True

    grab_calls = []
    button_calls = []
    interception_calls = []

    monkeypatch.setattr(
        service._helper_client,
        "grab_selected_mouse",
        lambda: grab_calls.append(True),
    )
    monkeypatch.setattr(
        service,
        "_set_helper_intercepted_mouse_buttons",
        button_calls.append,
    )
    monkeypatch.setattr(
        service,
        "_set_helper_mouse_interception",
        interception_calls.append,
    )

    mouse_selected_event = {
        "type": EVENT_MOUSE_SELECTED,
        "device_id": "mouse-1",
    }

    service._handle_helper_event(mouse_selected_event)

    assert service._selected_mouse == "mouse-1"
    assert service._mouse_grabbed is True
    assert grab_calls == [
        True,
    ]
    assert button_calls == [
        {evdev.ecodes.BTN_SIDE},
        {evdev.ecodes.BTN_SIDE},
    ]
    assert interception_calls == [
        True,
    ]

    service._handle_helper_disconnect()

    assert service._selected_mouse is None
    assert service._mouse_grabbed is False

    service._handle_helper_event(mouse_selected_event)

    assert service._selected_mouse == "mouse-1"
    assert service._mouse_grabbed is True
    assert grab_calls == [
        True,
        True,
    ]
    assert button_calls == [
        {evdev.ecodes.BTN_SIDE},
        {evdev.ecodes.BTN_SIDE},
        {evdev.ecodes.BTN_SIDE},
        {evdev.ecodes.BTN_SIDE},
    ]
    assert interception_calls == [
        True,
        True,
    ]
