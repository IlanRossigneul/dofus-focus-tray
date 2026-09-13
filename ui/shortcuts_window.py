import copy
import logging
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QKeyEvent, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from config.paths import ICON_DIR, SHORTCUTS_FILE
from shortcuts.model import Shortcut
from shortcuts.service import ShortcutService
from shortcuts.storage import ShortcutConfiguration, ShortcutStorage

logger = logging.getLogger(__name__)


class ShortcutButton(QPushButton):
    """Provide a native shortcut button with an optional error border."""

    def __init__(
        self,
        parent=None,
    ) -> None:
        super().__init__(parent)

        self._capture_error = False

    def set_capture_error(
        self,
        enabled: bool,
    ) -> None:
        """Enable or disable the capture error appearance."""
        self._capture_error = enabled

        palette = self.palette()

        if enabled:
            palette.setColor(
                QPalette.ColorRole.ButtonText,
                Qt.GlobalColor.red,
            )
        else:
            palette.setColor(
                QPalette.ColorRole.ButtonText,
                self.style().standardPalette().color(
                    QPalette.ColorRole.ButtonText,
                ),
            )

        self.setPalette(palette)
        self.update()

    def paintEvent(
        self,
        event,
    ) -> None:
        super().paintEvent(event)

        if not self._capture_error:
            return

        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing,
        )

        painter.setPen(
            QPen(
                Qt.GlobalColor.red,
                2,
            )
        )
        painter.setBrush(
            Qt.BrushStyle.NoBrush,
        )

        painter.drawRoundedRect(
            self.rect().adjusted(
                1,
                1,
                -2,
                -2,
            ),
            4,
            4,
        )


