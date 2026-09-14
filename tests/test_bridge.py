import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from bridge.bridge import DofusFocusBridge


def create_bridge() -> DofusFocusBridge:
    return DofusFocusBridge()


def calibrated_uuids(bridge: DofusFocusBridge) -> list[str]:
    return [
        window.uuid
        for window in bridge._calibration.calibrated_windows
    ]


def calibrated_orders(
    bridge: DofusFocusBridge,
) -> list[int | None]:
    return [
        window.calibrated_order
        for window in bridge._calibration.calibrated_windows
    ]


def positions(bridge: DofusFocusBridge) -> list[int]:
    return [
        window.position
        for window in bridge._calibration.calibrated_windows
    ]


def update_windows(
    bridge: DofusFocusBridge,
    windows: list[str],
) -> None:
    bridge.update_windows(json.dumps(windows))


def test_initial_state():
    bridge = create_bridge()

    assert bridge._windows.windows == []
    assert bridge._windows.active_window is None
    assert bridge._calibration.calibrating is False
    assert bridge._calibration.calibrated is False
    assert bridge._calibration.calibrated_windows == []
    assert bridge._calibration.total_windows == 0


def test_update_windows_updates_windows_and_calibration():
    bridge = create_bridge()

    update_windows(
        bridge,
        ["window-1", "window-2", "window-3"],
    )

    assert bridge._windows.windows == [
        "window-1",
        "window-2",
        "window-3",
    ]
    assert bridge._calibration.total_windows == 3


def test_update_active_window_updates_windows_controller():
    bridge = create_bridge()

    update_windows(
        bridge,
        ["window-1", "window-2"],
    )

    bridge.update_active_window("window-2")

    assert bridge._windows.active_window == "window-2"


def test_start_calibration_with_no_windows_is_cancelled():
    bridge = create_bridge()

    update_windows(bridge, [])

    bridge.start_calibration()

    assert bridge._calibration.calibrating is False
    assert bridge._calibration.calibrated is False
    assert bridge._calibration.calibrated_windows == []
    assert bridge._calibration.total_windows == 0


def test_start_calibration_with_one_window_completes_automatically():
    bridge = create_bridge()

    update_windows(
        bridge,
        ["window-1"],
    )

    bridge.start_calibration()

    assert bridge._calibration.calibrating is False
    assert bridge._calibration.calibrated is True
    assert bridge._calibration.total_windows == 1
    assert calibrated_uuids(bridge) == ["window-1"]
    assert calibrated_orders(bridge) == [0]
    assert positions(bridge) == [0]


def test_start_calibration_with_multiple_windows_without_active_window_waits():
    bridge = create_bridge()

    update_windows(
        bridge,
        ["window-1", "window-2", "window-3"],
    )

    bridge.start_calibration()

    assert bridge._calibration.calibrating is True
    assert bridge._calibration.calibrated is False
    assert bridge._calibration.total_windows == 3
    assert bridge._calibration.calibrated_windows == []


def test_start_calibration_with_active_window_calibrates_it_immediately():
    bridge = create_bridge()

    update_windows(
        bridge,
        ["window-1", "window-2", "window-3"],
    )
    bridge.update_active_window("window-2")

    bridge.start_calibration()

    assert bridge._calibration.calibrating is True
    assert bridge._calibration.calibrated is False
    assert calibrated_uuids(bridge) == ["window-2"]
    assert calibrated_orders(bridge) == [0]


def test_update_active_window_selects_window_during_calibration():
    bridge = create_bridge()

    update_windows(
        bridge,
        ["window-1", "window-2", "window-3"],
    )
    bridge.start_calibration()

    bridge.update_active_window("window-2")

    assert calibrated_uuids(bridge) == ["window-2"]
    assert calibrated_orders(bridge) == [0]
    assert bridge._calibration.calibrating is True
    assert bridge._calibration.calibrated is False


