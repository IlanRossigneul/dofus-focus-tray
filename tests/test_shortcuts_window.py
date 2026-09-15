from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from shortcuts.model import Shortcut
from shortcuts.storage import ShortcutConfiguration, ShortcutStorage
from ui.shortcuts_window import ShortcutsWindow


class FakeShortcutService:
    """Provide a controllable shortcut service for window tests."""

    def __init__(self) -> None:
        self.start_capture_calls = []
        self.stop_capture_calls = 0

    def start_capture(
        self,
        allowed_mouse_buttons=None,
        callback=None,
        error_callback=None,
        rejected_callback=None,
    ) -> None:
        self.start_capture_calls.append(
            {
                "allowed_mouse_buttons": allowed_mouse_buttons,
                "callback": callback,
                "error_callback": error_callback,
                "rejected_callback": rejected_callback,
            }
        )

    def stop_capture(self) -> None:
        self.stop_capture_calls += 1


def get_qapplication():
    application = QApplication.instance()

    if application is None:
        application = QApplication([])

    return application


def make_window(tmp_path):
    get_qapplication()

    service = FakeShortcutService()

    window = ShortcutsWindow(
        shortcut_service=service,
        storage_path=tmp_path / "shortcuts.json",
    )

    window._test_shortcut_service = service

    return window


def start_fake_capture(
    window,
    target,
):
    configuration_name, shortcut_type = target

    window._capture_target = target
    window._capture_original = getattr(
        window._configurations[configuration_name],
        shortcut_type,
    )
    window._capture_active = True


def press_key(
    window,
    key,
):
    event = QKeyEvent(
        QEvent.Type.KeyPress,
        key,
        Qt.KeyboardModifier.NoModifier,
    )

    window.keyPressEvent(event)

    return event


def test_window_has_expected_title(tmp_path):
    window = make_window(tmp_path)

    assert window.windowTitle() == "Configuration des raccourcis"

    window.close()


def test_window_has_all_shortcut_fields(tmp_path):
    window = make_window(tmp_path)

    expected_fields = {
        ("calibration", "primary"),
        ("calibration", "alternate"),
        ("next", "primary"),
        ("next", "alternate"),
        ("previous", "primary"),
        ("previous", "alternate"),
    }

    assert set(window._buttons) == expected_fields

    window.close()


def test_empty_shortcuts_are_displayed_as_dash(tmp_path):
    window = make_window(tmp_path)

    for button in window._buttons.values():
        assert button.text() == "—"

    window.close()


def test_existing_shortcuts_are_loaded_and_displayed(
    tmp_path,
):
    storage = ShortcutStorage(
        tmp_path / "shortcuts.json",
    )

    storage.save(
        {
            "calibration": ShortcutConfiguration(
                primary=Shortcut(
                    trigger="D",
                    modifiers=frozenset({"CTRL"}),
                ),
                alternate=Shortcut(
                    trigger="BTN_SIDE",
                ),
            ),
            "next": ShortcutConfiguration(
                primary=Shortcut(
                    trigger="RIGHT",
                    modifiers=frozenset({"ALT"}),
                ),
            ),
            "previous": ShortcutConfiguration(
                primary=Shortcut(
                    trigger="LEFT",
                    modifiers=frozenset({"CTRL"}),
                ),
                alternate=Shortcut(
                    trigger="F",
                ),
            ),
        },
    )

    window = make_window(tmp_path)

    assert window._buttons[("calibration", "primary")].text() == "CTRL + D"

    assert window._buttons[("calibration", "alternate")].text() == "BTN_SIDE"

    assert window._buttons[("next", "primary")].text() == "ALT + RIGHT"

    assert window._buttons[("next", "alternate")].text() == "—"

    assert window._buttons[("previous", "primary")].text() == "CTRL + LEFT"

    assert window._buttons[("previous", "alternate")].text() == "F"

    window.close()


def test_starting_calibration_capture_uses_no_mouse_buttons(
    tmp_path,
):
    window = make_window(tmp_path)
    service = window._test_shortcut_service

    window._start_capture(
        "calibration",
        "primary",
    )

    assert len(service.start_capture_calls) == 1

    call = service.start_capture_calls[0]

    assert call["allowed_mouse_buttons"] == set()
    assert call["callback"] == window.shortcut_captured.emit
    assert call["error_callback"] == window.capture_failed.emit
    assert call["rejected_callback"] == window.capture_rejected.emit

    window.close()


