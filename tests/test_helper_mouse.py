import errno
from unittest.mock import MagicMock

import evdev
import pytest

from helper.devices import HelperDevice
from helper.mouse import (
    VIRTUAL_MOUSE_NAME,
    VIRTUAL_MOUSE_PHYS,
    MouseGrabber,
    MouseInterceptor,
    MouseSelector,
)
from input.classifier import DeviceClass
from input.discovery import InputDeviceInfo


def make_mouse(
    path: str = "/dev/input/event42",
    device_id: str = "mouse-1",
) -> HelperDevice:
    info = InputDeviceInfo(
        path=path,
        name="Test Mouse",
        phys="usb-test/mouse0",
        uniq="1234",
        vendor=0x1234,
        product=0x5678,
        bus=0x03,
        capabilities={
            evdev.ecodes.EV_KEY: [
                evdev.ecodes.BTN_LEFT,
                evdev.ecodes.BTN_RIGHT,
                evdev.ecodes.BTN_SIDE,
                evdev.ecodes.BTN_EXTRA,
            ],
            evdev.ecodes.EV_REL: [
                evdev.ecodes.REL_X,
                evdev.ecodes.REL_Y,
            ],
        },
    )

    return HelperDevice(
        device_id=device_id,
        info=info,
        device_class=DeviceClass.MOUSE,
    )


def make_grabber(physical_device=None):
    grabber = MagicMock(spec=MouseGrabber)

    if physical_device is None:
        grabber.get_device.side_effect = RuntimeError(
            "Mouse grabber is not started.",
        )
    else:
        grabber.get_device.return_value = physical_device

    return grabber


def test_mouse_selector_is_inactive_initially():
    selector = MouseSelector()

    assert selector.is_active() is False
    assert selector.get_watched_fds() == []
    assert selector.remaining_timeout() is None


def test_mouse_selector_start_opens_candidate_mice(monkeypatch):
    mice = [
        make_mouse("/dev/input/event1", "mouse-1"),
        make_mouse("/dev/input/event2", "mouse-2"),
    ]

    input_devices = []

    def create_input_device(path):
        input_device = MagicMock()
        input_device.fileno.return_value = len(input_devices) + 10
        input_devices.append(input_device)
        return input_device

    monkeypatch.setattr(
        "helper.mouse.evdev.InputDevice",
        create_input_device,
    )

    selector = MouseSelector()

    selector.start(mice)

    assert selector.is_active() is True
    assert selector.get_watched_fds() == [10, 11]
    assert len(input_devices) == 2

    for input_device in input_devices:
        input_device.close.assert_not_called()


def test_mouse_selector_start_is_resettable(monkeypatch):
    mouse = make_mouse()

    first_device = MagicMock()
    first_device.fileno.return_value = 10

    second_device = MagicMock()
    second_device.fileno.return_value = 11

    input_devices = iter([first_device, second_device])

    monkeypatch.setattr(
        "helper.mouse.evdev.InputDevice",
        lambda path: next(input_devices),
    )

    selector = MouseSelector()

    selector.start([mouse])
    selector.start([mouse])

    first_device.close.assert_called_once()
    assert selector.get_watched_fds() == [11]


def test_mouse_selector_start_with_no_mice():
    selector = MouseSelector()

    selector.start([])

    assert selector.is_active() is False
    assert selector.get_watched_fds() == []
    assert selector.remaining_timeout() is None


def test_mouse_selector_skips_device_when_open_fails(monkeypatch):
    mouse = make_mouse()

    monkeypatch.setattr(
        "helper.mouse.evdev.InputDevice",
        MagicMock(side_effect=PermissionError),
    )

    selector = MouseSelector()

    selector.start([mouse])

    assert selector.is_active() is False
    assert selector.get_watched_fds() == []
    assert selector.remaining_timeout() is None


def test_mouse_selector_add_device(monkeypatch):
    mouse = make_mouse()

    input_device = MagicMock()
    input_device.fileno.return_value = 42

    monkeypatch.setattr(
        "helper.mouse.evdev.InputDevice",
        lambda path: input_device,
    )

    selector = MouseSelector()

    selector.add_device(mouse)

    assert selector.is_active() is True
    assert selector.get_watched_fds() == [42]
    assert selector.remaining_timeout() is not None