def test_update_active_window_selects_windows_in_focus_order():
    bridge = create_bridge()

    update_windows(
        bridge,
        ["window-1", "window-2", "window-3"],
    )
    bridge.start_calibration()

    bridge.update_active_window("window-2")
    bridge.update_active_window("window-3")
    bridge.update_active_window("window-1")

    assert bridge._calibration.calibrating is False
    assert bridge._calibration.calibrated is True

    assert calibrated_uuids(bridge) == [
        "window-2",
        "window-3",
        "window-1",
    ]
    assert calibrated_orders(bridge) == [0, 1, 2]


def test_update_active_window_does_not_calibrate_already_calibrated_window_again():
    bridge = create_bridge()

    update_windows(
        bridge,
        ["window-1", "window-2", "window-3"],
    )
    bridge.start_calibration()

    bridge.update_active_window("window-1")
    bridge.update_active_window("window-2")
    bridge.update_active_window("window-1")

    assert calibrated_uuids(bridge) == [
        "window-1",
        "window-2",
    ]
    assert calibrated_orders(bridge) == [0, 1]
    assert bridge._calibration.calibrating is True


def test_update_active_window_completes_calibration_when_last_window_is_selected():
    bridge = create_bridge()

    update_windows(
        bridge,
        ["window-1", "window-2"],
    )
    bridge.start_calibration()

    bridge.update_active_window("window-1")
    bridge.update_active_window("window-2")

    assert bridge._calibration.calibrating is False
    assert bridge._calibration.calibrated is True
    assert calibrated_uuids(bridge) == [
        "window-1",
        "window-2",
    ]


def test_new_window_during_calibration_is_added_to_dynamic_window_list():
    bridge = create_bridge()

    update_windows(
        bridge,
        ["window-1", "window-2"],
    )
    bridge.start_calibration()

    bridge.update_active_window("window-1")

    update_windows(
        bridge,
        ["window-1", "window-2", "window-3"],
    )

    assert bridge._calibration.total_windows == 3
    assert bridge._windows.windows == [
        "window-1",
        "window-2",
        "window-3",
    ]
    assert calibrated_uuids(bridge) == ["window-1"]


def test_new_window_during_calibration_is_calibrated_when_it_becomes_active():
    bridge = create_bridge()

    update_windows(
        bridge,
        ["window-1", "window-2"],
    )
    bridge.start_calibration()

    bridge.update_active_window("window-1")

    update_windows(
        bridge,
        ["window-1", "window-2", "window-3"],
    )
    bridge.update_active_window("window-3")

    assert calibrated_uuids(bridge) == [
        "window-1",
        "window-3",
    ]
    assert bridge._calibration.total_windows == 3
    assert bridge._calibration.calibrating is True


def test_multiple_new_windows_during_calibration_are_calibrated_one_by_one():
    bridge = create_bridge()

    update_windows(
        bridge,
        ["window-1", "window-2"],
    )
    bridge.start_calibration()

    bridge.update_active_window("window-1")

    update_windows(
        bridge,
        ["window-1", "window-2", "window-3"],
    )
    bridge.update_active_window("window-3")

    update_windows(
        bridge,
        ["window-1", "window-2", "window-3", "window-4"],
    )
    bridge.update_active_window("window-4")

    assert calibrated_uuids(bridge) == [
        "window-1",
        "window-3",
        "window-4",
    ]
    assert calibrated_orders(bridge) == [0, 1, 2]
    assert bridge._calibration.total_windows == 4
    assert bridge._calibration.calibrating is True


def test_disappearing_calibrated_window_cancels_calibration():
    bridge = create_bridge()

    update_windows(
        bridge,
        ["window-1", "window-2", "window-3"],
    )
    bridge.start_calibration()

    bridge.update_active_window("window-1")
    bridge.update_active_window("window-2")

    update_windows(
        bridge,
        ["window-2", "window-3"],
    )

    assert bridge._calibration.calibrating is False
    assert bridge._calibration.calibrated is False
    assert bridge._calibration.calibrated_windows == []
    assert bridge._calibration.total_windows == 0


