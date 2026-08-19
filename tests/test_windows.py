from bridge.calibration import CalibrationController
from bridge.models import DofusFocusState
from bridge.windows import WindowsController


def create_controller(
    windows: list[str],
) -> WindowsController:
    state = DofusFocusState()
    calibration = CalibrationController(state)
    controller = WindowsController(state, calibration)
    controller.update(windows)

    return controller


def test_update_stores_detected_windows():
    controller = create_controller([])

    controller.update(["window-1", "window-2"])

    assert controller.windows == ["window-1", "window-2"]


def test_update_returns_none_when_no_window_disappeared():
    controller = create_controller(
        ["window-1", "window-2"]
    )

    assert controller.update(
        ["window-1", "window-2", "window-3"]
    ) is None

    assert controller.windows == [
        "window-1",
        "window-2",
        "window-3",
    ]


def test_update_returns_disappeared_window():
    controller = create_controller(
        ["window-1", "window-2"]
    )

    assert controller.update(["window-1"]) == "window-2"
    assert controller.windows == ["window-1"]


def test_window_removal_during_calibration_delegates_to_calibration():
    controller = create_controller(
        ["window-1", "window-2", "window-3"]
    )

    controller.state.calibrated_windows = []
    controller._calibration.start()

    assert controller.state.calibrating is True

    assert controller._calibration.select_window("window-1") is True

    assert controller.update(
        ["window-1", "window-3"]
    ) == "window-2"

    assert controller.state.calibrating is True
    assert controller.state.calibrated is False
    assert controller.state.total_windows == 2

    assert [
        window.uuid
        for window in controller.state.calibrated_windows
    ] == ["window-1"]


def test_removing_calibrated_window_during_calibration_cancels_calibration():
    controller = create_controller(
        ["window-1", "window-2", "window-3"]
    )

    controller._calibration.start()

    assert controller._calibration.select_window("window-1") is True

    assert controller.update(
        ["window-2", "window-3"]
    ) == "window-1"

    assert controller.state.calibrated is False
    assert controller.state.calibrating is False
    assert controller.state.calibrated_windows == []
    assert controller.state.current_index == -1
    assert controller.state.total_windows == 0


def test_removing_unselected_window_during_calibration_can_complete_calibration():
    controller = create_controller(
        ["window-1", "window-2", "window-3"]
    )

    controller._calibration.start()

    assert controller._calibration.select_window("window-1") is True
    assert controller._calibration.select_window("window-2") is True

    assert controller.update(
        ["window-1", "window-2"]
    ) == "window-3"

    assert controller.state.calibrated is True
    assert controller.state.calibrating is False
    assert controller.state.total_windows == 2
    assert controller.state.current_index == 1

    assert [
        window.uuid
        for window in controller.state.calibrated_windows
    ] == ["window-1", "window-2"]


def test_removing_calibrated_window_after_calibration_removes_it_from_order():
    controller = create_controller(
        ["window-1", "window-2", "window-3"]
    )

    controller._calibration.start()

    assert controller._calibration.select_window("window-1") is True
    assert controller._calibration.select_window("window-2") is True
    assert controller._calibration.select_window("window-3") is True

    assert controller.state.calibrated is True

    assert controller.update(
        ["window-1", "window-3"]
    ) == "window-2"

    assert controller.state.calibrated is True
    assert [
        window.uuid
        for window in controller.state.calibrated_windows
    ] == ["window-1", "window-3"]


def test_removing_window_before_current_index_decrements_current_index():
    controller = create_controller(
        ["window-1", "window-2", "window-3"]
    )

    controller._calibration.start()

    assert controller._calibration.select_window("window-1") is True
    assert controller._calibration.select_window("window-2") is True
    assert controller._calibration.select_window("window-3") is True

    controller.state.current_index = 2

    assert controller.update(
        ["window-1", "window-3"]
    ) == "window-2"

    assert controller.state.current_index == 1


def test_removing_current_last_window_moves_current_index_to_last_window():
    controller = create_controller(
        ["window-1", "window-2", "window-3"]
    )

    controller._calibration.start()

    assert controller._calibration.select_window("window-1") is True
    assert controller._calibration.select_window("window-2") is True
    assert controller._calibration.select_window("window-3") is True

    controller.state.current_index = 2

    assert controller.update(
        ["window-1", "window-2"]
    ) == "window-3"

    assert controller.state.current_index == 1


def test_removing_last_calibrated_window_resets_state():
    controller = create_controller(
        ["window-1", "window-2"]
    )

    controller._calibration.start()

    assert controller._calibration.select_window("window-1") is True
    assert controller._calibration.select_window("window-2") is True

    assert controller.update([]) == "window-1"

    assert controller.state.calibrated is False
    assert controller.state.calibrating is False
    assert controller.state.calibrated_windows == []
    assert controller.state.current_index == -1
    assert controller.state.total_windows == 0