def test_mouse_selector_add_device_is_idempotent(monkeypatch):
    mouse = make_mouse()

    input_device = MagicMock()
    input_device.fileno.return_value = 42

    input_device_factory = MagicMock(return_value=input_device)

    monkeypatch.setattr(
        "helper.mouse.evdev.InputDevice",
        input_device_factory,
    )

    selector = MouseSelector()

    selector.add_device(mouse)
    selector.add_device(mouse)

    input_device_factory.assert_called_once_with(mouse.info.path)


def test_mouse_selector_remove_device_closes_device(monkeypatch):
    mouse = make_mouse()

    input_device = MagicMock()
    input_device.fileno.return_value = 42

    monkeypatch.setattr(
        "helper.mouse.evdev.InputDevice",
        lambda path: input_device,
    )

    selector = MouseSelector()
    selector.add_device(mouse)
    selector.remove_device(mouse.device_id)

    input_device.close.assert_called_once()
    assert selector.is_active() is False
    assert selector.get_watched_fds() == []


def test_mouse_selector_remove_unknown_device_is_safe():
    selector = MouseSelector()

    selector.remove_device("unknown")

    assert selector.is_active() is False


def test_mouse_selector_selects_mouse_on_relative_event(monkeypatch):
    mouse = make_mouse()

    input_device = MagicMock()
    input_device.fileno.return_value = 42

    event = MagicMock()
    event.type = evdev.ecodes.EV_REL
    event.code = evdev.ecodes.REL_X
    event.value = 5

    input_device.read.return_value = [event]

    monkeypatch.setattr(
        "helper.mouse.evdev.InputDevice",
        lambda path: input_device,
    )

    selector = MouseSelector()
    selector.start([mouse])

    selected = selector.process_ready([42])

    assert selected is not None
    selected_mouse, selected_events = selected

    assert selected_mouse == mouse
    assert selected_events == [event]
    assert selector.is_active() is False
    input_device.close.assert_called_once()


@pytest.mark.parametrize(
    "button_code",
    [
        evdev.ecodes.BTN_LEFT,
        evdev.ecodes.BTN_RIGHT,
        evdev.ecodes.BTN_MIDDLE,
        evdev.ecodes.BTN_SIDE,
        evdev.ecodes.BTN_EXTRA,
    ],
)
def test_mouse_selector_selects_mouse_on_mouse_button_event(
    monkeypatch,
    button_code,
):
    mouse = make_mouse()

    input_device = MagicMock()
    input_device.fileno.return_value = 42

    event = MagicMock()
    event.type = evdev.ecodes.EV_KEY
    event.code = button_code
    event.value = 1

    input_device.read.return_value = [event]

    monkeypatch.setattr(
        "helper.mouse.evdev.InputDevice",
        lambda path: input_device,
    )

    selector = MouseSelector()
    selector.start([mouse])

    selected = selector.process_ready([42])

    assert selected is not None
    selected_mouse, selected_events = selected

    assert selected_mouse == mouse
    assert selected_events == [event]
    assert selector.is_active() is False
    input_device.close.assert_called_once()


def test_mouse_selector_ignores_non_mouse_events(monkeypatch):
    mouse = make_mouse()

    input_device = MagicMock()
    input_device.fileno.return_value = 42

    event = MagicMock()
    event.type = evdev.ecodes.EV_KEY
    event.code = evdev.ecodes.KEY_A
    event.value = 1

    input_device.read.return_value = [event]

    monkeypatch.setattr(
        "helper.mouse.evdev.InputDevice",
        lambda path: input_device,
    )

    selector = MouseSelector()
    selector.start([mouse])

    assert selector.process_ready([42]) is None
    assert selector.is_active() is True


def test_mouse_selector_ignores_unknown_fd(monkeypatch):
    mouse = make_mouse()

    input_device = MagicMock()
    input_device.fileno.return_value = 42

    monkeypatch.setattr(
        "helper.mouse.evdev.InputDevice",
        lambda path: input_device,
    )

    selector = MouseSelector()
    selector.start([mouse])

    assert selector.process_ready([99]) is None
    input_device.read.assert_not_called()
    assert selector.is_active() is True


def test_mouse_selector_removes_device_when_read_fails(monkeypatch):
    mouse = make_mouse()

    input_device = MagicMock()
    input_device.fileno.return_value = 42
    input_device.read.side_effect = OSError("Device disappeared")

    monkeypatch.setattr(
        "helper.mouse.evdev.InputDevice",
        lambda path: input_device,
    )

    selector = MouseSelector()
    selector.start([mouse])

    assert selector.process_ready([42]) is None

    input_device.close.assert_called_once()
    assert selector.is_active() is False


