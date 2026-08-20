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

    assert [
        window.position
        for window in controller.state.calibrated_windows
    ] == [1, 2]

    assert controller.state.calibrating is True
    assert controller.state.calibrated is False


def test_select_window_when_not_calibrating_is_rejected():
    controller = create_controller(["window-1"])

    controller.start()

    assert controller.select_window("window-1") is False


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


def test_set_windows_updates_detected_windows():
    controller = create_controller(
        ["window-1", "window-2"]
    )

    controller.set_windows(
        ["window-1", "window-2", "window-3"]
    )

    controller.start()

    assert controller.state.total_windows == 3
    assert controller.state.calibrating is True


def test_set_windows_with_removed_window_during_calibration():
    controller = create_controller(
        ["window-1", "window-2", "window-3"]
    )

    controller.start()

    assert controller.select_window("window-1") is True

    controller.set_windows(
        ["window-1", "window-3"]
    )

    assert controller.state.calibrating is True
    assert controller.state.calibrated is False
    assert controller.state.total_windows == 2
    assert [
        window.uuid
        for window in controller.state.calibrated_windows
    ] == ["window-1"]


def test_set_windows_with_added_window_during_calibration():
    controller = create_controller(
        ["window-1", "window-2"]
    )

    controller.start()

    assert controller.select_window("window-1") is True

    controller.set_windows(
        ["window-1", "window-2", "window-3"]
    )

    assert controller.state.calibrating is True
    assert controller.state.calibrated is False
    assert controller.state.total_windows == 3

    assert controller.select_window("window-3") is True
    assert controller.select_window("window-2") is True

    assert controller.state.calibrated is True
    assert controller.state.calibrating is False

    assert [
        window.position
        for window in controller.state.calibrated_windows
    ] == [0, 2, 1]

    assert [
        window.uuid
        for window in controller.state.calibrated_windows
    ] == ["window-1", "window-3", "window-2"]


def test_set_windows_removing_selected_window_cancels_calibration():
    controller = create_controller(
        ["window-1", "window-2", "window-3"]
    )

    controller.start()

    assert controller.select_window("window-1") is True

    controller.set_windows(
        ["window-2", "window-3"]
    )

    assert controller.state.calibrated is False
    assert controller.state.calibrating is False
    assert controller.state.calibrated_windows == []
    assert controller.state.current_index == -1
    assert controller.state.total_windows == 0


def test_set_windows_with_unknown_changes_does_not_corrupt_calibration():
    controller = create_controller(
        ["window-1", "window-2", "window-3"]
    )

    controller.start()

    assert controller.select_window("window-1") is True
    assert controller.select_window("window-2") is True

    controller.set_windows(
        ["window-1", "window-2", "window-3", "window-4"]
    )

    assert controller.state.calibrating is True
    assert controller.state.calibrated is False
    assert controller.state.total_windows == 4

    assert [
        window.uuid
        for window in controller.state.calibrated_windows
    ] == ["window-1", "window-2"]


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
    assert [
        window.uuid
        for window in controller.state.calibrated_windows
    ] == ["window-2"]

    assert controller.state.calibrated_windows[0].calibrated_order == 0
    assert controller.state.calibrated_windows[0].position == 1


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

    assert [
        window.uuid
        for window in controller.state.calibrated_windows
    ] == [
        "window-2",
        "window-1",
    ]


def test_start_with_single_window_ignores_active_window():
    controller = create_controller(["window-1"])

    controller.start(active_window_id="unknown")

    assert controller.state.calibrated is True
    assert controller.state.calibrating is False
    assert controller.state.current_index == 0

    assert [
        window.uuid
        for window in controller.state.calibrated_windows
    ] == ["window-1"]


def test_set_windows_removing_unselected_window_can_complete_calibration():
    controller = create_controller(
        ["window-1", "window-2", "window-3"]
    )

    controller.start()

    assert controller.select_window("window-1") is True
    assert controller.select_window("window-2") is True

    controller.set_windows(
        ["window-1", "window-2"]
    )

    assert controller.state.calibrated is True
    assert controller.state.calibrating is False
    assert controller.state.total_windows == 2
    assert controller.state.current_index == 1

    assert [
        window.uuid
        for window in controller.state.calibrated_windows
    ] == ["window-1", "window-2"]


def test_set_windows_with_no_windows_cancels_calibration():
    controller = create_controller(
        ["window-1", "window-2"]
    )

    controller.start()

    assert controller.select_window("window-1") is True

    controller.set_windows([])

    assert controller.state.calibrated is False
    assert controller.state.calibrating is False
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
    assert len(controller.state.calibrated_windows) == 1

    window = controller.state.calibrated_windows[0]

    assert window.uuid == "window-1"
    assert window.position == 0
    assert window.calibrated_order == 0
