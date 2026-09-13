import time
from unittest.mock import MagicMock, call

from helper.commands import HelperContext
from helper.hotplug import (
    process_device_changes,
    process_keyboard_selector,
    process_mouse_discovery,
    process_mouse_selector,
)
from helper.protocol import (
    EVENT_KEYBOARD_SELECTED,
    EVENT_KEYBOARD_SELECTED_LOST,
    EVENT_MOUSE_SELECTED,
    EVENT_MOUSE_SELECTED_LOST,
)
from helper.state import HelperState
from input.classifier import DeviceClass


def build_hotplug_context():
    server = MagicMock()
    registry = MagicMock()
    reader = MagicMock()
    keyboard_selector = MagicMock()
    mouse_selector = MagicMock()
    keyboard_state = MagicMock()
    xkb = MagicMock()

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

    return context, state


def build_device(
    device_id,
    device_class,
):
    device = MagicMock()
    device.device_id = device_id
    device.device_class = device_class
    return device


def build_keyboard(device_id="keyboard-1"):
    keyboard = build_device(
        device_id,
        DeviceClass.KEYBOARD,
    )
    keyboard.info.name = "Test Keyboard"
    return keyboard


def build_mouse(device_id="mouse-1"):
    mouse = build_device(
        device_id,
        DeviceClass.MOUSE,
    )
    mouse.info.name = "Test Mouse"
    return mouse


def configure_selector_selection(
    selector,
    device,
    events=None,
    fd=42,
):
    selector.get_watched_fds.return_value = [fd]

    def process_ready(ready_fds):
        if ready_fds == [fd]:
            return device, events or []
        return None

    selector.process_ready.side_effect = process_ready


def test_process_keyboard_selector_selects_keyboard_and_registers_new_events():
    context, state = build_hotplug_context()

    keyboard = build_keyboard()
    event = MagicMock()

    context.keyboard_selector.is_active.return_value = True
    configure_selector_selection(
        context.keyboard_selector,
        keyboard,
        [event],
    )

    context.reader.get_watched_fds.side_effect = [
        [10],
        [10, 20],
    ]

    selected_events = []

    new_reader_fds = process_keyboard_selector(
        context,
        state,
        [42],
        selected_events,
    )

    assert state.selected_keyboard is keyboard
    assert selected_events == [(keyboard, event)]
    assert new_reader_fds == {20}

    context.reader.add_device.assert_called_once_with(keyboard)

    context.server.send_event.assert_called_once_with(
        {
            "type": EVENT_KEYBOARD_SELECTED,
            "device_id": "keyboard-1",
        }
    )


def test_process_keyboard_selector_does_nothing_without_selection():
    context, state = build_hotplug_context()

    context.keyboard_selector.is_active.return_value = True
    context.keyboard_selector.get_watched_fds.return_value = [42]
    context.keyboard_selector.process_ready.return_value = None

    selected_events = []

    new_reader_fds = process_keyboard_selector(
        context,
        state,
        [42],
        selected_events,
    )

    assert state.selected_keyboard is None
    assert selected_events == []
    assert new_reader_fds == set()

    context.reader.add_device.assert_not_called()
    context.server.send_event.assert_not_called()


def test_process_mouse_selector_selects_mouse_and_clears_pending_discovery():
    context, state = build_hotplug_context()

    mouse = build_mouse()

    state.next_mouse_discovery = 10.0

    context.mouse_selector.is_active.return_value = True
    configure_selector_selection(
        context.mouse_selector,
        mouse,
    )

    selected_events = []

    process_mouse_selector(
        context,
        state,
        [42],
        None,
        selected_events,
    )

    assert state.selected_mouse is mouse
    assert state.next_mouse_discovery is None
    assert selected_events == []

    context.server.send_event.assert_called_once_with(
        {
            "type": EVENT_MOUSE_SELECTED,
            "device_id": "mouse-1",
        }
    )


def test_process_mouse_selector_schedules_discovery_after_timeout(
    monkeypatch,
):
    context, state = build_hotplug_context()

    state.input_monitoring_active = True

    context.mouse_selector.is_active.return_value = True
    context.mouse_selector.get_watched_fds.return_value = []
    context.mouse_selector.process_ready.return_value = None

    monkeypatch.setattr(
        time,
        "monotonic",
        MagicMock(return_value=10.0),
    )

    process_mouse_selector(
        context,
        state,
        [],
        0.0,
        [],
    )

    assert state.next_mouse_discovery == 11.0
    context.mouse_selector.stop.assert_called_once_with()


def test_process_mouse_selector_ignores_inactive_or_unexpired_selector():
    context, state = build_hotplug_context()

    context.mouse_selector.is_active.return_value = False

    process_mouse_selector(
        context,
        state,
        [42],
        0.0,
        [],
    )

    context.mouse_selector.process_ready.assert_not_called()
    context.mouse_selector.stop.assert_not_called()

    context.mouse_selector.reset_mock()
    context.mouse_selector.is_active.return_value = True
    context.mouse_selector.get_watched_fds.return_value = []
    context.mouse_selector.process_ready.return_value = None

    process_mouse_selector(
        context,
        state,
        [],
        1.0,
        [],
    )

    context.mouse_selector.stop.assert_not_called()
    assert state.next_mouse_discovery is None


