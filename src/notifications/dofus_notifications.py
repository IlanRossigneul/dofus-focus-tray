import gi

gi.require_version("Notify", "0.7")

from gi.repository import GLib, Notify


class DofusNotificationManager:
    """Manage Dofus Focus desktop notifications."""

    def __init__(self) -> None:
        Notify.init("Dofus Focus Tray")

    def notify_calibration_no_windows(self) -> None:
        """Notify the user that no Dofus window was detected."""

        self._notify(
            "Calibration",
            "0 compte détecté\n"
            "Veuillez relancer la calibration avec vos comptes ouverts.",
        )

    def notify_calibration_one_window(self) -> None:
        """Notify the user that calibration is complete with one Dofus window."""

        self._notify(
            "Calibration",
            "1 Compte détecté\n"
            "Calibration terminée.",
        )

    def notify_calibration_multiple_windows(
        self,
        window_count: int,
        step: int = 0,
        summary: str | None = None,
    ) -> None:
        """Notify the user about the current multi-window calibration step."""

        if step == 0:
            message = (
                f"{window_count} comptes détectés\n"
                "Sélectionnez-les dans l'ordre souhaité."
            )

        elif step == window_count - 1:
            message = (
                f"Étape {step} / {window_count}\n"
                "Sélectionnez maintenant le dernier compte."
            )

        elif step == window_count:
            message = (
                f"Étape {step} / {window_count}\n"
                "Calibration terminée."
            )

            if summary:
                message += f"\n{summary}"

        else:
            message = (
                f"Étape {step} / {window_count}\n"
                "Sélectionnez maintenant le compte suivant."
            )

        self._notify(
            "Calibration",
            message,
        )

    def notify_new_window(self) -> None:
        """Notify the user that a new Dofus window was detected."""

        self._notify(
            "Nouveau compte détecté",
            "Une nouvelle fenêtre Dofus a été détectée.\n"
            "Relancez une calibration pour l'ajouter à la rotation.",
        )

    def notify_calibration_already_selected(self) -> None:
        """Notify the user that the active Dofus window was already selected."""

        self._notify(
            "Calibration",
            "Ce compte a déjà été sélectionné.",
        )

    def notify_calibration_cancelled(self) -> None:
        """Notify the user that calibration was cancelled."""

        self._notify(
            "Calibration",
            "Calibration annulée\n"
            "Un compte calibré a été fermé.",
        )

    def _notify(
        self,
        title: str,
        message: str,
        summary: str | None = None,
    ) -> None:
        """Show a desktop notification."""

        notification = Notify.Notification.new(
            title,
            message,
            summary or "",
        )

        notification.set_timeout(10000)

        notification.set_hint(
            "desktop-entry",
            GLib.Variant("s", "dofus-focus-tray"),
        )

        notification.show()
