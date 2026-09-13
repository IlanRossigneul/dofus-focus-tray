from unittest.mock import MagicMock

from helper.devices import HelperDevice
from helper.events import InputEventReader
from input.classifier import DeviceClass
from input.discovery import InputDeviceInfo


def make_device(device_id: str, path: str) -> HelperDevice:
    info = InputDeviceInfo(
        path=path,
        name=f"Test Device {device_id}",
        phys=f"usb-test/{device_id}",
        uniq=device_id,
        vendor=0x1234,
        product=0x5678,
        bus=0x03,
        capabilities={
            1: [30, 31, 32],
        },
    )

    return HelperDevice(
        device_id=device_id,
        info=info,
        device_class=DeviceClass.KEYBOARD,
    )


def test_add_device_opens_and_tracks_device(monkeypatch):
    device = make_device("keyboard-1", "/dev/input/event1")
    input_device = MagicMock()
    input_device.fileno.return_value = 10

    monkeypatch.setattr(
        "helper.events.evdev.InputDevice",
        lambda path: input_device,
    )

    reader = InputEventReader()
    reader.add_device(device)

    assert reader.get_watched_fds() == [10]
    input_device.close.assert_not_called()


def test_add_device_ignores_already_tracked_device(monkeypatch):
    device = make_device("keyboard-1", "/dev/input/event1")
    input_device = MagicMock()
    input_device.fileno.return_value = 10

    create_calls = []

    def create_input_device(path):
        create_calls.append(path)
        return input_device

    monkeypatch.setattr(
        "helper.events.evdev.InputDevice",
        create_input_device,
    )

    reader = InputEventReader()
    reader.add_device(device)
    reader.add_device(device)

    assert create_calls == [device.info.path]
    assert reader.get_watched_fds() == [10]


def test_add_device_ignores_open_failure(monkeypatch):
    device = make_device("keyboard-1", "/dev/input/event1")

    monkeypatch.setattr(
        "helper.events.evdev.InputDevice",
        lambda path: (_ for _ in ()).throw(PermissionError),
    )

    reader = InputEventReader()
    reader.add_device(device)

    assert reader.get_watched_fds() == []


def test_remove_device_closes_and_untracks_device(monkeypatch):
    device = make_device("keyboard-1", "/dev/input/event1")
    input_device = MagicMock()
    input_device.fileno.return_value = 10

    monkeypatch.setattr(
        "helper.events.evdev.InputDevice",
        lambda path: input_device,
    )

    reader = InputEventReader()
    reader.add_device(device)
    reader.remove_device(device.device_id)

    assert reader.get_watched_fds() == []
    input_device.close.assert_called_once()


def test_remove_device_ignores_unknown_device():
    reader = InputEventReader()

    reader.remove_device("unknown-device")

    assert reader.get_watched_fds() == []


def test_sync_devices_adds_missing_devices(monkeypatch):
    devices = [
        make_device("keyboard-1", "/dev/input/event1"),
        make_device("keyboard-2", "/dev/input/event2"),
    ]

    input_devices = []

    def create_input_device(path):
        input_device = MagicMock()
        input_device.fileno.return_value = len(input_devices) + 10
        input_devices.append(input_device)
        return input_device

    monkeypatch.setattr(
        "helper.events.evdev.InputDevice",
        create_input_device,
    )

    reader = InputEventReader()
    reader.sync_devices(devices)

    assert reader.get_watched_fds() == [10, 11]
    assert len(input_devices) == 2


def test_sync_devices_removes_missing_devices(monkeypatch):
    device = make_device("keyboard-1", "/dev/input/event1")
    input_device = MagicMock()
    input_device.fileno.return_value = 10

    monkeypatch.setattr(
        "helper.events.evdev.InputDevice",
        lambda path: input_device,
    )

    reader = InputEventReader()
    reader.add_device(device)
    reader.sync_devices([])

    assert reader.get_watched_fds() == []
    input_device.close.assert_called_once()