def test_process_mouse_discovery_restarts_selection_when_retry_is_due(
    monkeypatch,
):
    context, state = build_hotplug_context()

    mouse = build_mouse()

    state.input_monitoring_active = True
    state.next_mouse_discovery = 1.0

    context.mouse_selector.is_active.return_value = False
    context.registry.reconcile.return_value = (
        [mouse],
        [],
        [mouse],
    )

    monkeypatch.setattr(
        "helper.hotplug.discover_devices",
        MagicMock(return_value=[mouse]),
    )
    monkeypatch.setattr(
        time,
        "monotonic",
        MagicMock(return_value=2.0),
    )

    process_mouse_discovery(
        context,
        state,
    )

    assert state.next_mouse_discovery is None

    context.registry.reconcile.assert_called_once_with(
        [mouse],
    )
    context.mouse_selector.start.assert_called_once_with(
        [mouse],
    )


def test_process_mouse_discovery_waits_when_retry_is_not_ready(
    monkeypatch,
):
    context, state = build_hotplug_context()

    state.input_monitoring_active = True
    state.next_mouse_discovery = 10.0

    context.mouse_selector.is_active.return_value = False

    monkeypatch.setattr(
        time,
        "monotonic",
        MagicMock(return_value=5.0),
    )

    process_mouse_discovery(
        context,
        state,
    )

    context.registry.reconcile.assert_not_called()
    context.mouse_selector.start.assert_not_called()


def test_process_device_changes_handles_keyboard_removal_and_mouse_reselection(
    monkeypatch,
):
    context, state = build_hotplug_context()

    old_keyboard = build_keyboard("old-keyboard")
    old_mouse = build_mouse("old-mouse")
    new_keyboard = build_keyboard("new-keyboard")
    new_mouse = build_mouse("new-mouse")

    state.input_monitoring_active = True
    state.selected_keyboard = old_keyboard
    state.selected_mouse = old_mouse

    context.reader.get_device_monitor_fd.return_value = 77
    context.reader.device_changes_pending.return_value = True

    context.registry.reconcile.return_value = (
        [new_keyboard, new_mouse],
        [old_keyboard, old_mouse],
        [new_keyboard, new_mouse],
    )

    monkeypatch.setattr(
        "helper.hotplug.discover_devices",
        MagicMock(
            return_value=[new_keyboard, new_mouse],
        ),
    )
    monkeypatch.setattr(
        "helper.hotplug.stop_mouse_interception",
        MagicMock(),
    )

    process_device_changes(
        context,
        state,
        [77],
    )

    assert state.selected_keyboard is None
    assert state.selected_mouse is None
    assert state.mouse_interceptor is None
    assert state.next_mouse_discovery is not None

    context.reader.remove_device.assert_any_call(
        old_keyboard.device_id,
    )
    context.reader.remove_device.assert_any_call(
        old_mouse.device_id,
    )

    context.keyboard_selector.start.assert_called_once_with(
        [new_keyboard],
    )
    context.mouse_selector.stop.assert_called_once_with()

    assert context.server.send_event.call_args_list == [
        call(
            {
                "type": EVENT_KEYBOARD_SELECTED_LOST,
            }
        ),
        call(
            {
                "type": EVENT_MOUSE_SELECTED_LOST,
            }
        ),
    ]


def test_process_device_changes_stops_mouse_grabber_when_selected_mouse_is_removed(
    monkeypatch,
):
    context, state = build_hotplug_context()

    old_mouse = build_mouse("old-mouse")
    new_mouse = build_mouse("new-mouse")
    grabber = MagicMock()

    state.input_monitoring_active = True
    state.selected_mouse = old_mouse
    state.mouse_grabber = grabber

    context.reader.get_device_monitor_fd.return_value = 77
    context.reader.device_changes_pending.return_value = True

    context.registry.reconcile.return_value = (
        [new_mouse],
        [old_mouse],
        [new_mouse],
    )

    monkeypatch.setattr(
        "helper.hotplug.discover_devices",
        MagicMock(return_value=[new_mouse]),
    )
    stop_interception = MagicMock()
    monkeypatch.setattr(
        "helper.hotplug.stop_mouse_interception",
        stop_interception,
    )

    process_device_changes(
        context,
        state,
        [77],
    )

    stop_interception.assert_called_once_with(
        context.server,
        old_mouse,
        None,
    )
    grabber.stop.assert_called_once_with()

    assert state.mouse_grabber is None
    assert state.selected_mouse is None
    assert state.mouse_interceptor is None
    assert state.next_mouse_discovery is not None


def test_process_device_changes_starts_selection_when_no_mouse_is_selected(
    monkeypatch,
):
    context, state = build_hotplug_context()

    mouse = build_mouse()

    state.input_monitoring_active = True
    state.selected_mouse = None

    context.reader.get_device_monitor_fd.return_value = 77
    context.reader.device_changes_pending.return_value = True

    context.registry.reconcile.return_value = (
        [mouse],
        [],
        [mouse],
    )

    monkeypatch.setattr(
        "helper.hotplug.discover_devices",
        MagicMock(return_value=[mouse]),
    )

    process_device_changes(
        context,
        state,
        [77],
    )

    context.mouse_selector.stop.assert_called_once_with()
    context.mouse_selector.start.assert_called_once_with(
        [mouse],
    )

    assert state.selected_mouse is None
    assert state.next_mouse_discovery is None


def test_process_device_changes_ignores_unrelated_reader_activity():
    context, state = build_hotplug_context()

    state.input_monitoring_active = True

    context.reader.get_device_monitor_fd.return_value = 77
    context.reader.device_changes_pending.return_value = True

    process_device_changes(
        context,
        state,
        [42],
    )

    context.reader.device_changes_pending.assert_not_called()
    context.registry.reconcile.assert_not_called()
