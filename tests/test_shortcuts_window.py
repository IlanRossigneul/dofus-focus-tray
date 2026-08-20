import threading
import time

from PySide6.QtWidgets import QApplication

from shortcuts.listener import ShortcutListener
from shortcuts.model import Shortcut
from shortcuts.storage import ShortcutConfiguration, ShortcutStorage
from ui.shortcuts_window import (
    ShortcutCaptureWorker,
    ShortcutsWindow,
)


def get_qapplication():
    application = QApplication.instance()

    if application is None:
        application = QApplication([])

    return application


def make_window(tmp_path):
    get_qapplication()

    return ShortcutsWindow(
        storage_path=tmp_path / "shortcuts.json",
    )


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

    assert (
        window._buttons[
            ("calibration", "primary")
        ].text()
        == "CTRL + D"
    )

    assert (
        window._buttons[
            ("calibration", "alternate")
        ].text()
        == "BTN_SIDE"
    )

    assert (
        window._buttons[
            ("next", "primary")
        ].text()
        == "ALT + RIGHT"
    )

    assert (
        window._buttons[
            ("next", "alternate")
        ].text()
        == "—"
    )

    assert (
        window._buttons[
            ("previous", "primary")
        ].text()
        == "CTRL + LEFT"
    )

    assert (
        window._buttons[
            ("previous", "alternate")
        ].text()
        == "F"
    )

    window.close()


def test_starting_capture_disables_all_controls(
    tmp_path,
    monkeypatch,
):
    window = make_window(tmp_path)

    class FakeWorker:
        def __init__(
            self,
            callback,
            error_callback,
        ):
            self.callback = callback
            self.error_callback = error_callback

        def start(self):
            pass

    monkeypatch.setattr(
        "ui.shortcuts_window.ShortcutCaptureWorker",
        FakeWorker,
    )

    target = window._buttons[
        ("calibration", "primary")
    ]

    window._start_capture(
        "calibration",
        "primary",
    )

    assert window._capture_active is True
    assert window._capture_target == (
        "calibration",
        "primary",
    )

    assert window._save_button.isEnabled() is False
    assert window._quit_button.isEnabled() is False

    for button in window._buttons.values():
        assert button.isEnabled() is False

    assert target.text() == "Appuyez sur une touche..."

    window.close()


def test_capture_result_updates_only_targeted_shortcut(
    tmp_path,
):
    window = make_window(tmp_path)

    window._capture_target = (
        "calibration",
        "primary",
    )
    window._capture_active = True

    shortcut = Shortcut(
        trigger="D",
        modifiers=frozenset({"CTRL"}),
    )

    window._handle_shortcut_captured(
        shortcut,
    )

    assert (
        window._configurations[
            "calibration"
        ].primary
        == shortcut
    )

    assert (
        window._configurations[
            "calibration"
        ].alternate
        is None
    )

    assert (
        window._configurations[
            "next"
        ].primary
        is None
    )

    assert (
        window._configurations[
            "previous"
        ].primary
        is None
    )

    assert (
        window._buttons[
            ("calibration", "primary")
        ].text()
        == "CTRL + D"
    )

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

    window._capture_target = (
        "calibration",
        "primary",
    )
    window._capture_active = True

    window._handle_shortcut_captured(
        replacement,
    )

    assert (
        window._configurations[
            "calibration"
        ].primary
        == replacement
    )

    assert (
        window._buttons[
            ("calibration", "primary")
        ].text()
        == "ALT + F"
    )

    window.close()


def test_primary_and_alternate_are_independent(
    tmp_path,
):
    window = make_window(tmp_path)

    primary = Shortcut(
        trigger="D",
    )

    alternate = Shortcut(
        trigger="BTN_SIDE",
    )

    window._capture_target = (
        "calibration",
        "primary",
    )
    window._capture_active = True

    window._handle_shortcut_captured(
        primary,
    )

    window._capture_target = (
        "calibration",
        "alternate",
    )
    window._capture_active = True

    window._handle_shortcut_captured(
        alternate,
    )

    assert (
        window._configurations[
            "calibration"
        ].primary
        == primary
    )

    assert (
        window._configurations[
            "calibration"
        ].alternate
        == alternate
    )

    assert (
        window._buttons[
            ("calibration", "primary")
        ].text()
        == "D"
    )

    assert (
        window._buttons[
            ("calibration", "alternate")
        ].text()
        == "BTN_SIDE"
    )

    window.close()