def test_starting_regular_capture_allows_configured_mouse_buttons(
    tmp_path,
):
    window = make_window(tmp_path)
    service = window._test_shortcut_service

    window._start_capture(
        "next",
        "primary",
    )

    assert len(service.start_capture_calls) == 1

    call = service.start_capture_calls[0]

    assert call["allowed_mouse_buttons"] is None

    window.close()


def test_starting_capture_disables_all_controls_except_target(
    tmp_path,
):
    window = make_window(tmp_path)

    target = window._buttons[("calibration", "primary")]

    window._start_capture(
        "calibration",
        "primary",
    )

    assert window._capture_active is True
    assert window._capture_target == (
        "calibration",
        "primary",
    )
    assert window._capture_original is None

    assert window._save_button.isEnabled() is False
    assert window._quit_button.isEnabled() is False

    for key, button in window._buttons.items():
        if key == ("calibration", "primary"):
            assert button.isEnabled() is True
        else:
            assert button.isEnabled() is False

    assert target.text() == "Appuyez sur une touche..."

    window.close()


def test_capture_result_updates_targeted_shortcut(
    tmp_path,
):
    window = make_window(tmp_path)

    start_fake_capture(
        window,
        ("calibration", "primary"),
    )

    shortcut = Shortcut(
        trigger="D",
        modifiers=frozenset({"CTRL"}),
    )

    window._handle_shortcut_captured(
        shortcut,
    )

    assert window._configurations["calibration"].primary == shortcut

    assert window._configurations["calibration"].alternate is None

    assert window._configurations["next"].primary is None

    assert window._configurations["previous"].primary is None

    assert window._buttons[("calibration", "primary")].text() == "CTRL + D"

    assert window._capture_active is False
    assert window._capture_target is None

    window.close()


def test_capture_result_stops_capture_service(
    tmp_path,
):
    window = make_window(tmp_path)
    service = window._test_shortcut_service

    start_fake_capture(
        window,
        ("calibration", "primary"),
    )

    window._handle_shortcut_captured(
        Shortcut(
            trigger="D",
            modifiers=frozenset({"CTRL"}),
        ),
    )

    assert service.stop_capture_calls == 1

    window.close()


def test_capture_can_replace_existing_shortcut(
    tmp_path,
):
    storage = ShortcutStorage(
        tmp_path / "shortcuts.json",
    )

    original = Shortcut(
        trigger="D",
        modifiers=frozenset({"CTRL"}),
    )

    storage.save(
        {
            "calibration": ShortcutConfiguration(
                primary=original,
            ),
        },
    )

    window = make_window(tmp_path)

    replacement = Shortcut(
        trigger="F",
        modifiers=frozenset({"ALT"}),
    )

    start_fake_capture(
        window,
        ("calibration", "primary"),
    )

    window._handle_shortcut_captured(
        replacement,
    )

    assert window._configurations["calibration"].primary == replacement

    assert window._buttons[("calibration", "primary")].text() == "ALT + F"

    window.close()


def test_same_shortcut_can_be_kept_in_same_field(
    tmp_path,
):
    window = make_window(tmp_path)

    existing = Shortcut(
        trigger="D",
        modifiers=frozenset({"CTRL"}),
    )

    window._configurations["calibration"].primary = existing

    start_fake_capture(
        window,
        ("calibration", "primary"),
    )

    window._handle_shortcut_captured(
        existing,
    )

    assert window._configurations["calibration"].primary == existing

    assert window._capture_active is False
    assert window._capture_target is None

    window.close()


def test_duplicate_shortcut_does_not_modify_configuration(
    tmp_path,
):
    window = make_window(tmp_path)

    existing = Shortcut(
        trigger="D",
        modifiers=frozenset({"CTRL"}),
    )

    original_target = Shortcut(
        trigger="F",
        modifiers=frozenset({"ALT"}),
    )

    window._configurations["calibration"].primary = existing

    window._configurations["next"].primary = original_target

    start_fake_capture(
        window,
        ("previous", "primary"),
    )

    window._handle_shortcut_captured(
        existing,
    )

    assert window._configurations["calibration"].primary == existing

    assert window._configurations["next"].primary == original_target

    assert window._configurations["previous"].primary is None

    assert window._capture_active is True
    assert window._capture_target == (
        "previous",
        "primary",
    )

    window.close()


