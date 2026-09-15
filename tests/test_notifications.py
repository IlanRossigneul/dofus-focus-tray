from unittest.mock import Mock

from app.application import Application
from notifications.dofus_notifications import (
    DofusNotificationManager,
)


def test_calibration_no_windows_creates_expected_notification(
    monkeypatch,
):
    notification = Mock()

    monkeypatch.setattr(
        "notifications.dofus_notifications.Notify.Notification.new",
        Mock(return_value=notification),
    )

    manager = DofusNotificationManager()

    manager.notify_calibration_no_windows()

    notification.set_timeout.assert_called_once_with(10000)

    notification.set_hint.assert_called_once()

    hint_name, hint_value = notification.set_hint.call_args.args

    assert hint_name == "desktop-entry"
    assert hint_value.unpack() == "dofus-focus-tray"

    notification.show.assert_called_once()


def test_calibration_no_windows_uses_expected_content(
    monkeypatch,
):
    notification = Mock()

    new_notification = Mock(
        return_value=notification,
    )

    monkeypatch.setattr(
        "notifications.dofus_notifications.Notify.Notification.new",
        new_notification,
    )

    manager = DofusNotificationManager()

    manager.notify_calibration_no_windows()

    new_notification.assert_called_once_with(
        "Calibration",
        "0 compte détecté\nVeuillez relancer la calibration avec vos comptes ouverts.",
        "",
    )


def test_application_notifies_when_calibration_starts_with_no_windows():
    application = Application()

    notification_manager = Mock(
        spec=DofusNotificationManager,
    )

    application.notification_manager = notification_manager

    application._handle_calibration_started(0)

    notification_manager.notify_calibration_no_windows.assert_called_once_with()


def test_application_does_not_notify_when_windows_are_detected():
    application = Application()

    notification_manager = Mock(
        spec=DofusNotificationManager,
    )

    application.notification_manager = notification_manager

    application._handle_calibration_started(1)
    application._handle_calibration_started(2)

    notification_manager.notify_calibration_no_windows.assert_not_called()


def test_application_does_not_notify_without_notification_manager():
    application = Application()

    application._handle_calibration_started(0)


def test_calibration_one_window_uses_expected_content(
    monkeypatch,
):
    notification = Mock()

    new_notification = Mock(
        return_value=notification,
    )

    monkeypatch.setattr(
        "notifications.dofus_notifications.Notify.Notification.new",
        new_notification,
    )

    manager = DofusNotificationManager()

    manager.notify_calibration_one_window()

    new_notification.assert_called_once_with(
        "Calibration",
        "1 Compte détecté\nCalibration terminée.",
        "",
    )


def test_application_notifies_when_calibration_starts_with_one_window():
    application = Application()

    notification_manager = Mock(
        spec=DofusNotificationManager,
    )

    application.notification_manager = notification_manager

    application._handle_calibration_started(1)

    notification_manager.notify_calibration_one_window.assert_called_once_with()


def test_application_does_not_notify_one_window_without_notification_manager():
    application = Application()

    application._handle_calibration_started(1)


def test_calibration_multiple_windows_uses_expected_content(
    monkeypatch,
):
    notification = Mock()

    new_notification = Mock(
        return_value=notification,
    )

    monkeypatch.setattr(
        "notifications.dofus_notifications.Notify.Notification.new",
        new_notification,
    )

    manager = DofusNotificationManager()

    manager.notify_calibration_multiple_windows(
        window_count=3,
    )

    new_notification.assert_called_once_with(
        "Calibration",
        "3 comptes détectés\nSélectionnez-les dans l'ordre souhaité.",
        "",
    )


def test_calibration_multiple_windows_with_active_window_uses_expected_content(
    monkeypatch,
):
    notification = Mock()

    new_notification = Mock(
        return_value=notification,
    )

    monkeypatch.setattr(
        "notifications.dofus_notifications.Notify.Notification.new",
        new_notification,
    )

    manager = DofusNotificationManager()

    manager.notify_calibration_multiple_windows(
        window_count=3,
        step=1,
    )

    new_notification.assert_called_once_with(
        "Calibration",
        "Étape 1 / 3\nSélectionnez maintenant le compte suivant.",
        "",
    )


def test_calibration_multiple_windows_step_uses_expected_content(
    monkeypatch,
):
    notification = Mock()

    new_notification = Mock(
        return_value=notification,
    )

    monkeypatch.setattr(
        "notifications.dofus_notifications.Notify.Notification.new",
        new_notification,
    )

    manager = DofusNotificationManager()

    manager.notify_calibration_multiple_windows(
        window_count=4,
        step=2,
    )

    new_notification.assert_called_once_with(
        "Calibration",
        "Étape 2 / 4\nSélectionnez maintenant le compte suivant.",
        "",
    )


def test_calibration_multiple_windows_last_step_uses_expected_content(
    monkeypatch,
):
    notification = Mock()

    new_notification = Mock(
        return_value=notification,
    )

    monkeypatch.setattr(
        "notifications.dofus_notifications.Notify.Notification.new",
        new_notification,
    )

    manager = DofusNotificationManager()

    manager.notify_calibration_multiple_windows(
        window_count=4,
        step=3,
    )

    new_notification.assert_called_once_with(
        "Calibration",
        "Étape 3 / 4\nSélectionnez maintenant le dernier compte.",
        "",
    )


def test_calibration_multiple_windows_completion_uses_expected_content(
    monkeypatch,
):
    notification = Mock()

    new_notification = Mock(
        return_value=notification,
    )

    monkeypatch.setattr(
        "notifications.dofus_notifications.Notify.Notification.new",
        new_notification,
    )

    manager = DofusNotificationManager()

    summary = "Compte 2, Compte 1, Compte 4 et Compte 3"

    manager.notify_calibration_multiple_windows(
        window_count=4,
        step=4,
        summary=summary,
    )

    new_notification.assert_called_once_with(
        "Calibration",
        "Étape 4 / 4\nCalibration terminée.\nCompte 2, Compte 1, Compte 4 et Compte 3",
        "",
    )


def test_new_window_uses_expected_content(
    monkeypatch,
):
    notification = Mock()

    new_notification = Mock(
        return_value=notification,
    )

    monkeypatch.setattr(
        "notifications.dofus_notifications.Notify.Notification.new",
        new_notification,
    )

    manager = DofusNotificationManager()

    manager.notify_new_window()

    new_notification.assert_called_once_with(
        "Nouveau compte détecté",
        "Une nouvelle fenêtre Dofus a été détectée.\n"
        "Relancez une calibration pour l'ajouter à la rotation.",
        "",
    )