def test_mouse_selector_closes_all_devices_on_stop(monkeypatch):
    mice = [
        make_mouse("/dev/input/event1", "mouse-1"),
        make_mouse("/dev/input/event2", "mouse-2"),
    ]

    input_devices = []

    def create_input_device(path):
        input_device = MagicMock()
        input_device.fileno.return_value = len(input_devices) + 10
        input_devices.append(input_device)
        return input_device

    monkeypatch.setattr(
        "helper.mouse.evdev.InputDevice",
        create_input_device,
    )

    selector = MouseSelector()
    selector.start(mice)
    selector.stop()

    for input_device in input_devices:
        input_device.close.assert_called_once()

    assert selector.is_active() is False
    assert selector.get_watched_fds() == []
    assert selector.remaining_timeout() is None


def test_mouse_selector_remaining_timeout_uses_deadline(monkeypatch):
    mouse = make_mouse()

    input_device = MagicMock()
    input_device.fileno.return_value = 42

    monkeypatch.setattr(
        "helper.mouse.evdev.InputDevice",
        lambda path: input_device,
    )
    monkeypatch.setattr(
        "helper.mouse.time.monotonic",
        MagicMock(side_effect=[100.0, 102.0]),
    )

    selector = MouseSelector(timeout=5.0)
    selector.start([mouse])

    assert selector.remaining_timeout() == 3.0


def test_mouse_selector_remaining_timeout_reaches_zero(monkeypatch):
    mouse = make_mouse()

    input_device = MagicMock()
    input_device.fileno.return_value = 42

    monkeypatch.setattr(
        "helper.mouse.evdev.InputDevice",
        lambda path: input_device,
    )
    monkeypatch.setattr(
        "helper.mouse.time.monotonic",
        MagicMock(side_effect=[100.0, 106.0]),
    )

    selector = MouseSelector(timeout=5.0)
    selector.start([mouse])

    assert selector.remaining_timeout() == 0.0


def test_mouse_selector_can_add_mouse_after_selection_started(
    monkeypatch,
):
    mouse1 = make_mouse(
        "/dev/input/event1",
        "mouse-1",
    )
    mouse2 = make_mouse(
        "/dev/input/event2",
        "mouse-2",
    )

    input_devices = []

    def create_input_device(path):
        input_device = MagicMock()
        input_device.fileno.return_value = len(input_devices) + 10
        input_devices.append(input_device)
        return input_device

    monkeypatch.setattr(
        "helper.mouse.evdev.InputDevice",
        create_input_device,
    )

    selector = MouseSelector(timeout=5.0)
    selector.start([mouse1])
    selector.add_device(mouse2)

    assert selector.get_watched_fds() == [10, 11]
    assert selector.is_active() is True


def test_mouse_selector_removing_last_device_clears_timeout(
    monkeypatch,
):
    mouse = make_mouse()

    input_device = MagicMock()
    input_device.fileno.return_value = 42

    monkeypatch.setattr(
        "helper.mouse.evdev.InputDevice",
        lambda path: input_device,
    )

    selector = MouseSelector()
    selector.start([mouse])
    selector.remove_device(mouse.device_id)

    assert selector.remaining_timeout() is None


def test_mouse_interceptor_is_not_started_initially():
    interceptor = MouseInterceptor(
        make_grabber(),
        {evdev.ecodes.BTN_SIDE},
    )

    assert interceptor.is_started() is False


def test_mouse_interceptor_start_creates_virtual_device(
    monkeypatch,
):
    physical_device = MagicMock()
    virtual_device = MagicMock()
    grabber = make_grabber(physical_device)

    monkeypatch.setattr(
        "helper.mouse.evdev.UInput.from_device",
        MagicMock(return_value=virtual_device),
    )

    interceptor = MouseInterceptor(
        grabber,
        {evdev.ecodes.BTN_SIDE},
    )

    assert interceptor.start() is True
    assert interceptor.is_started() is True

    grabber.get_device.assert_called_once()

    evdev.UInput.from_device.assert_called_once_with(
        physical_device,
        name=VIRTUAL_MOUSE_NAME,
        phys=VIRTUAL_MOUSE_PHYS,
    )