class ShortcutsWindow(QDialog):
    """Provide the shortcut configuration window."""

    shortcut_captured = Signal(object)
    capture_failed = Signal(object)
    capture_rejected = Signal(str)
    closed = Signal()
    configuration_saved = Signal(object)

    def __init__(
        self,
        shortcut_service: ShortcutService,
        parent=None,
        storage_path: Path = SHORTCUTS_FILE,
    ) -> None:
        super().__init__(parent)

        self._shortcut_service = shortcut_service

        self._storage = ShortcutStorage(
            storage_path,
        )

        self._configurations = self._load_configurations()

        self._capture_target: tuple[
            str,
            str,
        ] | None = None

        self._capture_active = False

        self._capture_original: Shortcut | None = None

        self._duplicate_timer = QTimer(self)
        self._duplicate_timer.setSingleShot(True)
        self._duplicate_timer.setInterval(2000)
        self._duplicate_timer.timeout.connect(
            self._cancel_capture,
        )

        self._buttons: dict[
            tuple[str, str],
            ShortcutButton,
        ] = {}

        self._build_ui()
        self._update_buttons()
        self._center_window()

        self.shortcut_captured.connect(
            self._handle_shortcut_captured,
        )

        self.capture_failed.connect(
            self._handle_capture_failed,
        )

        self.capture_rejected.connect(
            self._handle_capture_rejected,
        )

        self.setWindowIcon(
            QIcon(
                str(ICON_DIR / "dofus.webp"),
            )
        )

    def _load_configurations(
        self,
    ) -> dict[str, ShortcutConfiguration]:
        """Load stored configurations and ensure required actions exist."""
        configurations = self._storage.load()

        for name in (
            "calibration",
            "next",
            "previous",
        ):
            configurations.setdefault(
                name,
                ShortcutConfiguration(),
            )

        return copy.deepcopy(configurations)

    def _build_ui(self) -> None:
        """Build the shortcut configuration interface."""
        self.setWindowTitle(
            "Configuration des raccourcis",
        )

        self.setModal(False)

        main_layout = QVBoxLayout(self)

        main_layout.addWidget(
            self._create_configuration_group(
                "calibration",
                "Raccourcis pour Calibration",
            )
        )

        main_layout.addWidget(
            self._create_configuration_group(
                "next",
                "Raccourcis pour Suivant",
            )
        )

        main_layout.addWidget(
            self._create_configuration_group(
                "previous",
                "Raccourcis pour Précédent",
            )
        )

        buttons_layout = QHBoxLayout()

        buttons_layout.addStretch()

        save_button = QPushButton(
            "Sauvegarder",
        )

        save_button.clicked.connect(
            self._save,
        )

        self._save_button = save_button

        buttons_layout.addWidget(
            save_button,
        )

        quit_button = QPushButton(
            "Quitter",
        )

        quit_button.clicked.connect(
            self.close,
        )

        self._quit_button = quit_button

        buttons_layout.addWidget(
            quit_button,
        )

        buttons_layout.addStretch()

        main_layout.addSpacing(8)
        main_layout.addLayout(buttons_layout)

        self.setMinimumWidth(420)

    def _create_configuration_group(
        self,
        configuration_name: str,
        title: str,
    ) -> QGroupBox:
        group = QGroupBox(title)

        layout = QGridLayout(group)

        primary_label = QLabel("Principal")
        alternate_label = QLabel("Alternatif")

        layout.addWidget(
            primary_label,
            0,
            0,
        )

        layout.addWidget(
            alternate_label,
            1,
            0,
        )

        primary_button = self._create_shortcut_button(
            configuration_name,
            "primary",
        )

        alternate_button = self._create_shortcut_button(
            configuration_name,
            "alternate",
        )

        layout.addWidget(
            primary_button,
            0,
            1,
        )

        layout.addWidget(
            alternate_button,
            1,
            1,
        )

        return group

    def _create_shortcut_button(
        self,
        configuration_name: str,
        shortcut_type: str,
    ) -> ShortcutButton:
        """Create and register a shortcut configuration button."""
        button = ShortcutButton()

        button.setMinimumWidth(270)

        button.clicked.connect(
            lambda _=False: self._start_capture(
                configuration_name,
                shortcut_type,
            ),
        )

        self._buttons[
            (
                configuration_name,
                shortcut_type,
            )
        ] = button

        return button

    def _update_buttons(self) -> None:
        """Update shortcut buttons from the current configurations."""
        for (
            configuration_name,
            shortcut_type,
        ), button in self._buttons.items():
            configuration = self._configurations[
                configuration_name
            ]

            shortcut = getattr(
                configuration,
                shortcut_type,
            )

            button.set_capture_error(False)

            if shortcut is None:
                button.setText("—")
            else:
                button.setText(str(shortcut))

    def _start_capture(
        self,
        configuration_name: str,
        shortcut_type: str,
    ) -> None:
        """Start capturing a shortcut for the selected action."""
        if self._capture_active:
            return

        self._capture_target = (
            configuration_name,
            shortcut_type,
        )

        self._capture_original = getattr(
            self._configurations[configuration_name],
            shortcut_type,
        )

        self._capture_active = True

        self._save_button.setEnabled(False)
        self._quit_button.setEnabled(False)

        for button in self._buttons.values():
            button.setEnabled(False)

        target_button = self._buttons[
            (
                configuration_name,
                shortcut_type,
            )
        ]

        target_button.setEnabled(True)

        target_button.setText(
            "Appuyez sur une touche..."
        )

        if configuration_name == "calibration":
            allowed_mouse_buttons = set()
        else:
            allowed_mouse_buttons = None

        self._shortcut_service.start_capture(
            allowed_mouse_buttons=allowed_mouse_buttons,
            callback=self.shortcut_captured.emit,
            error_callback=self.capture_failed.emit,
            rejected_callback=self.capture_rejected.emit,
        )

    def _is_shortcut_duplicate(
        self,
        shortcut: Shortcut,
        target: tuple[str, str],
    ) -> bool:
        """Return whether a shortcut is already assigned elsewhere."""
        for (
            configuration_name,
            configuration,
        ) in self._configurations.items():
            for shortcut_type in (
                "primary",
                "alternate",
            ):
                if (
                    configuration_name,
                    shortcut_type,
                ) == target:
                    continue

                if getattr(
                    configuration,
                    shortcut_type,
                ) == shortcut:
                    return True

        return False

    def _show_capture_error(
        self,
        message: str,
    ) -> None:
        """Display a capture error on the current target button."""
        if self._capture_target is None:
            return

        button = self._buttons[
            self._capture_target
        ]

        button.setText(message)
        button.set_capture_error(True)

    def _finish_capture(self) -> None:
        """Stop capture and restore the normal window state."""
        if self._duplicate_timer.isActive():
            self._duplicate_timer.stop()

        self._shortcut_service.stop_capture()

        self._capture_target = None
        self._capture_original = None
        self._capture_active = False

        self._save_button.setEnabled(True)
        self._quit_button.setEnabled(True)

        for button in self._buttons.values():
            button.setEnabled(True)

        self._update_buttons()

    def _cancel_capture(self) -> None:
        """Cancel the current capture and restore the original shortcut."""
        if self._capture_target is None:
            return

        configuration_name, shortcut_type = (
            self._capture_target
        )

        configuration = self._configurations[
            configuration_name
        ]

        setattr(
            configuration,
            shortcut_type,
            self._capture_original,
        )

        self._finish_capture()

    def _clear_target_shortcut(self) -> None:
        """Clear the shortcut assigned to the current capture target."""
        if self._capture_target is None:
            return

        configuration_name, shortcut_type = (
            self._capture_target
        )

        configuration = self._configurations[
            configuration_name
        ]

        setattr(
            configuration,
            shortcut_type,
            None,
        )

        self._finish_capture()

    def _handle_shortcut_captured(
        self,
        shortcut: Shortcut,
    ) -> None:
        """Handle a captured shortcut, including cancellation and duplicates."""
        if self._capture_target is None:
            return

        if shortcut.trigger == "ESCAPE":
            self._cancel_capture()
            return

        if shortcut.trigger == "BACKSPACE":
            self._clear_target_shortcut()
            return

        if (
            not shortcut.trigger.startswith("BTN_")
            and not shortcut.modifiers
        ):
            self._show_capture_error(
                "Un modificateur est requis"
            )
            self._duplicate_timer.start()
            return

        if self._is_shortcut_duplicate(
            shortcut,
            self._capture_target,
        ):
            self._show_capture_error(
                "Raccourci déjà utilisé"
            )
            self._duplicate_timer.start()
            return

        configuration_name, shortcut_type = (
            self._capture_target
        )

        configuration = self._configurations[
            configuration_name
        ]

        setattr(
            configuration,
            shortcut_type,
            shortcut,
        )

        self._finish_capture()

    def _handle_capture_rejected(
        self,
        _trigger: str,
    ) -> None:
        """Display an error when a mouse button is rejected."""
        if self._capture_target is None:
            return

        self._show_capture_error(
            "Bouton souris non autorisé",
        )
        self._duplicate_timer.start()

    def _handle_capture_failed(
        self,
        error: Exception,
    ) -> None:
        """Handle an unexpected error raised during shortcut capture."""
        self._finish_capture()

        logger.error(
            "Shortcut capture failed: %s",
            error,
        )

    def _save(self) -> None:
        """Save the current shortcut configuration and close the window."""
        if self._capture_active:
            return

        self._storage.save(
            self._configurations,
        )

        self.configuration_saved.emit(
            self._configurations,
        )

        self.close()

    def _center_window(self) -> None:
        screen = self.screen()

        if screen is None:
            return

        available_geometry = (
            screen.availableGeometry()
        )

        window_geometry = self.frameGeometry()

        window_geometry.moveCenter(
            available_geometry.center(),
        )

        self.move(
            window_geometry.topLeft(),
        )

    def keyPressEvent(
        self,
        event: QKeyEvent,
    ) -> None:
        if (
            self._capture_active
            and event.key() == Qt.Key.Key_Escape
        ):
            event.accept()
            return

        super().keyPressEvent(event)

    def reload(self) -> None:
        """Reload shortcut configurations from storage."""

        if self._capture_active:
            self._shortcut_service.stop_capture()

        self._configurations = self._load_configurations()

        if self._duplicate_timer.isActive():
            self._duplicate_timer.stop()

        self._capture_target = None
        self._capture_original = None
        self._capture_active = False

        self._save_button.setEnabled(True)
        self._quit_button.setEnabled(True)

        for button in self._buttons.values():
            button.setEnabled(True)

        self._update_buttons()

    def closeEvent(self, event) -> None:
        """Handle window closing and prevent it during shortcut capture."""
        if self._capture_active:
            event.ignore()
            return

        event.accept()
        self.closed.emit()
