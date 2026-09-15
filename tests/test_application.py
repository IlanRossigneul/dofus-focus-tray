import logging
from unittest.mock import Mock

from PySide6.QtCore import QLockFile

from app.application import Application
from notifications.dofus_notifications import DofusNotificationManager


def test_calibration_started_with_no_windows_notifies_user():
    application = Application()

    notification_manager = Mock(
        spec=DofusNotificationManager,
    )

    application.notification_manager = notification_manager

    application._handle_calibration_started(0)

    notification_manager.notify_calibration_no_windows.assert_called_once_with()


def test_calibration_started_with_one_window_notifies_user():
    application = Application()

    notification_manager = Mock(
        spec=DofusNotificationManager,
    )

    application.notification_manager = notification_manager

    application._handle_calibration_started(1)

    notification_manager.notify_calibration_one_window.assert_called_once_with()


def test_calibration_started_with_multiple_windows_notifies_user():
    application = Application()

    notification_manager = Mock(
        spec=DofusNotificationManager,
    )

    application.notification_manager = notification_manager

    application._handle_calibration_started(
        window_count=3,
        step=0,
    )

    notification_manager.notify_calibration_multiple_windows.assert_called_once_with(
        window_count=3,
        step=0,
        summary=None,
    )


def test_calibration_started_with_multiple_windows_selection_notifies_user():
    application = Application()

    notification_manager = Mock(
        spec=DofusNotificationManager,
    )

    application.notification_manager = notification_manager

    application._handle_calibration_started(
        window_count=3,
        step=1,
    )

    notification_manager.notify_calibration_multiple_windows.assert_called_once_with(
        window_count=3,
        step=1,
        summary=None,
    )


def test_calibration_started_with_multiple_windows_completion_notifies_user():
    application = Application()

    notification_manager = Mock(
        spec=DofusNotificationManager,
    )

    application.notification_manager = notification_manager

    summary = (
        "Compte 2, Compte 1 et Compte 3"
    )

    application._handle_calibration_started(
        window_count=3,
        step=3,
        summary=summary,
    )

    notification_manager.notify_calibration_multiple_windows.assert_called_once_with(
        window_count=3,
        step=3,
        summary=summary,
    )


def test_calibration_already_selected_window_notifies_user():
    application = Application()

    notification_manager = Mock(
        spec=DofusNotificationManager,
    )

    application.notification_manager = notification_manager

    application._handle_calibration_already_selected()

    notification_manager.notify_calibration_already_selected.assert_called_once_with()


def test_calibration_cancelled_by_calibrated_window_closing_notifies_user():
    application = Application()

    notification_manager = Mock(
        spec=DofusNotificationManager,
    )

    application.notification_manager = notification_manager

    application._handle_calibration_cancelled()

    notification_manager.notify_calibration_cancelled.assert_called_once_with()


def test_application_notifies_when_new_window_is_detected():
    application = Application()

    notification_manager = Mock(
        spec=DofusNotificationManager,
    )

    application.notification_manager = notification_manager

    application._handle_new_window_detected()

    notification_manager.notify_new_window.assert_called_once_with()


def test_application_notifies_first_calibration_step_when_active_window_is_already_selected():
    application = Application()

    notification_manager = Mock(
        spec=DofusNotificationManager,
    )

    application.notification_manager = notification_manager

    application._handle_calibration_started(
        3,
        1,
        None,
    )

    notification_manager.notify_calibration_multiple_windows.assert_called_once_with(
        window_count=3,
        step=1,
        summary=None,
    )


def test_run_shortcuts_logs_failure_and_cleans_up_xkb(
    monkeypatch,
    caplog,
):
    application = Application()

    xkb = Mock()

    def fail_load():
        raise RuntimeError("test failure")

    xkb.load_wayland_keymap.side_effect = fail_load

    monkeypatch.setattr(
        "app.application.Xkb",
        Mock(return_value=xkb),
    )

    with caplog.at_level(logging.ERROR):
        application._run_shortcuts()

    xkb.close.assert_called_once_with()
    assert application.shortcut_service is None

    assert "Shortcut thread failed" in caplog.text
    assert "test failure" in caplog.text


def test_acquire_instance_lock_succeeds():
    application = Application()

    application._instance_lock = Mock(
        spec=QLockFile,
    )
    application._instance_lock.tryLock.return_value = True

    assert application._acquire_instance_lock()

    application._instance_lock.tryLock.assert_called_once_with(0)


def test_acquire_instance_lock_fails_when_another_instance_is_running(
    caplog,
):
    application = Application()

    application._instance_lock = Mock(
        spec=QLockFile,
    )
    application._instance_lock.tryLock.return_value = False

    with caplog.at_level(logging.WARNING):
        assert not application._acquire_instance_lock()

    application._instance_lock.tryLock.assert_called_once_with(0)

    assert (
        "Another Dofus Focus Tray instance is already running."
        in caplog.text
    )


def test_instance_lock_allows_only_one_holder(tmp_path):
    lock_path = tmp_path / "dofus-focus-tray.lock"

    first_lock = QLockFile(str(lock_path))
    second_lock = QLockFile(str(lock_path))

    first_lock.setStaleLockTime(0)
    second_lock.setStaleLockTime(0)

    assert first_lock.tryLock(0)
    assert not second_lock.tryLock(0)

    first_lock.unlock()

    assert second_lock.tryLock(0)

    second_lock.unlock()
