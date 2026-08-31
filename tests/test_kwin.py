import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bridge.kwin import KWinController


def create_kwin_mocks():
    bus = MagicMock()
    bus.introspect = AsyncMock()

    proxy_object = MagicMock()
    scripting = MagicMock()

    scripting.call_load_script = AsyncMock(return_value=42)
    scripting.call_start = AsyncMock()
    scripting.call_unload_script = AsyncMock()

    bus.get_proxy_object.return_value = proxy_object
    proxy_object.get_interface.return_value = scripting

    return bus, proxy_object, scripting


def test_activate_window_loads_and_starts_kwin_script():
    controller = KWinController()
    bus, proxy_object, scripting = create_kwin_mocks()

    bus.disconnect = MagicMock()
    bus.connect = AsyncMock(return_value=bus)

    async def run_test():
        with (
            patch(
                "bridge.kwin.MessageBus",
                return_value=bus,
            ) as message_bus,
            patch(
                "bridge.kwin.asyncio.sleep",
                new=AsyncMock(),
            ),
        ):
            await controller.activate_window("12345")

        message_bus.assert_called_once()
        bus.connect.assert_awaited_once()
        bus.introspect.assert_awaited_once()

        bus.get_proxy_object.assert_called_once()
        proxy_object.get_interface.assert_called_once()

        scripting.call_load_script.assert_awaited_once()
        scripting.call_start.assert_awaited_once()
        scripting.call_unload_script.assert_awaited_once_with("42")

    asyncio.run(run_test())


def test_activate_window_generates_script_for_target_window():
    controller = KWinController()
    bus, _, scripting = create_kwin_mocks()

    bus.connect = AsyncMock(return_value=bus)
    bus.disconnect = MagicMock()

    temp_file = MagicMock()
    temp_file.name = "/tmp/test-kwin-script.js"
    temp_file.__enter__.return_value = temp_file

    async def run_test():
        with (
            patch(
                "bridge.kwin.MessageBus",
                return_value=bus,
            ),
            patch(
                "bridge.kwin.asyncio.sleep",
                new=AsyncMock(),
            ),
            patch(
                "bridge.kwin.tempfile.NamedTemporaryFile",
                return_value=temp_file,
            ),
            patch(
                "bridge.kwin.os.path.exists",
                return_value=True,
            ),
            patch(
                "bridge.kwin.os.remove",
            ),
        ):
            await controller.activate_window("abc-123")

        script = temp_file.write.call_args.args[0]

        assert (
            'String(windows[i].internalId) === "abc-123"'
            in script
        )
        assert "workspace.activeWindow = windows[i]" in script

        scripting.call_load_script.assert_awaited_once_with(
            "/tmp/test-kwin-script.js"
        )

    asyncio.run(run_test())


def test_activate_window_removes_temporary_script():
    controller = KWinController()
    bus, _, _ = create_kwin_mocks()

    bus.connect = AsyncMock(return_value=bus)
    bus.disconnect = MagicMock()

    with (
        patch(
            "bridge.kwin.MessageBus",
            return_value=bus,
        ),
        patch(
            "bridge.kwin.asyncio.sleep",
            new=AsyncMock(),
        ),
        patch(
            "bridge.kwin.os.path.exists",
            return_value=True,
        ),
        patch(
            "bridge.kwin.os.remove",
        ) as remove,
    ):
        asyncio.run(controller.activate_window("12345"))

    remove.assert_called_once()


def test_activate_window_propagates_connection_failure():
    controller = KWinController()

    bus = MagicMock()
    bus.connect = AsyncMock(return_value=bus)
    bus.introspect = AsyncMock(
        side_effect=RuntimeError("DBus failure")
    )

    with (
        patch(
            "bridge.kwin.MessageBus",
            return_value=bus,
        ),
        pytest.raises(
            RuntimeError,
            match="DBus failure",
        ),
    ):
        asyncio.run(controller.activate_window("12345"))

    bus.connect.assert_awaited_once()
    bus.introspect.assert_awaited_once()
    bus.disconnect.assert_not_called()


def test_activate_window_removes_script_on_failure():
    controller = KWinController()
    bus, _, scripting = create_kwin_mocks()

    bus.connect = AsyncMock(return_value=bus)
    scripting.call_start = AsyncMock(
        side_effect=RuntimeError("KWin script failure")
    )

    temp_file = MagicMock()
    temp_file.name = "/tmp/test-kwin-script.js"
    temp_file.__enter__.return_value = temp_file

    with (
        patch(
            "bridge.kwin.MessageBus",
            return_value=bus,
        ),
        patch(
            "bridge.kwin.tempfile.NamedTemporaryFile",
            return_value=temp_file,
        ),
        patch(
            "bridge.kwin.os.path.exists",
            return_value=True,
        ),
        patch(
            "bridge.kwin.os.remove",
        ) as remove,
        pytest.raises(
            RuntimeError,
            match="KWin script failure",
        ),
    ):
        asyncio.run(controller.activate_window("12345"))

    remove.assert_called_once_with(
        "/tmp/test-kwin-script.js"
    )
    scripting.call_unload_script.assert_awaited_once_with(
        "42"
    )


def test_close_disconnects_bus():
    controller = KWinController()
    bus = MagicMock()

    controller._bus = bus
    controller._scripting = MagicMock()

    asyncio.run(controller.close())

    bus.disconnect.assert_called_once()
    assert controller._bus is None
    assert controller._scripting is None


def test_close_does_nothing_when_not_connected():
    controller = KWinController()

    asyncio.run(controller.close())

    assert controller._bus is None
    assert controller._scripting is None
