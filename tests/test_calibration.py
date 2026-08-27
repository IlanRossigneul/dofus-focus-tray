from bridge.calibration import CalibrationController


def create_controller() -> CalibrationController:
    return CalibrationController()


def calibrated_uuids(controller: CalibrationController) -> list[str]:
    return [
        window.uuid
        for window in controller.calibrated_windows
    ]


def calibrated_orders(controller: CalibrationController) -> list[int | None]:
    return [
        window.calibrated_order
        for window in controller.calibrated_windows
    ]


def positions(controller: CalibrationController) -> list[int]:
    return [
        window.position
        for window in controller.calibrated_windows
    ]


def test_initial_state():
    controller = create_controller()

    assert controller.calibrating is False
    assert controller.calibrated is False
    assert controller.calibrated_windows == []
    assert controller.total_windows == 0


def test_start_with_no_windows_cancels_calibration():
    controller = create_controller()

    controller.start([])

    assert controller.calibrating is False
    assert controller.calibrated is False
    assert controller.calibrated_windows == []
    assert controller.total_windows == 0


def test_start_with_single_window_completes_calibration():
    controller = create_controller()

    controller.start(["window-1"])

    assert controller.calibrating is False
    assert controller.calibrated is True
    assert controller.total_windows == 1

    assert calibrated_uuids(controller) == ["window-1"]
    assert calibrated_orders(controller) == [0]
    assert positions(controller) == [0]


def test_start_with_multiple_windows_without_active_window_waits_for_selection():
    controller = create_controller()

    controller.start(
        ["window-1", "window-2", "window-3"]
    )

    assert controller.calibrating is True
    assert controller.calibrated is False
    assert controller.total_windows == 3
    assert controller.calibrated_windows == []


def test_select_window_calibrates_window_in_selection_order():
    controller = create_controller()

    controller.start(
        ["window-1", "window-2", "window-3"]
    )

    assert controller.select_window("window-2") is True
    assert controller.select_window("window-3") is True

    assert calibrated_uuids(controller) == [
        "window-2",
        "window-3",
    ]

    assert calibrated_orders(controller) == [0, 1]
    assert positions(controller) == [1, 2]

    assert controller.calibrating is True
    assert controller.calibrated is False


def test_select_window_completes_calibration_when_last_window_is_selected():
    controller = create_controller()

    controller.start(
        ["window-1", "window-2"]
    )

    assert controller.select_window("window-2") is True
    assert controller.select_window("window-1") is True

    assert controller.calibrating is False
    assert controller.calibrated is True
    assert calibrated_uuids(controller) == [
        "window-2",
        "window-1",
    ]
    assert calibrated_orders(controller) == [0, 1]


def test_select_window_ignores_selection_when_not_calibrating():
    controller = create_controller()

    controller.start(["window-1"])

    assert controller.select_window("window-1") is False

    assert controller.calibrated is True
    assert calibrated_uuids(controller) == ["window-1"]


def test_select_window_ignores_unknown_window():
    controller = create_controller()

    controller.start(
        ["window-1", "window-2"]
    )

    assert controller.select_window("unknown") is False

    assert calibrated_uuids(controller) == []
    assert controller.calibrating is True


def test_select_window_ignores_already_calibrated_window():
    controller = create_controller()

    controller.start(
        ["window-1", "window-2", "window-3"]
    )

    assert controller.select_window("window-2") is True
    assert controller.select_window("window-2") is False

    assert calibrated_uuids(controller) == ["window-2"]
    assert calibrated_orders(controller) == [0]
    assert controller.calibrating is True


def test_update_windows_updates_dynamic_window_list_and_total():
    controller = create_controller()

    controller.start(
        ["window-1", "window-2"]
    )

    controller.update_windows(
        ["window-1", "window-2", "window-3"]
    )

    assert controller.total_windows == 3
    assert controller.calibrating is True


def test_update_windows_keeps_calibrated_windows_during_calibration():
    controller = create_controller()

    controller.start(
        ["window-1", "window-2", "window-3"]
    )

    controller.select_window("window-1")

    controller.update_windows(
        ["window-1", "window-2", "window-3", "window-4"]
    )

    assert controller.calibrating is True
    assert calibrated_uuids(controller) == ["window-1"]
    assert controller.total_windows == 4


def test_update_windows_removing_uncalibrated_window_continues_calibration():
    controller = create_controller()

    controller.start(
        ["window-1", "window-2", "window-3"]
    )

    controller.select_window("window-1")
    controller.select_window("window-2")

    controller.update_windows(
        ["window-1", "window-2"]
    )

    assert controller.calibrating is False
    assert controller.calibrated is True
    assert controller.total_windows == 2
    assert calibrated_uuids(controller) == [
        "window-1",
        "window-2",
    ]


