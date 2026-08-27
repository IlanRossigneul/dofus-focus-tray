from bridge.windows import WindowsController


def create_controller() -> WindowsController:
    return WindowsController()


def test_windows_are_empty_on_initialization():
    controller = create_controller()

    assert controller.windows == []


def test_update_windows_replaces_live_windows():
    controller = create_controller()

    controller.update_windows(
        ["window-1", "window-2"]
    )

    assert controller.windows == [
        "window-1",
        "window-2",
    ]

    controller.update_windows(
        ["window-3"]
    )

    assert controller.windows == ["window-3"]


def test_windows_property_returns_a_copy():
    controller = create_controller()
    controller.update_windows(
        ["window-1", "window-2"]
    )

    windows = controller.windows
    windows.append("window-3")

    assert controller.windows == [
        "window-1",
        "window-2",
    ]


def test_update_active_window_stores_active_window():
    controller = create_controller()

    controller.update_active_window("window-2")

    assert controller.active_window == "window-2"


def test_update_active_window_replaces_previous_active_window():
    controller = create_controller()

    controller.update_active_window("window-1")
    controller.update_active_window("window-2")

    assert controller.active_window == "window-2"
