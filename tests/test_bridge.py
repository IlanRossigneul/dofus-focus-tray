import asyncio

from unittest.mock import AsyncMock

from bridge.bridge import DofusFocusBridge


def create_bridge() -> DofusFocusBridge:
    bridge = DofusFocusBridge()
    bridge._kwin.activate_window = AsyncMock()
    return bridge


def test_update_active_window_ignores_empty_id():
    bridge = create_bridge()

    bridge.update_active_window("")

    assert bridge._active_window_id is None
    assert bridge.state.current_index == -1


def test_update_active_window_stores_active_window_id():
    bridge = create_bridge()

    bridge.update_active_window("window-2")

    assert bridge._active_window_id == "window-2"


def test_update_active_window_selects_window_during_calibration():
    bridge = create_bridge()
    bridge._calibration.set_windows(
        ["window-1", "window-2", "window-3"]
    )
    bridge._calibration.start()

    bridge.update_active_window("window-2")

    assert bridge._active_window_id == "window-2"
    assert bridge.state.calibrating is True
    assert [
        window.uuid
        for window in bridge.state.calibrated_windows
    ] == ["window-2"]


def test_update_active_window_updates_current_index():
    bridge = create_bridge()
    bridge._calibration.set_windows(
        ["window-1", "window-2", "window-3"]
    )
    bridge._calibration.start()

    bridge._calibration.select_window("window-1")
    bridge._calibration.select_window("window-2")
    bridge._calibration.select_window("window-3")

    bridge.update_active_window("window-2")

    assert bridge._active_window_id == "window-2"
    assert bridge.state.current_index == 1


def test_update_active_window_ignores_unknown_window():
    bridge = create_bridge()
    bridge._calibration.set_windows(
        ["window-1", "window-2", "window-3"]
    )
    bridge._calibration.start()

    bridge._calibration.select_window("window-1")
    bridge._calibration.select_window("window-2")
    bridge._calibration.select_window("window-3")

    bridge.update_active_window("unknown")

    assert bridge._active_window_id == "unknown"
    assert bridge.state.current_index == 2


def test_dofus_focus_ignores_when_not_calibrated():
    bridge = create_bridge()

    bridge.dofus_focus(1)

    assert bridge.state.current_index == -1
    bridge._kwin.activate_window.assert_not_awaited()


def test_dofus_focus_ignores_when_no_calibrated_windows():
    bridge = create_bridge()
    bridge.state.calibrated = True

    bridge.dofus_focus(1)

    assert bridge.state.current_index == -1
    bridge._kwin.activate_window.assert_not_awaited()


def test_dofus_focus_ignores_invalid_direction():
    bridge = create_bridge()
    bridge._calibration.set_windows(
        ["window-1", "window-2", "window-3"]
    )
    bridge._calibration.start()

    bridge._calibration.select_window("window-1")
    bridge._calibration.select_window("window-2")
    bridge._calibration.select_window("window-3")

    bridge.state.current_index = 1

    bridge.dofus_focus(0)

    assert bridge.state.current_index == 1
    bridge._kwin.activate_window.assert_not_awaited()


def test_dofus_focus_ignores_invalid_current_index():
    bridge = create_bridge()
    bridge._calibration.set_windows(
        ["window-1", "window-2", "window-3"]
    )
    bridge._calibration.start()

    bridge._calibration.select_window("window-1")
    bridge._calibration.select_window("window-2")
    bridge._calibration.select_window("window-3")

    bridge.state.current_index = -1

    bridge.dofus_focus(1)

    assert bridge.state.current_index == -1
    bridge._kwin.activate_window.assert_not_awaited()


def test_dofus_focus_moves_to_next_window():
    bridge = create_bridge()
    bridge._calibration.set_windows(
        ["window-1", "window-2", "window-3"]
    )
    bridge._calibration.start()

    bridge._calibration.select_window("window-1")
    bridge._calibration.select_window("window-2")
    bridge._calibration.select_window("window-3")

    bridge.state.current_index = 0

    async def focus():
        bridge.dofus_focus(1)
        await asyncio.sleep(0)

    asyncio.run(focus())

    assert bridge.state.current_index == 1
    bridge._kwin.activate_window.assert_called_once_with("window-2")


def test_dofus_focus_moves_to_previous_window():
    bridge = create_bridge()
    bridge._calibration.set_windows(
        ["window-1", "window-2", "window-3"]
    )
    bridge._calibration.start()

    bridge._calibration.select_window("window-1")
    bridge._calibration.select_window("window-2")
    bridge._calibration.select_window("window-3")

    bridge.state.current_index = 1

    async def focus():
        bridge.dofus_focus(-1)
        await asyncio.sleep(0)

    asyncio.run(focus())

    assert bridge.state.current_index == 0
    bridge._kwin.activate_window.assert_called_once_with("window-1")


def test_dofus_focus_wraps_to_first_window():
    bridge = create_bridge()
    bridge._calibration.set_windows(
        ["window-1", "window-2", "window-3"]
    )
    bridge._calibration.start()

    bridge._calibration.select_window("window-1")
    bridge._calibration.select_window("window-2")
    bridge._calibration.select_window("window-3")

    bridge.state.current_index = 2

    async def focus():
        bridge.dofus_focus(1)
        await asyncio.sleep(0)

    asyncio.run(focus())

    assert bridge.state.current_index == 0
    bridge._kwin.activate_window.assert_called_once_with("window-1")


def test_dofus_focus_wraps_to_last_window():
    bridge = create_bridge()
    bridge._calibration.set_windows(
        ["window-1", "window-2", "window-3"]
    )
    bridge._calibration.start()

    bridge._calibration.select_window("window-1")
    bridge._calibration.select_window("window-2")
    bridge._calibration.select_window("window-3")

    bridge.state.current_index = 0

    async def focus():
        bridge.dofus_focus(-1)
        await asyncio.sleep(0)

    asyncio.run(focus())

    assert bridge.state.current_index == 2
    bridge._kwin.activate_window.assert_called_once_with("window-3")
