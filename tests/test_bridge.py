from unittest.mock import AsyncMock

from bridge.bridge import DofusFocusBridge


def create_bridge() -> DofusFocusBridge:
    bridge = DofusFocusBridge()
    bridge._kwin.activate_window = AsyncMock()
    return bridge


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


def test_start_calibration_uses_active_window():
    bridge = create_bridge()
    bridge.update_active_window("window-2")
    bridge.update_windows(
        '["window-1", "window-2", "window-3"]'
    )
    bridge.start_calibration()

    assert bridge.state.calibrating is True
    assert [
        window.uuid
        for window in bridge.state.calibrated_windows
    ] == ["window-2"]


def test_update_windows_ignores_updates_without_removed_windows():
    bridge = create_bridge()
    bridge.update_windows(
        '["window-1", "window-2"]'
    )

    bridge.update_windows(
        '["window-1", "window-2", "window-3"]'
    )

    assert bridge._windows_controller.windows == [
        "window-1",
        "window-2",
        "window-3",
    ]


def test_update_windows_cancels_calibration_when_window_disappears():
    bridge = create_bridge()
    bridge.update_windows(
        ["window-1", "window-2", "window-3"]
    )
    bridge.start_calibration()

    bridge.update_windows(
        '["window-1", "window-3"]'
    )

    assert bridge.state.calibrated is False
    assert bridge.state.calibrating is False
    assert bridge.state.calibrated_windows == []
    assert bridge.state.current_index == -1
    assert bridge.state.total_windows == 0


def test_update_windows_keeps_calibration_when_no_window_disappears():
    bridge = create_bridge()
    bridge._calibration.set_windows(
        ["window-1", "window-2", "window-3"]
    )
    bridge._calibration.start()

    bridge._calibration.select_window("window-1")
    bridge._calibration.select_window("window-2")
    bridge._calibration.select_window("window-3")

    bridge.update_windows(
        '["window-1", "window-2", "window-3", "window-4"]'
    )

    assert bridge.state.calibrated is True
    assert len(bridge.state.calibrated_windows) == 3


def test_update_windows_removes_calibrated_window():
    bridge = create_bridge()
    bridge.update_windows(
        '["window-1", "window-2", "window-3"]'
    )
    bridge.start_calibration()

    bridge._calibration.select_window("window-1")
    bridge._calibration.select_window("window-2")
    bridge._calibration.select_window("window-3")

    bridge.state.current_index = 2

    bridge.update_windows(
        '["window-1", "window-2"]'
    )

    assert [
        window.uuid
        for window in bridge.state.calibrated_windows
    ] == ["window-1", "window-2"]

    assert bridge.state.current_index == 1
    assert bridge.state.calibrated is True


def test_update_windows_adjusts_current_index_when_window_before_it_is_removed():
    bridge = create_bridge()
    bridge.update_windows(
        '["window-1", "window-2", "window-3"]'
    )
    bridge.start_calibration()

    bridge._calibration.select_window("window-1")
    bridge._calibration.select_window("window-2")
    bridge._calibration.select_window("window-3")

    bridge.state.current_index = 2

    bridge.update_windows(
        '["window-2", "window-3"]'
    )

    assert [
        window.uuid
        for window in bridge.state.calibrated_windows
    ] == ["window-2", "window-3"]

    assert bridge.state.current_index == 1


def test_update_windows_resets_state_when_all_calibrated_windows_are_removed():
    bridge = create_bridge()
    bridge.update_windows(
        ["window-1", "window-2"]
    )
    bridge.start_calibration()

    bridge._calibration.select_window("window-1")
    bridge._calibration.select_window("window-2")

    bridge.update_windows("[]")

    assert bridge.state.calibrated is False
    assert bridge.state.calibrating is False
    assert bridge.state.calibrated_windows == []
    assert bridge.state.current_index == -1
    assert bridge.state.total_windows == 0


def test_update_windows_handles_invalid_json():
    bridge = create_bridge()

    bridge.update_windows("not-json")

    assert bridge._windows_controller.windows == []
    assert bridge.state.calibrated is False
    assert bridge.state.calibrating is False