def test_primary_and_alternate_are_independent(
    tmp_path,
):
    window = make_window(tmp_path)

    primary = Shortcut(
        trigger="D",
        modifiers=frozenset({"CTRL"}),
    )

    alternate = Shortcut(
        trigger="BTN_SIDE",
    )

    start_fake_capture(
        window,
        ("calibration", "primary"),
    )

    window._handle_shortcut_captured(
        primary,
    )

    start_fake_capture(
        window,
        ("calibration", "alternate"),
    )

    window._handle_shortcut_captured(
        alternate,
    )

    assert window._configurations["calibration"].primary == primary

    assert window._configurations["calibration"].alternate == alternate

    assert window._buttons[("calibration", "primary")].text() == "CTRL + D"

    assert window._buttons[("calibration", "alternate")].text() == "BTN_SIDE"

    window.close()


def test_capture_result_reenables_all_controls(
    tmp_path,
):
    window = make_window(tmp_path)

    start_fake_capture(
        window,
        ("calibration", "primary"),
    )

    for button in window._buttons.values():
        button.setEnabled(False)

    window._save_button.setEnabled(False)
    window._quit_button.setEnabled(False)

    window._handle_shortcut_captured(
        Shortcut(
            trigger="D",
            modifiers=frozenset({"CTRL"}),
        ),
    )

    assert window._capture_active is False
    assert window._capture_target is None

    assert window._save_button.isEnabled() is True
    assert window._quit_button.isEnabled() is True

    for button in window._buttons.values():
        assert button.isEnabled() is True

    window.close()


def test_capture_failure_restores_current_configuration(
    tmp_path,
    caplog,
):
    window = make_window(tmp_path)

    existing = Shortcut(
        trigger="D",
        modifiers=frozenset({"CTRL"}),
    )

    window._configurations["calibration"].primary = existing

    window._update_buttons()

    start_fake_capture(
        window,
        ("calibration", "primary"),
    )

    for button in window._buttons.values():
        button.setEnabled(False)

    window._save_button.setEnabled(False)
    window._quit_button.setEnabled(False)

    error = RuntimeError("capture failed")

    window._handle_capture_failed(
        error,
    )

    assert window._capture_active is False
    assert window._capture_target is None

    assert window._configurations["calibration"].primary == existing

    assert window._buttons[("calibration", "primary")].text() == "CTRL + D"

    assert window._save_button.isEnabled() is True
    assert window._quit_button.isEnabled() is True

    for button in window._buttons.values():
        assert button.isEnabled() is True

    assert "Shortcut capture failed" in caplog.text

    window.close()


def test_capture_failure_stops_capture_service(
    tmp_path,
):
    window = make_window(tmp_path)
    service = window._test_shortcut_service

    start_fake_capture(
        window,
        ("calibration", "primary"),
    )

    window._handle_capture_failed(
        RuntimeError("capture failed"),
    )

    assert service.stop_capture_calls == 1

    window.close()


def test_new_shortcut_is_not_saved_before_save(
    tmp_path,
):
    path = tmp_path / "shortcuts.json"

    storage = ShortcutStorage(path)

    original = Shortcut(
        trigger="D",
    )

    storage.save(
        {
            "calibration": ShortcutConfiguration(
                primary=original,
            ),
        },
    )

    window = make_window(tmp_path)

    replacement = Shortcut(
        trigger="F",
    )

    start_fake_capture(
        window,
        ("calibration", "primary"),
    )

    window._handle_shortcut_captured(
        replacement,
    )

    loaded = storage.load()

    assert loaded["calibration"].primary == original

    window.close()


