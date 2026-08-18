from bridge.calibration import CalibrationController
from bridge.models import DofusFocusState


def create_controller(windows: list[str]) -> CalibrationController:
    state = DofusFocusState()
    controller = CalibrationController(state)
    controller.set_windows(windows)
    return controller


def test_start_with_no_windows():
    controller = create_controller([])

    controller.start()

    assert controller.state.calibrated is False
    assert controller.state.calibrating is False
    assert controller.state.original_windows == []
    assert controller.state.calibrated_windows == []
    assert controller.state.current_index == -1
    assert controller.state.total_windows == 0


def test_start_with_single_window():
    controller = create_controller(["window-1"])

    controller.start()

    assert controller.state.calibrated is True
    assert controller.state.calibrating is False
    assert controller.state.total_windows == 1
    assert controller.state.current_index == 0
    assert len(controller.state.original_windows) == 1
    assert len(controller.state.calibrated_windows) == 1
    assert controller.state.calibrated_windows[0].uuid == "window-1"


def test_start_with_multiple_windows():
    controller = create_controller(
        ["window-1", "window-2", "window-3"]
    )

    controller.start()

    assert controller.state.calibrated is False
    assert controller.state.calibrating is True
    assert controller.state.total_windows == 3
    assert controller.state.current_index == -1
    assert len(controller.state.original_windows) == 3
    assert controller.state.calibrated_windows == []


def test_select_window_adds_window_in_order():
    controller = create_controller(
        ["window-1", "window-2", "window-3"]
    )

    controller.start()

    assert controller.select_window("window-2") is True
    assert controller.select_window("window-3") is True

    assert [
        window.uuid
        for window in controller.state.calibrated_windows
    ] == ["window-2", "window-3"]

    assert [
        window.calibrated_order
        for window in controller.state.calibrated_windows
    ] == [0, 1]

    assert controller.state.calibrating is True
    assert controller.state.calibrated is False


def test_select_unknown_window_is_rejected():
    controller = create_controller(
        ["window-1", "window-2"]
    )

    controller.start()

    assert controller.select_window("unknown") is False
    assert controller.state.calibrated_windows == []
    assert controller.state.calibrating is True


def test_select_duplicate_window_is_rejected():
    controller = create_controller(
        ["window-1", "window-2"]
    )

    controller.start()

    assert controller.select_window("window-1") is True
    assert controller.select_window("window-1") is False

    assert [
        window.uuid
        for window in controller.state.calibrated_windows
    ] == ["window-1"]


def test_last_selection_completes_calibration():
    controller = create_controller(
        ["window-1", "window-2"]
    )

    controller.start()

    assert controller.select_window("window-1") is True
    assert controller.select_window("window-2") is True

    assert controller.state.calibrated is True
    assert controller.state.calibrating is False
    assert controller.state.current_index == 1


def test_select_window_when_not_calibrating_is_rejected():
    controller = create_controller(
        ["window-1"]
    )

    controller.start()

    assert controller.select_window("window-1") is False


def test_window_removal_during_calibration_cancels_calibration():
    controller = create_controller(
        ["window-1", "window-2", "window-3"]
    )

    controller.start()
    assert controller.select_window("window-1") is True

    assert controller.handle_window_removal("window-2") is True

    assert controller.state.calibrated is False
    assert controller.state.calibrating is False
    assert controller.state.original_windows == []
    assert controller.state.calibrated_windows == []
    assert controller.state.current_index == -1
    assert controller.state.total_windows == 0


def test_unknown_window_removal_does_not_cancel_calibration():
    controller = create_controller(
        ["window-1", "window-2"]
    )

    controller.start()

    assert controller.handle_window_removal("unknown") is False
    assert controller.state.calibrating is True
    assert controller.state.total_windows == 2


def test_window_removal_when_not_calibrating_is_ignored():
    controller = create_controller(
        ["window-1", "window-2"]
    )

    controller.start()
    controller.select_window("window-1")
    controller.select_window("window-2")

    assert controller.handle_window_removal("window-1") is False
    assert controller.state.calibrated is True
    assert controller.state.calibrated_windows


def test_start_resets_previous_calibration():
    controller = create_controller(
        ["window-1", "window-2"]
    )

    controller.start()
    controller.select_window("window-2")

    controller.start()

    assert controller.state.calibrated is False
    assert controller.state.calibrating is True
    assert controller.state.calibrated_windows == []
    assert controller.state.current_index == -1
    assert controller.state.total_windows == 2


def test_start_with_active_dofus_window_selects_it_first():
    controller = create_controller(
        ["window-1", "window-2", "window-3"]
    )

    controller.start(active_window_id="window-2")

    assert controller.state.calibrating is True
    assert controller.state.calibrated is False
    assert [window.uuid for window in controller.state.calibrated_windows] == ["window-2"]
    assert controller.state.calibrated_windows[0].calibrated_order == 0


def test_start_with_unknown_active_window_waits_for_selection():
    controller = create_controller(
        ["window-1", "window-2"]
    )

    controller.start(active_window_id="window-unknown")

    assert controller.state.calibrating is True
    assert controller.state.calibrated is False
    assert controller.state.calibrated_windows == []


def test_start_with_active_window_can_complete_calibration():
    controller = create_controller(
        ["window-1", "window-2"]
    )

    controller.start(active_window_id="window-2")

    assert controller.state.calibrating is True

    assert controller.select_window("window-1") is True

    assert controller.state.calibrating is False
    assert controller.state.calibrated is True
    assert controller.state.current_index == 1
    assert [window.uuid for window in controller.state.calibrated_windows] == [
        "window-2",
        "window-1",
    ]


def test_start_with_single_window_ignores_active_window():
    controller = create_controller(["window-1"])

    controller.start(active_window_id="unknown")

    assert controller.state.calibrated is True
    assert controller.state.calibrating is False
    assert controller.state.current_index == 0
    assert [window.uuid for window in controller.state.calibrated_windows] == [
        "window-1"
    ]
