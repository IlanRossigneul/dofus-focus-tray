import asyncio
import copy
import threading
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from config.paths import SHORTCUTS_FILE
from shortcuts.keyboard import KeyboardLayout
from shortcuts.listener import ShortcutListener
from shortcuts.model import Shortcut
from shortcuts.storage import ShortcutConfiguration, ShortcutStorage


class ShortcutCaptureWorker:
    """Capture one shortcut in a background thread."""

    def __init__(
        self,
        callback,
        error_callback,
    ) -> None:
        self._callback = callback
        self._error_callback = error_callback

    def start(self) -> None:
        thread = threading.Thread(
            target=self._run,
            name="ShortcutCaptureThread",
            daemon=True,
        )

        thread.start()

    def _run(self) -> None:
        keyboard_layout = KeyboardLayout()

        try:
            asyncio.run(
                keyboard_layout.connect(),
            )

            shortcut = ShortcutListener(
                keyboard_layout,
            ).capture()

            self._callback(shortcut)

        except Exception as error:
            self._error_callback(error)

        finally:
            asyncio.run(
                keyboard_layout.close(),
            )


class ShortcutsWindow(QDialog):
    """Provide the shortcut configuration window."""

    shortcut_captured = Signal(object)
    capture_failed = Signal(object)

    def __init__(
        self,
        parent=None,
        storage_path: Path = SHORTCUTS_FILE,
    ) -> None:
        super().__init__(parent)

        self._storage = ShortcutStorage(
            storage_path,
        )

        self._configurations = self._load_configurations()

        self._capture_target: tuple[
            str,
            str,
        ] | None = None

        self._capture_active = False

        self._buttons: dict[
            tuple[str, str],
            QPushButton,
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

    def _load_configurations(
        self,
    ) -> dict[str, ShortcutConfiguration]:
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

        primary_label = QLabel("Primary")
        alternate_label = QLabel("Alternate")

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
    ) -> QPushButton:
        button = QPushButton()

        button.setMinimumWidth(220)

        button.clicked.connect(
            lambda checked=False: self._start_capture(
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

            if shortcut is None:
                button.setText("—")
            else:
                button.setText(str(shortcut))

    def _start_capture(
        self,
        configuration_name: str,
        shortcut_type: str,
    ) -> None:
        if self._capture_active:
            return

        self._capture_target = (
            configuration_name,
            shortcut_type,
        )

        self._capture_active = True

        self._save_button.setEnabled(False)
        self._quit_button.setEnabled(False)

        for button in self._buttons.values():
            button.setEnabled(False)

        self._buttons[
            (
                configuration_name,
                shortcut_type,
            )
        ].setText(
            "Appuyez sur une touche..."
        )

        worker = ShortcutCaptureWorker(
            callback=self.shortcut_captured.emit,
            error_callback=self.capture_failed.emit,
        )

        worker.start()

    def _handle_shortcut_captured(
        self,
        shortcut: Shortcut,
    ) -> None:
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
            shortcut,
        )

        self._capture_target = None
        self._capture_active = False

        self._save_button.setEnabled(True)
        self._quit_button.setEnabled(True)

        for button in self._buttons.values():
            button.setEnabled(True)

        self._update_buttons()

    def _handle_capture_failed(
        self,
        error: Exception,
    ) -> None:
        self._capture_target = None
        self._capture_active = False

        self._save_button.setEnabled(True)
        self._quit_button.setEnabled(True)

        for button in self._buttons.values():
            button.setEnabled(True)

        self._update_buttons()

        print(
            "[SHORTCUTS WINDOW] Shortcut capture failed:",
            error,
            flush=True,
        )

    def _save(self) -> None:
        if self._capture_active:
            return

        self._storage.save(
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

    def reload(self) -> None:
        """Reload shortcut configurations from storage."""

        self._configurations = self._load_configurations()

        self._capture_target = None
        self._capture_active = False

        self._save_button.setEnabled(True)
        self._quit_button.setEnabled(True)

        for button in self._buttons.values():
            button.setEnabled(True)

        self._update_buttons()

    def closeEvent(self, event) -> None:
        if self._capture_active:
            event.ignore()
            return

        event.accept()
