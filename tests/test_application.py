from unittest.mock import Mock

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
