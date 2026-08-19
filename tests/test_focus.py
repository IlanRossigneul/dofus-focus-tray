import asyncio

from unittest.mock import AsyncMock, MagicMock

from bridge.focus import FocusController
from bridge.kwin import KWinController
from bridge.models import DofusFocusState


def create_window(uuid: str):
    window = MagicMock()
    window.uuid = uuid
    return window


def create_focus():
    state = DofusFocusState()
    kwin = KWinController()
    kwin.activate_window = AsyncMock()

    return FocusController(state, kwin)


def set_calibrated_windows(focus, *uuids):
    focus._state.calibrated_windows = [
        create_window(uuid)
        for uuid in uuids
    ]
    focus._state.calibrated = True


def run_focus(focus, direction):
    async def run():
        focus.focus(direction)
        await asyncio.sleep(0)

    asyncio.run(run())


def test_update_active_window_updates_current_index():
    focus = create_focus()
    set_calibrated_windows(
        focus,
        "window-1",
        "window-2",
        "window-3",
    )

    focus.update_active_window("window-2")

    assert focus._state.current_index == 1


def test_update_active_window_ignores_unknown_window():
    focus = create_focus()
    set_calibrated_windows(
        focus,
        "window-1",
        "window-2",
        "window-3",
    )
    focus._state.current_index = 1

    focus.update_active_window("unknown")

    assert focus._state.current_index == 1


def test_update_active_window_ignores_empty_id():
    focus = create_focus()

    focus.update_active_window("")

    assert focus._state.current_index == -1


def test_focus_ignores_when_not_calibrated():
    focus = create_focus()

    focus.focus(1)

    assert focus._state.current_index == -1
    focus._kwin.activate_window.assert_not_awaited()


def test_focus_ignores_when_no_calibrated_windows():
    focus = create_focus()
    focus._state.calibrated = True

    focus.focus(1)

    assert focus._state.current_index == -1
    focus._kwin.activate_window.assert_not_awaited()


def test_focus_ignores_invalid_direction():
    focus = create_focus()
    set_calibrated_windows(
        focus,
        "window-1",
        "window-2",
        "window-3",
    )
    focus._state.current_index = 1

    focus.focus(0)

    assert focus._state.current_index == 1
    focus._kwin.activate_window.assert_not_awaited()


def test_focus_ignores_invalid_current_index():
    focus = create_focus()
    set_calibrated_windows(
        focus,
        "window-1",
        "window-2",
        "window-3",
    )
    focus._state.current_index = -1

    focus.focus(1)

    assert focus._state.current_index == -1
    focus._kwin.activate_window.assert_not_awaited()


def test_focus_moves_to_next_window():
    focus = create_focus()
    set_calibrated_windows(
        focus,
        "window-1",
        "window-2",
        "window-3",
    )
    focus._state.current_index = 0

    run_focus(focus, 1)

    assert focus._state.current_index == 1
    focus._kwin.activate_window.assert_called_once_with(
        "window-2"
    )


def test_focus_moves_to_previous_window():
    focus = create_focus()
    set_calibrated_windows(
        focus,
        "window-1",
        "window-2",
        "window-3",
    )
    focus._state.current_index = 1

    run_focus(focus, -1)

    assert focus._state.current_index == 0
    focus._kwin.activate_window.assert_called_once_with(
        "window-1"
    )


def test_focus_wraps_to_first_window():
    focus = create_focus()
    set_calibrated_windows(
        focus,
        "window-1",
        "window-2",
        "window-3",
    )
    focus._state.current_index = 2

    run_focus(focus, 1)

    assert focus._state.current_index == 0
    focus._kwin.activate_window.assert_called_once_with(
        "window-1"
    )


def test_focus_wraps_to_last_window():
    focus = create_focus()
    set_calibrated_windows(
        focus,
        "window-1",
        "window-2",
        "window-3",
    )
    focus._state.current_index = 0

    run_focus(focus, -1)

    assert focus._state.current_index == 2
    focus._kwin.activate_window.assert_called_once_with(
        "window-3"
    )