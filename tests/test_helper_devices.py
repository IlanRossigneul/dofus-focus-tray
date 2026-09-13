from helper.devices import DeviceRegistry, HelperDevice
from input.classifier import DeviceClass
from input.discovery import InputDeviceInfo


def make_device() -> HelperDevice:
    info = InputDeviceInfo(
        path="/dev/input/event42",
        name="Test Keyboard",
        phys="usb-Test/event0",
        uniq="1234",
        vendor=0x1234,
        product=0x5678,
        bus=0x03,
        capabilities={
            1: [30, 31, 32],
            4: [4],
        },
    )

    return HelperDevice(
        device_id="device-123",
        info=info,
        device_class=DeviceClass.KEYBOARD,
    )


def make_info(
    path: str,
    name: str = "Test Keyboard",
) -> InputDeviceInfo:
    return InputDeviceInfo(
        path=path,
        name=name,
        phys="usb-Test/event0",
        uniq="1234",
        vendor=0x1234,
        product=0x5678,
        bus=0x03,
        capabilities={
            1: [30, 31, 32],
        },
    )


def test_device_registry_assigns_id_to_new_device():
    registry = DeviceRegistry()

    added, removed, current = registry.reconcile(
        [make_info("/dev/input/event42")],
    )

    assert len(added) == 1
    assert removed == []
    assert len(current) == 1
    assert current[0].device_id
    assert current[0].info.path == "/dev/input/event42"


def test_device_registry_preserves_id_for_existing_device():
    registry = DeviceRegistry()

    _, _, first = registry.reconcile(
        [make_info("/dev/input/event42")],
    )

    first_id = first[0].device_id

    _, _, second = registry.reconcile(
        [make_info("/dev/input/event42")],
    )

    assert second[0].device_id == first_id


def test_device_registry_reports_new_and_removed_devices():
    registry = DeviceRegistry()

    _, _, first = registry.reconcile(
        [make_info("/dev/input/event42")],
    )

    first_device = first[0]

    added, removed, current = registry.reconcile(
        [make_info("/dev/input/event43")],
    )

    assert len(added) == 1
    assert added[0].info.path == "/dev/input/event43"
    assert removed == [first_device]
    assert current == added


def test_device_registry_assigns_new_id_after_removal():
    registry = DeviceRegistry()

    _, _, first = registry.reconcile(
        [make_info("/dev/input/event42")],
    )

    first_id = first[0].device_id

    registry.reconcile([])

    added, removed, current = registry.reconcile(
        [make_info("/dev/input/event42")],
    )

    assert removed == []
    assert len(added) == 1
    assert current[0].device_id != first_id


def test_device_registry_preserves_id_when_metadata_is_rediscovered():
    registry = DeviceRegistry()

    _, _, first = registry.reconcile(
        [make_info("/dev/input/event42", "Original Keyboard")],
    )

    first_id = first[0].device_id

    _, _, current = registry.reconcile(
        [make_info("/dev/input/event42", "Updated Keyboard")],
    )

    assert current[0].device_id == first_id
    assert current[0].info.name == "Updated Keyboard"