def test_sync_devices_preserves_existing_device(monkeypatch):
    device = make_device("keyboard-1", "/dev/input/event1")
    rediscovered_device = make_device(
        "keyboard-1",
        "/dev/input/event1",
    )

    input_device = MagicMock()
    input_device.fileno.return_value = 10

    create_calls = []

    def create_input_device(path):
        create_calls.append(path)
        return input_device

    monkeypatch.setattr(
        "helper.events.evdev.InputDevice",
        create_input_device,
    )

    reader = InputEventReader()
    reader.add_device(device)
    reader.sync_devices([rediscovered_device])

    assert create_calls == [device.info.path]
    assert reader.get_watched_fds() == [10]
    input_device.close.assert_not_called()


def test_read_ready_reads_events():
    device = make_device("keyboard-1", "/dev/input/event1")
    input_device = MagicMock()
    event = MagicMock()
    input_device.read.return_value = [event]

    reader = InputEventReader()
    reader._input_devices[device.device_id] = input_device
    reader._info_by_fd[10] = device
    reader._fd_by_device_id[device.device_id] = 10

    events = list(reader.read_ready([10]))

    assert events == [(device, event)]


def test_read_ready_ignores_unknown_fd():
    reader = InputEventReader()

    assert list(reader.read_ready([10])) == []


def test_read_ready_removes_device_after_read_error():
    device = make_device("keyboard-1", "/dev/input/event1")
    input_device = MagicMock()
    input_device.read.side_effect = OSError("device disconnected")

    reader = InputEventReader()
    reader._input_devices[device.device_id] = input_device
    reader._info_by_fd[10] = device
    reader._fd_by_device_id[device.device_id] = 10

    events = list(reader.read_ready([10]))

    assert events == []
    assert device.device_id not in reader._input_devices
    assert 10 not in reader._info_by_fd
    assert device.device_id not in reader._fd_by_device_id


def test_start_device_monitor(monkeypatch):
    monitor = MagicMock()

    monkeypatch.setattr(
        "helper.events.pyudev.Context",
        MagicMock(),
    )
    monkeypatch.setattr(
        "helper.events.pyudev.Monitor.from_netlink",
        MagicMock(return_value=monitor),
    )

    reader = InputEventReader()
    reader.start_device_monitor()

    monitor.filter_by.assert_called_once_with(subsystem="input")
    monitor.start.assert_called_once()
    assert reader.get_device_monitor_fd() == monitor.fileno.return_value


def test_start_device_monitor_is_idempotent(monkeypatch):
    monitor = MagicMock()
    from_netlink = MagicMock(return_value=monitor)

    monkeypatch.setattr(
        "helper.events.pyudev.Context",
        MagicMock(),
    )
    monkeypatch.setattr(
        "helper.events.pyudev.Monitor.from_netlink",
        from_netlink,
    )

    reader = InputEventReader()
    reader.start_device_monitor()
    reader.start_device_monitor()

    from_netlink.assert_called_once()
    monitor.start.assert_called_once()


def test_get_device_monitor_fd_without_monitor():
    reader = InputEventReader()

    assert reader.get_device_monitor_fd() is None


def test_device_changes_pending_without_monitor():
    reader = InputEventReader()

    assert reader.device_changes_pending() is False


def test_device_changes_pending_without_changes():
    monitor = MagicMock()
    monitor.poll.return_value = None

    reader = InputEventReader()
    reader._device_monitor = monitor

    assert reader.device_changes_pending() is False
    monitor.poll.assert_called_once_with(timeout=0)


def test_device_changes_pending_with_changes():
    monitor = MagicMock()
    monitor.poll.side_effect = [object(), object(), None]

    reader = InputEventReader()
    reader._device_monitor = monitor

    assert reader.device_changes_pending() is True
    assert monitor.poll.call_count == 3


def test_close_closes_all_devices():
    devices = [
        make_device("keyboard-1", "/dev/input/event1"),
        make_device("keyboard-2", "/dev/input/event2"),
    ]

    input_devices = [
        MagicMock(),
        MagicMock(),
    ]

    reader = InputEventReader()

    for device, input_device, fd in zip(
        devices,
        input_devices,
        [10, 11],
        strict=True,
    ):
        reader._input_devices[device.device_id] = input_device
        reader._info_by_fd[fd] = device
        reader._fd_by_device_id[device.device_id] = fd

    reader.close()

    assert reader.get_watched_fds() == []

    for input_device in input_devices:
        input_device.close.assert_called_once()

    assert reader.get_device_monitor_fd() is None