def test_update_windows_removing_uncalibrated_window_keeps_calibration_in_progress():
    controller = create_controller()

    controller.start(
        ["window-1", "window-2", "window-3", "window-4"]
    )

    controller.select_window("window-1")
    controller.select_window("window-2")

    controller.update_windows(
        ["window-1", "window-2", "window-4"]
    )

    assert controller.calibrating is True
    assert controller.calibrated is False
    assert controller.total_windows == 3
    assert calibrated_uuids(controller) == [
        "window-1",
        "window-2",
    ]


def test_update_windows_removing_calibrated_window_cancels_calibration():
    controller = create_controller()

    controller.start(
        ["window-1", "window-2", "window-3"]
    )

    controller.select_window("window-1")

    controller.update_windows(
        ["window-2", "window-3"]
    )

    assert controller.calibrating is False
    assert controller.calibrated is False
    assert controller.calibrated_windows == []
    assert controller.total_windows == 0


def test_update_windows_removing_calibrated_window_after_other_windows_were_selected_cancels_calibration():
    controller = create_controller()

    controller.start(
        ["window-1", "window-2", "window-3"]
    )

    controller.select_window("window-1")
    controller.select_window("window-2")

    controller.update_windows(
        ["window-2", "window-3"]
    )

    assert controller.calibrating is False
    assert controller.calibrated is False
    assert controller.calibrated_windows == []
    assert controller.total_windows == 0


def test_update_windows_can_complete_calibration_when_last_uncalibrated_window_disappears():
    controller = create_controller()

    controller.start(
        ["window-1", "window-2", "window-3"]
    )

    controller.select_window("window-1")
    controller.select_window("window-2")

    controller.update_windows(
        ["window-1", "window-2"]
    )

    assert controller.calibrating is False
    assert controller.calibrated is True
    assert controller.total_windows == 2
    assert calibrated_uuids(controller) == [
        "window-1",
        "window-2",
    ]


def test_update_windows_recalculates_positions_of_calibrated_windows():
    controller = create_controller()

    controller.start(
        ["window-1", "window-2", "window-3"]
    )

    controller.select_window("window-1")
    controller.select_window("window-3")

    controller.update_windows(
        ["window-3", "window-1"]
    )

    assert positions(controller) == [1, 0]


def test_update_windows_keeps_calibrated_order_when_window_position_changes():
    controller = create_controller()

    controller.start(
        ["window-1", "window-2", "window-3"]
    )

    controller.select_window("window-3")
    controller.select_window("window-1")

    controller.update_windows(
        ["window-1", "window-3"]
    )

    assert calibrated_uuids(controller) == [
        "window-3",
        "window-1",
    ]

    assert calibrated_orders(controller) == [0, 1]
    assert positions(controller) == [1, 0]


def test_update_windows_does_not_add_new_window_to_calibration_automatically():
    controller = create_controller()

    controller.start(
        ["window-1", "window-2"]
    )

    controller.select_window("window-1")

    controller.update_windows(
        ["window-1", "window-2", "window-3"]
    )

    assert controller.calibrating is True
    assert calibrated_uuids(controller) == ["window-1"]

    assert controller.select_window("window-3") is True

    assert calibrated_uuids(controller) == [
        "window-1",
        "window-3",
    ]


def test_update_windows_after_completed_calibration_does_not_add_new_window():
    controller = create_controller()

    controller.start(
        ["window-1", "window-2"]
    )

    controller.select_window("window-1")
    controller.select_window("window-2")

    assert controller.calibrated is True

    controller.update_windows(
        ["window-1", "window-2", "window-3"]
    )

    assert controller.calibrated is True
    assert controller.calibrating is False
    assert calibrated_uuids(controller) == [
        "window-1",
        "window-2",
    ]


def test_update_windows_after_completed_calibration_removes_missing_window():
    controller = create_controller()

    controller.start(
        ["window-1", "window-2", "window-3"]
    )

    controller.select_window("window-1")
    controller.select_window("window-2")
    controller.select_window("window-3")

    assert controller.calibrated is True

    controller.update_windows(
        ["window-1", "window-3"]
    )

    assert controller.calibrated is True
    assert controller.calibrating is False
    assert calibrated_uuids(controller) == [
        "window-1",
        "window-3",
    ]


def test_start_resets_previous_calibration():
    controller = create_controller()

    controller.start(
        ["window-1", "window-2"]
    )
    controller.select_window("window-2")

    controller.start(
        ["window-3", "window-4"]
    )

    assert controller.calibrating is True
    assert controller.calibrated is False
    assert controller.total_windows == 2
    assert controller.calibrated_windows == []


def test_calibrated_windows_property_returns_a_copy():
    controller = create_controller()

    controller.start(["window-1"])

    windows = controller.calibrated_windows
    windows.clear()

    assert calibrated_uuids(controller) == ["window-1"]


def test_calibration_resets_when_all_calibrated_windows_disappear():
    controller = create_controller()

    controller.start(
        ["window-1", "window-2"]
    )

    controller.select_window("window-1")
    controller.select_window("window-2")

    assert controller.calibrated is True

    controller.update_windows([])

    assert controller.calibrating is False
    assert controller.calibrated is False
    assert controller.calibrated_windows == []
    assert controller.total_windows == 0