def test_disappearing_uncalibrated_window_keeps_calibration_in_progress():
    bridge = create_bridge()

    update_windows(
        bridge,
        ["window-1", "window-2", "window-3", "window-4"],
    )
    bridge.start_calibration()

    bridge.update_active_window("window-1")
    bridge.update_active_window("window-2")

    update_windows(
        bridge,
        ["window-1", "window-2", "window-4"],
    )

    assert bridge._calibration.calibrating is True
    assert bridge._calibration.calibrated is False
    assert bridge._calibration.total_windows == 3
    assert calibrated_uuids(bridge) == [
        "window-1",
        "window-2",
    ]


def test_disappearing_last_uncalibrated_window_completes_calibration():
    bridge = create_bridge()

    update_windows(
        bridge,
        ["window-1", "window-2", "window-3"],
    )
    bridge.start_calibration()

    bridge.update_active_window("window-1")
    bridge.update_active_window("window-2")

    update_windows(
        bridge,
        ["window-1", "window-2"],
    )

    assert bridge._calibration.calibrating is False
    assert bridge._calibration.calibrated is True
    assert bridge._calibration.total_windows == 2
    assert calibrated_uuids(bridge) == [
        "window-1",
        "window-2",
    ]


def test_disappearing_calibrated_window_cancels_even_if_other_windows_are_calibrated():
    bridge = create_bridge()

    update_windows(
        bridge,
        ["window-1", "window-2", "window-3", "window-4"],
    )
    bridge.start_calibration()

    bridge.update_active_window("window-1")
    bridge.update_active_window("window-2")
    bridge.update_active_window("window-3")

    update_windows(
        bridge,
        ["window-1", "window-3", "window-4"],
    )

    assert bridge._calibration.calibrating is False
    assert bridge._calibration.calibrated is False
    assert bridge._calibration.calibrated_windows == []
    assert bridge._calibration.total_windows == 0


def test_calibration_completes_when_dynamic_total_reaches_calibrated_count():
    bridge = create_bridge()

    update_windows(
        bridge,
        ["window-1", "window-2", "window-3", "window-4"],
    )
    bridge.start_calibration()

    bridge.update_active_window("window-1")
    bridge.update_active_window("window-2")

    update_windows(
        bridge,
        ["window-1", "window-2"],
    )

    assert bridge._calibration.total_windows == 2
    assert len(bridge._calibration.calibrated_windows) == 2
    assert bridge._calibration.calibrating is False
    assert bridge._calibration.calibrated is True


def test_calibrated_order_is_preserved_when_live_window_order_changes():
    bridge = create_bridge()

    update_windows(
        bridge,
        ["window-1", "window-2", "window-3"],
    )
    bridge.start_calibration()

    bridge.update_active_window("window-3")
    bridge.update_active_window("window-1")
    bridge.update_active_window("window-2")

    assert calibrated_uuids(bridge) == [
        "window-3",
        "window-1",
        "window-2",
    ]
    assert calibrated_orders(bridge) == [0, 1, 2]

    update_windows(
        bridge,
        ["window-2", "window-3", "window-1"],
    )

    assert calibrated_uuids(bridge) == [
        "window-3",
        "window-1",
        "window-2",
    ]
    assert calibrated_orders(bridge) == [0, 1, 2]
    assert positions(bridge) == [1, 2, 0]


def test_calibrated_window_disappearing_after_calibration_updates_calibrated_order():
    bridge = create_bridge()

    update_windows(
        bridge,
        ["window-1", "window-2", "window-3"],
    )
    bridge.start_calibration()

    bridge.update_active_window("window-3")
    bridge.update_active_window("window-1")
    bridge.update_active_window("window-2")

    assert bridge._calibration.calibrated is True
    assert calibrated_orders(bridge) == [0, 1, 2]

    update_windows(
        bridge,
        ["window-3", "window-1"],
    )

    assert bridge._calibration.calibrated is True
    assert bridge._calibration.calibrating is False
    assert calibrated_uuids(bridge) == [
        "window-3",
        "window-1",
    ]
    assert calibrated_orders(bridge) == [0, 1]


