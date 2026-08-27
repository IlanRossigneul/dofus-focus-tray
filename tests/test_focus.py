import asyncio
from unittest.mock import AsyncMock, MagicMock

from bridge.calibration import CalibrationController
from bridge.focus import FocusController
from bridge.kwin import KWinController
from bridge.windows import WindowsController


def create_controller():
    windows = WindowsController()
    calibration = CalibrationController()
    kwin = KWinController()
    kwin.activate_window = AsyncMock()

    focus = FocusController(
        windows,
        calibration,
        kwin,
    )

    return focus, windows, calibration, kwin


def calibrate_windows(
    calibration: CalibrationController,
    windows: list[str],
) -> None:
    calibration.start(windows)

    for uuid in windows:
        calibration.select_window(uuid)


def test_update_active_window_updates_current_index():
    focus, _, calibration, _ = create_controller()

    calibrate_windows(
        calibration,
        ["window-1", "window-2", "window-3"],
    )

    focus.update_active_window("window-2")

    assert focus._current_index == 1


def test_update_active_window_ignores_unknown_window():
    focus, _, calibration, _ = create_controller()

    calibrate_windows(
        calibration,
        ["window-1", "window-2", "window-3"],
    )

    focus._current_index = 1

    focus.update_active_window("unknown")

    assert focus._current_index == 1


def test_update_active_window_ignores_empty_uuid():
    focus, _, calibration, _ = create_controller()

    calibrate_windows(
        calibration,
        ["window-1", "window-2", "window-3"],
    )

    focus._current_index = 1

    focus.update_active_window("")

    assert focus._current_index == 1


def test_focus_ignores_when_not_calibrated():
    focus, _, _, kwin = create_controller()

    asyncio.run(focus.focus(1))

    assert focus._current_index == -1
    kwin.activate_window.assert_not_awaited()


def test_focus_ignores_invalid_direction():
    focus, windows, calibration, kwin = create_controller()

    windows.update_windows(
        ["window-1", "window-2", "window-3"]
    )
    calibrate_windows(
        calibration,
        ["window-1", "window-2", "window-3"],
    )

    focus._current_index = 1

    asyncio.run(focus.focus(0))

    assert focus._current_index == 1
    kwin.activate_window.assert_not_awaited()


def test_focus_ignores_when_no_live_windows():
    focus, _, calibration, kwin = create_controller()

    calibrate_windows(
        calibration,
        ["window-1", "window-2", "window-3"],
    )

    focus._current_index = 1

    asyncio.run(focus.focus(1))

    assert focus._current_index == 1
    kwin.activate_window.assert_not_awaited()


def test_focus_ignores_when_no_calibrated_window_is_live():
    focus, windows, calibration, kwin = create_controller()

    calibrate_windows(
        calibration,
        ["window-1", "window-2", "window-3"],
    )

    windows.update_windows(
        ["window-4"],
    )

    focus._current_index = 1

    asyncio.run(focus.focus(1))

    assert focus._current_index == 1
    kwin.activate_window.assert_not_awaited()


def test_focus_moves_to_next_calibrated_window():
    focus, windows, calibration, kwin = create_controller()

    windows.update_windows(
        ["window-1", "window-2", "window-3"],
    )
    calibrate_windows(
        calibration,
        ["window-1", "window-2", "window-3"],
    )

    focus.update_active_window("window-1")

    asyncio.run(focus.focus(1))

    assert focus._current_index == 1
    kwin.activate_window.assert_awaited_once_with(
        "window-2",
    )


def test_focus_moves_to_previous_calibrated_window():
    focus, windows, calibration, kwin = create_controller()

    windows.update_windows(
        ["window-1", "window-2", "window-3"],
    )
    calibrate_windows(
        calibration,
        ["window-1", "window-2", "window-3"],
    )

    focus.update_active_window("window-2")

    asyncio.run(focus.focus(-1))

    assert focus._current_index == 0
    kwin.activate_window.assert_awaited_once_with(
        "window-1",
    )


def test_focus_wraps_to_first_calibrated_window():
    focus, windows, calibration, kwin = create_controller()

    windows.update_windows(
        ["window-1", "window-2", "window-3"],
    )
    calibrate_windows(
        calibration,
        ["window-1", "window-2", "window-3"],
    )

    focus.update_active_window("window-3")

    asyncio.run(focus.focus(1))

    assert focus._current_index == 0
    kwin.activate_window.assert_awaited_once_with(
        "window-1",
    )


def test_focus_wraps_to_last_calibrated_window():
    focus, windows, calibration, kwin = create_controller()

    windows.update_windows(
        ["window-1", "window-2", "window-3"],
    )
    calibrate_windows(
        calibration,
        ["window-1", "window-2", "window-3"],
    )

    focus.update_active_window("window-1")

    asyncio.run(focus.focus(-1))

    assert focus._current_index == 2
    kwin.activate_window.assert_awaited_once_with(
        "window-3",
    )


def test_focus_skips_calibrated_window_that_is_not_live():
    focus, windows, calibration, kwin = create_controller()

    calibrate_windows(
        calibration,
        ["window-1", "window-2", "window-3"],
    )

    windows.update_windows(
        ["window-1", "window-3"],
    )

    focus.update_active_window("window-1")

    asyncio.run(focus.focus(1))

    assert focus._current_index == 2
    kwin.activate_window.assert_awaited_once_with(
        "window-3",
    )


def test_focus_skips_multiple_non_live_calibrated_windows():
    focus, windows, calibration, kwin = create_controller()

    calibrate_windows(
        calibration,
        [
            "window-1",
            "window-2",
            "window-3",
            "window-4",
        ],
    )

    windows.update_windows(
        ["window-1", "window-4"],
    )

    focus.update_active_window("window-1")

    asyncio.run(focus.focus(1))

    assert focus._current_index == 3
    kwin.activate_window.assert_awaited_once_with(
        "window-4",
    )


def test_focus_reset_sets_current_index_to_minus_one():
    focus, _, _, _ = create_controller()

    focus._current_index = 2

    focus.reset()

    assert focus._current_index == -1


def test_focus_with_single_calibrated_window_keeps_same_window():
    focus, windows, calibration, kwin = create_controller()

    windows.update_windows(["window-1"])
    calibrate_windows(
        calibration,
        ["window-1"],
    )

    focus.update_active_window("window-1")

    asyncio.run(focus.focus(1))

    assert focus._current_index == 0
    kwin.activate_window.assert_awaited_once_with(
        "window-1",
    )

    kwin.activate_window.reset_mock()

    asyncio.run(focus.focus(-1))

    assert focus._current_index == 0
    kwin.activate_window.assert_awaited_once_with(
        "window-1",
    )