def test_mouse_interceptor_start_is_idempotent(
    monkeypatch,
):
    physical_device = MagicMock()
    virtual_device = MagicMock()
    grabber = make_grabber(physical_device)

    monkeypatch.setattr(
        "helper.mouse.evdev.UInput.from_device",
        MagicMock(return_value=virtual_device),
    )

    interceptor = MouseInterceptor(
        grabber,
        {evdev.ecodes.BTN_SIDE},
    )

    assert interceptor.start() is True
    assert interceptor.start() is True

    evdev.UInput.from_device.assert_called_once()
    grabber.get_device.assert_called_once()


def test_mouse_interceptor_returns_false_when_uinput_creation_fails(
    monkeypatch,
):
    physical_device = MagicMock()
    error = OSError(errno.ENODEV, "No such device")
    grabber = make_grabber(physical_device)

    monkeypatch.setattr(
        "helper.mouse.evdev.UInput.from_device",
        MagicMock(side_effect=error),
    )

    interceptor = MouseInterceptor(
        grabber,
        {evdev.ecodes.BTN_SIDE},
    )

    assert interceptor.start() is False
    assert interceptor.is_started() is False


def test_mouse_interceptor_stop_closes_virtual_device(
    monkeypatch,
):
    physical_device = MagicMock()
    virtual_device = MagicMock()
    grabber = make_grabber(physical_device)

    monkeypatch.setattr(
        "helper.mouse.evdev.UInput.from_device",
        MagicMock(return_value=virtual_device),
    )

    interceptor = MouseInterceptor(
        grabber,
        {evdev.ecodes.BTN_SIDE},
    )

    interceptor.start()
    interceptor.stop()

    virtual_device.close.assert_called_once()
    grabber.get_device.assert_called_once()

    assert interceptor.is_started() is False


def test_mouse_interceptor_stop_is_safe_when_not_started():
    interceptor = MouseInterceptor(
        make_grabber(),
        {evdev.ecodes.BTN_SIDE},
    )

    interceptor.stop()

    assert interceptor.is_started() is False


def test_mouse_interceptor_fileno_requires_started_interceptor():
    interceptor = MouseInterceptor(
        make_grabber(),
        {evdev.ecodes.BTN_SIDE},
    )

    with pytest.raises(
        RuntimeError,
        match="Mouse grabber is not started",
    ):
        interceptor.fileno()


def test_mouse_interceptor_fileno_returns_physical_device_fd():
    physical_device = MagicMock()
    physical_device.fileno.return_value = 42
    grabber = make_grabber(physical_device)

    interceptor = MouseInterceptor(
        grabber,
        {evdev.ecodes.BTN_SIDE},
    )

    assert interceptor.fileno() == 42


def test_mouse_interceptor_read_requires_started_interceptor():
    interceptor = MouseInterceptor(
        make_grabber(),
        {evdev.ecodes.BTN_SIDE},
    )

    with pytest.raises(
        RuntimeError,
        match="Mouse grabber is not started",
    ):
        interceptor.read()


def test_mouse_interceptor_read_returns_physical_device_events():
    physical_device = MagicMock()
    events = [MagicMock(), MagicMock()]
    physical_device.read.return_value = events
    grabber = make_grabber(physical_device)

    interceptor = MouseInterceptor(
        grabber,
        {evdev.ecodes.BTN_SIDE},
    )

    assert interceptor.read() == events


def test_mouse_interceptor_updates_intercepted_buttons():
    interceptor = MouseInterceptor(
        make_grabber(),
        {evdev.ecodes.BTN_SIDE},
    )

    interceptor.update_intercepted_buttons(
        {evdev.ecodes.BTN_EXTRA},
    )

    side_event = MagicMock()
    side_event.type = evdev.ecodes.EV_KEY
    side_event.code = evdev.ecodes.BTN_SIDE
    side_event.value = 1

    extra_event = MagicMock()
    extra_event.type = evdev.ecodes.EV_KEY
    extra_event.code = evdev.ecodes.BTN_EXTRA
    extra_event.value = 1

    assert interceptor.should_intercept(side_event) is False
    assert interceptor.should_intercept(extra_event) is True