def test_new_window_after_completed_calibration_is_not_added_to_calibrated_windows():
    bridge = create_bridge()

    update_windows(
        bridge,
        ["window-1", "window-2"],
    )
    bridge.start_calibration()

    bridge.update_active_window("window-1")
    bridge.update_active_window("window-2")

    assert bridge._calibration.calibrated is True

    update_windows(
        bridge,
        ["window-1", "window-2", "window-3"],
    )

    assert bridge._calibration.calibrated is True
    assert bridge._calibration.calibrating is False
    assert calibrated_uuids(bridge) == [
        "window-1",
        "window-2",
    ]


def test_calibration_resets_when_all_calibrated_windows_disappear():
    bridge = create_bridge()

    update_windows(
        bridge,
        ["window-1", "window-2"],
    )
    bridge.start_calibration()

    bridge.update_active_window("window-1")
    bridge.update_active_window("window-2")

    assert bridge._calibration.calibrated is True

    update_windows(bridge, [])

    assert bridge._calibration.calibrating is False
    assert bridge._calibration.calibrated is False
    assert bridge._calibration.calibrated_windows == []
    assert bridge._calibration.total_windows == 0


def test_start_calibration_resets_previous_calibration():
    bridge = create_bridge()

    update_windows(
        bridge,
        ["window-1", "window-2"],
    )
    bridge.start_calibration()

    bridge.update_active_window("window-2")

    assert calibrated_uuids(bridge) == ["window-2"]

    update_windows(
        bridge,
        ["window-3", "window-4"],
    )
    bridge.start_calibration()

    assert bridge._calibration.calibrating is True
    assert bridge._calibration.calibrated is False
    assert bridge._calibration.total_windows == 2
    assert bridge._calibration.calibrated_windows == []


def test_close_closes_kwin_controller():
    bridge = create_bridge()
    bridge._kwin.close = AsyncMock()

    asyncio.run(bridge.close())

    bridge._kwin.close.assert_awaited_once_with()


def test_update_active_window_after_calibrated_window_disappears_does_not_notify_already_selected():
    already_selected = []

    bridge = DofusFocusBridge(
        on_calibration_already_selected=lambda: (
            already_selected.append(True)
        ),
    )

    update_windows(
        bridge,
        ["window-1", "window-2", "window-3", "window-4"],
    )
    bridge.update_active_window("window-1")
    bridge.update_active_window("window-2")

    # KWin activates window-1 automatically after window-2 closes.
    bridge.update_active_window("window-1")

    # Then KWin reports that window-2 disappeared.
    update_windows(
        bridge,
        ["window-1", "window-3", "window-4"],
    )

    assert already_selected == []
    assert bridge._calibration.calibrating is False
    assert bridge._calibration.calibrated is False


def test_update_windows_rejects_invalid_json():
    bridge = create_bridge()

    with pytest.raises(
        ValueError,
        match="Invalid windows JSON",
    ):
        bridge.update_windows("{invalid")


def test_update_windows_rejects_non_list_json():
    bridge = create_bridge()

    with pytest.raises(
        TypeError,
        match="Windows data must be a list",
    ):
        bridge.update_windows(json.dumps({"window": "window-1"}))


def test_update_windows_rejects_non_string_window_ids():
    bridge = create_bridge()

    with pytest.raises(
        TypeError,
        match="Windows data must contain only strings",
    ):
        bridge.update_windows(
            json.dumps(["window-1", 123]),
        )


def test_update_windows_accepts_empty_list():
    bridge = create_bridge()

    bridge.update_windows(json.dumps([]))

    assert bridge._windows.windows == []
    assert bridge._calibration.total_windows == 0