def test_save_persists_current_configuration(
    tmp_path,
):
    path = tmp_path / "shortcuts.json"

    window = make_window(tmp_path)

    calibration_primary = Shortcut(
        trigger="D",
        modifiers=frozenset({"CTRL"}),
    )

    next_primary = Shortcut(
        trigger="RIGHT",
        modifiers=frozenset({"ALT"}),
    )

    previous_alternate = Shortcut(
        trigger="BTN_SIDE",
    )

    window._configurations["calibration"].primary = calibration_primary

    window._configurations["next"].primary = next_primary

    window._configurations["previous"].alternate = previous_alternate

    window._update_buttons()

    window._save()

    storage = ShortcutStorage(path)
    loaded = storage.load()

    assert loaded["calibration"].primary == calibration_primary

    assert loaded["next"].primary == next_primary

    assert loaded["previous"].alternate == previous_alternate

    assert window.isVisible() is False


def test_quit_does_not_save_unsaved_changes(
    tmp_path,
):
    path = tmp_path / "shortcuts.json"

    original = Shortcut(
        trigger="D",
    )

    storage = ShortcutStorage(path)

    storage.save(
        {
            "calibration": ShortcutConfiguration(
                primary=original,
            ),
        },
    )

    window = make_window(tmp_path)

    window._configurations["calibration"].primary = Shortcut(
        trigger="F",
    )

    window._update_buttons()

    window.close()

    loaded = storage.load()

    assert loaded["calibration"].primary == original


def test_close_is_ignored_while_capture_is_active(
    tmp_path,
):
    window = make_window(tmp_path)

    window._capture_active = True

    window.show()
    get_qapplication().processEvents()

    window.close()

    assert window.isVisible() is True

    window._capture_active = False
    window.close()


def test_close_is_allowed_after_capture_finishes(
    tmp_path,
):
    window = make_window(tmp_path)

    window._capture_active = True
    window._capture_active = False

    window.show()
    get_qapplication().processEvents()

    window.close()

    assert window.isVisible() is False


def test_second_capture_is_ignored_while_capture_is_active(
    tmp_path,
):
    window = make_window(tmp_path)
    service = window._test_shortcut_service

    window._start_capture(
        "calibration",
        "primary",
    )

    window._start_capture(
        "calibration",
        "alternate",
    )

    assert len(service.start_capture_calls) == 1

    assert window._capture_target == (
        "calibration",
        "primary",
    )

    window._capture_active = False
    window.close()


def test_duplicate_shortcut_shows_capture_error(
    tmp_path,
):
    window = make_window(tmp_path)

    existing = Shortcut(
        trigger="D",
        modifiers=frozenset({"CTRL"}),
    )

    target = (
        "next",
        "primary",
    )

    window._configurations["calibration"].primary = existing

    start_fake_capture(
        window,
        target,
    )

    window._handle_shortcut_captured(
        existing,
    )

    button = window._buttons[target]

    assert button.text() == "Raccourci déjà utilisé"
    assert button._capture_error is True
    assert window._capture_active is True
    assert window._capture_target == target

    window.close()


def test_duplicate_shortcut_starts_cancel_timer(
    tmp_path,
):
    window = make_window(tmp_path)

    existing = Shortcut(
        trigger="D",
        modifiers=frozenset({"CTRL"}),
    )

    target = (
        "next",
        "primary",
    )

    window._configurations["calibration"].primary = existing

    start_fake_capture(
        window,
        target,
    )

    window._handle_shortcut_captured(
        existing,
    )

    assert window._duplicate_timer.isActive() is True
    assert window._duplicate_timer.interval() == 2000

    window.close()


def test_duplicate_timeout_cancels_capture(
    tmp_path,
):
    window = make_window(tmp_path)

    original = Shortcut(
        trigger="F",
        modifiers=frozenset({"ALT"}),
    )

    duplicate = Shortcut(
        trigger="D",
        modifiers=frozenset({"CTRL"}),
    )

    target = (
        "next",
        "primary",
    )

    window._configurations["next"].primary = original

    window._configurations["calibration"].primary = duplicate

    start_fake_capture(
        window,
        target,
    )

    window._handle_shortcut_captured(
        duplicate,
    )

    window._duplicate_timer.timeout.emit()

    assert window._capture_active is False
    assert window._capture_target is None

    assert window._configurations["next"].primary == original

    assert window._buttons[target].text() == "ALT + F"
    assert window._buttons[target].styleSheet() == ""

    window.close()