@pytest.mark.parametrize(
    ("event_type", "event_code", "event_value", "expected"),
    [
        (
            evdev.ecodes.EV_KEY,
            evdev.ecodes.BTN_SIDE,
            1,
            True,
        ),
        (
            evdev.ecodes.EV_KEY,
            evdev.ecodes.BTN_SIDE,
            0,
            True,
        ),
        (
            evdev.ecodes.EV_KEY,
            evdev.ecodes.BTN_SIDE,
            2,
            False,
        ),
        (
            evdev.ecodes.EV_KEY,
            evdev.ecodes.BTN_LEFT,
            1,
            False,
        ),
        (
            evdev.ecodes.EV_REL,
            evdev.ecodes.REL_X,
            1,
            False,
        ),
    ],
)
def test_mouse_interceptor_should_intercept(
    event_type,
    event_code,
    event_value,
    expected,
):
    interceptor = MouseInterceptor(
        make_grabber(),
        {evdev.ecodes.BTN_SIDE},
    )

    event = MagicMock()
    event.type = event_type
    event.code = event_code
    event.value = event_value

    assert interceptor.should_intercept(event) is expected


def test_mouse_interceptor_forward_event_writes_and_syncs_event(
    monkeypatch,
):
    physical_device = MagicMock()
    virtual_device = MagicMock()
    grabber = make_grabber(physical_device)

    monkeypatch.setattr(
        "helper.mouse.evdev.UInput.from_device",
        MagicMock(return_value=virtual_device),
    )

    interceptor = MouseInterceptor(
        grabber,
        {evdev.ecodes.BTN_SIDE},
    )

    interceptor.start()

    event = MagicMock()
    interceptor.forward_event(event)

    virtual_device.write_event.assert_called_once_with(event)
    virtual_device.syn.assert_called_once()


def test_mouse_interceptor_forward_event_requires_started_interceptor():
    interceptor = MouseInterceptor(
        make_grabber(),
        {evdev.ecodes.BTN_SIDE},
    )

    with pytest.raises(
        RuntimeError,
        match="Mouse interceptor is not started",
    ):
        interceptor.forward_event(MagicMock())


def test_mouse_grabber_start_and_get_device(monkeypatch):
    mouse = make_mouse()
    physical_device = MagicMock()

    input_device = MagicMock(return_value=physical_device)
    monkeypatch.setattr(
        "helper.mouse.evdev.InputDevice",
        input_device,
    )

    grabber = MouseGrabber(mouse.info)

    with pytest.raises(
        RuntimeError,
        match="Mouse grabber is not started.",
    ):
        grabber.get_device()

    assert grabber.start() is True
    assert grabber.is_started() is True
    assert grabber.get_device() is physical_device

    assert grabber.start() is True

    input_device.assert_called_once_with(mouse.info.path)
    physical_device.grab.assert_called_once()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            OSError(errno.EBUSY, "Device or resource busy"),
            False,
        ),
        (
            OSError(errno.EACCES, "Permission denied"),
            OSError,
        ),
    ],
)
def test_mouse_grabber_start_handles_grab_errors(
    monkeypatch,
    error,
    expected,
):
    mouse = make_mouse()
    physical_device = MagicMock()
    physical_device.grab.side_effect = error

    monkeypatch.setattr(
        "helper.mouse.evdev.InputDevice",
        MagicMock(return_value=physical_device),
    )

    grabber = MouseGrabber(mouse.info)

    if expected is False:
        assert grabber.start() is False
    else:
        with pytest.raises(OSError):
            grabber.start()

    assert grabber.is_started() is False
    physical_device.close.assert_called_once()


def test_mouse_grabber_stop_releases_device_and_is_idempotent(monkeypatch):
    mouse = make_mouse()
    physical_device = MagicMock()

    monkeypatch.setattr(
        "helper.mouse.evdev.InputDevice",
        MagicMock(return_value=physical_device),
    )

    grabber = MouseGrabber(mouse.info)

    assert grabber.start() is True

    grabber.stop()

    assert grabber.is_started() is False
    physical_device.ungrab.assert_called_once()
    physical_device.close.assert_called_once()

    grabber.stop()

    physical_device.ungrab.assert_called_once()
    physical_device.close.assert_called_once()


def test_mouse_grabber_stop_ignores_ungrab_error(monkeypatch):
    mouse = make_mouse()
    physical_device = MagicMock()
    physical_device.ungrab.side_effect = OSError(
        errno.EIO,
        "Input/output error",
    )

    monkeypatch.setattr(
        "helper.mouse.evdev.InputDevice",
        MagicMock(return_value=physical_device),
    )

    grabber = MouseGrabber(mouse.info)

    assert grabber.start() is True

    grabber.stop()

    assert grabber.is_started() is False
    physical_device.ungrab.assert_called_once()
    physical_device.close.assert_called_once()