def test_capture_result_reenables_all_controls(
    tmp_path,
):
    window = make_window(tmp_path)

    window._capture_target = (
        "calibration",
        "primary",
    )
    window._capture_active = True

    for button in window._buttons.values():
        button.setEnabled(False)

    window._save_button.setEnabled(False)
    window._quit_button.setEnabled(False)

    window._handle_shortcut_captured(
        Shortcut("D"),
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
    capsys,
):
    window = make_window(tmp_path)

    existing = Shortcut(
        trigger="D",
        modifiers=frozenset({"CTRL"}),
    )

    window._configurations[
        "calibration"
    ].primary = existing

    window._update_buttons()

    window._capture_target = (
        "calibration",
        "primary",
    )
    window._capture_active = True

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

    assert (
        window._configurations[
            "calibration"
        ].primary
        == existing
    )

    assert (
        window._buttons[
            ("calibration", "primary")
        ].text()
        == "CTRL + D"
    )

    assert window._save_button.isEnabled() is True
    assert window._quit_button.isEnabled() is True

    for button in window._buttons.values():
        assert button.isEnabled() is True

    output = capsys.readouterr().out

    assert (
        "[SHORTCUTS WINDOW] Shortcut capture failed:"
        in output
    )

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

    window._capture_target = (
        "calibration",
        "primary",
    )
    window._capture_active = True

    window._handle_shortcut_captured(
        replacement,
    )

    loaded = storage.load()

    assert (
        loaded["calibration"].primary
        == original
    )

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

    window._configurations[
        "calibration"
    ].primary = calibration_primary

    window._configurations[
        "next"
    ].primary = next_primary

    window._configurations[
        "previous"
    ].alternate = previous_alternate

    window._update_buttons()

    window._save()

    storage = ShortcutStorage(path)
    loaded = storage.load()

    assert (
        loaded["calibration"].primary
        == calibration_primary
    )

    assert (
        loaded["next"].primary
        == next_primary
    )

    assert (
        loaded["previous"].alternate
        == previous_alternate
    )

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

    window._configurations[
        "calibration"
    ].primary = Shortcut(
        trigger="F",
    )

    window._update_buttons()

    window.close()

    loaded = storage.load()

    assert (
        loaded["calibration"].primary
        == original
    )


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
    monkeypatch,
):
    window = make_window(tmp_path)

    starts = []

    class FakeWorker:
        def __init__(
            self,
            callback,
            error_callback,
        ):
            pass

        def start(self):
            starts.append(True)

    monkeypatch.setattr(
        "ui.shortcuts_window.ShortcutCaptureWorker",
        FakeWorker,
    )

    window._start_capture(
        "calibration",
        "primary",
    )

    window._start_capture(
        "calibration",
        "alternate",
    )

    assert len(starts) == 1

    assert window._capture_target == (
        "calibration",
        "primary",
    )

    window._capture_active = False
    window.close()


def test_capture_worker_runs_capture_outside_gui_thread(
    monkeypatch,
):
    captured_threads = []
    finished = threading.Event()

    class FakeKeyboardLayout:
        async def connect(self):
            pass

        async def close(self):
            pass

    def fake_listener_capture(self):
        captured_threads.append(
            threading.current_thread().name,
        )
        finished.set()

        return Shortcut("D")

    monkeypatch.setattr(
        "ui.shortcuts_window.KeyboardLayout",
        FakeKeyboardLayout,
    )

    monkeypatch.setattr(
        "ui.shortcuts_window.ShortcutListener.capture",
        fake_listener_capture,
    )

    worker = ShortcutCaptureWorker(
        callback=lambda shortcut: None,
        error_callback=lambda error: None,
    )

    gui_thread = threading.current_thread().name

    worker.start()

    assert finished.wait(timeout=2)

    assert len(captured_threads) == 1
    assert captured_threads[0] != gui_thread
    assert captured_threads[0] == "ShortcutCaptureThread"