def test_capture_after_duplicate_clears_capture_error(
    tmp_path,
):
    window = make_window(tmp_path)

    existing = Shortcut(
        trigger="D",
        modifiers=frozenset({"CTRL"}),
    )

    target = (
        "next",
        "primary",
    )

    window._configurations["calibration"].primary = existing

    start_fake_capture(
        window,
        target,
    )

    window._handle_shortcut_captured(
        existing,
    )

    replacement = Shortcut(
        trigger="F",
        modifiers=frozenset({"ALT"}),
    )

    window._handle_shortcut_captured(
        replacement,
    )

    button = window._buttons[target]

    assert button.text() == "ALT + F"
    assert button.styleSheet() == ""
    assert button._capture_error is False
    assert window._capture_active is False
    assert window._capture_target is None

    assert window._configurations["next"].primary == replacement

    assert window._duplicate_timer.isActive() is False

    window.close()


def test_escape_cancels_capture_and_restores_original_shortcut(
    tmp_path,
):
    window = make_window(tmp_path)

    target = (
        "calibration",
        "primary",
    )

    existing = Shortcut(
        trigger="D",
        modifiers=frozenset({"CTRL"}),
    )

    window._configurations["calibration"].primary = existing

    window._update_buttons()

    start_fake_capture(
        window,
        target,
    )

    event = press_key(
        window,
        Qt.Key.Key_Escape,
    )

    assert window._configurations["calibration"].primary == existing

    assert window._buttons[target].text() == "CTRL + D"
    assert window._capture_active is False
    assert window._capture_target is None
    assert event.isAccepted() is True

    window.close()


def test_escape_cancels_capture_without_creating_shortcut(
    tmp_path,
):
    window = make_window(tmp_path)

    target = (
        "calibration",
        "primary",
    )

    start_fake_capture(
        window,
        target,
    )

    event = press_key(
        window,
        Qt.Key.Key_Escape,
    )

    assert window._configurations["calibration"].primary is None

    assert window._buttons[target].text() == "—"
    assert window._capture_active is False
    assert window._capture_target is None
    assert event.isAccepted() is True

    window.close()


def test_backspace_clears_current_shortcut(
    tmp_path,
):
    window = make_window(tmp_path)

    target = (
        "calibration",
        "primary",
    )

    start_fake_capture(
        window,
        target,
    )

    event = press_key(
        window,
        Qt.Key.Key_Backspace,
    )

    assert window._configurations["calibration"].primary is None

    assert window._buttons[target].text() == "—"
    assert window._capture_active is False
    assert window._capture_target is None
    assert event.isAccepted() is True

    window.close()


def test_backspace_clears_existing_shortcut(
    tmp_path,
):
    window = make_window(tmp_path)

    target = (
        "calibration",
        "primary",
    )

    existing = Shortcut(
        trigger="D",
        modifiers=frozenset({"CTRL"}),
    )

    window._configurations["calibration"].primary = existing

    window._update_buttons()

    start_fake_capture(
        window,
        target,
    )

    event = press_key(
        window,
        Qt.Key.Key_Backspace,
    )

    assert window._configurations["calibration"].primary is None

    assert window._buttons[target].text() == "—"
    assert window._capture_active is False
    assert window._capture_target is None
    assert event.isAccepted() is True

    window.close()


def test_backspace_clears_capture_error(
    tmp_path,
):
    window = make_window(tmp_path)

    target = (
        "next",
        "primary",
    )

    existing = Shortcut(
        trigger="D",
        modifiers=frozenset({"CTRL"}),
    )

    window._configurations["calibration"].primary = existing

    start_fake_capture(
        window,
        target,
    )

    window._handle_shortcut_captured(
        existing,
    )

    event = press_key(
        window,
        Qt.Key.Key_Backspace,
    )

    assert window._configurations["next"].primary is None

    assert window._buttons[target].text() == "—"
    assert window._capture_active is False
    assert window._capture_target is None
    assert event.isAccepted() is True

    window.close()


def test_reload_stops_active_capture(
    tmp_path,
):
    window = make_window(tmp_path)
    service = window._test_shortcut_service

    window._start_capture(
        "calibration",
        "primary",
    )

    window.reload()

    assert service.stop_capture_calls == 1
    assert window._capture_active is False
    assert window._capture_target is None

    window.close()
