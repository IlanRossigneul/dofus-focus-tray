import argparse
import asyncio
import logging
import os
import threading

from dbus_next.aio import MessageBus
from KStatusNotifierItem import KStatusNotifierItem
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from bridge.bridge import (
    BUS_NAME,
    OBJECT_PATH,
    DofusFocusBridge,
)
from bridge.kwin import KWinController
from bridge.models import DofusFocusState
from config.paths import ICON_DIR, SHORTCUTS_FILE
from notifications.dofus_notifications import DofusNotificationManager
from shortcuts.keyboard import KeyboardLayout
from shortcuts.service import ShortcutService
from shortcuts.storage import ShortcutConfiguration, ShortcutStorage
from ui.menu import MenuWidgets, create_menu
from ui.shortcuts_window import ShortcutsWindow
from ui.status_view import StatusView
from ui.tray_view import create_indicator

from .logging import setup_logger

logger = logging.getLogger(__name__)


class ApplicationSignals(QObject):
    state_changed = Signal(object, int)
    calibration_started = Signal(int, int, object)
    calibration_already_selected = Signal()
    calibration_cancelled = Signal()
    new_window_detected = Signal()


class Application:
    def __init__(self) -> None:
        self.indicator: KStatusNotifierItem | None = None
        self.status_view: StatusView | None = None
        self.menu_widgets: MenuWidgets | None = None
        self.notification_manager: DofusNotificationManager | None = None
        self.shortcuts_window: ShortcutsWindow | None = None
        self.shortcut_service: ShortcutService | None = None
        self.shortcut_thread: threading.Thread | None = None

        self.bridge: DofusFocusBridge | None = None
        self.bus: MessageBus | None = None

        self.dbus_loop: asyncio.AbstractEventLoop | None = None
        self.dbus_stop_event: asyncio.Event | None = None
        self.dbus_thread: threading.Thread | None = None

        self.signals = ApplicationSignals()

        self.shortcut_stop_event = threading.Event()

        self.kwin_controller = KWinController()

        self.icon_dir = ICON_DIR

    def _parse_args(
        self,
        args: list[str],
    ) -> int:
        """Parse command-line arguments."""
        parser = argparse.ArgumentParser()

        group = parser.add_mutually_exclusive_group()

        group.add_argument(
            "--info",
            dest="log_level",
            action="store_const",
            const=logging.INFO,
        )

        group.add_argument(
            "--debug",
            dest="log_level",
            action="store_const",
            const=logging.DEBUG,
        )

        parsed = parser.parse_args(args)

        return (
            parsed.log_level
            if parsed.log_level is not None
            else logging.INFO
        )

    def _create_status_view(
        self,
        widgets: MenuWidgets,
    ) -> StatusView:
        return StatusView(
            windows_item=widgets.windows_item,
            order_item=widgets.order_item,
            active_window_item=widgets.active_window_item,
        )

    def _handle_state_changed(
        self,
        state: DofusFocusState,
        window_count: int,
    ) -> None:
        if self.shortcut_service is not None:
            self.shortcut_service.set_calibration_valid(
                state.calibrated,
            )

        if self.status_view is None:
            return

        self.status_view.update(
            state,
            window_count,
        )

        self.indicator.setStatus(
            KStatusNotifierItem.ItemStatus.Active
            if window_count > 0
            else KStatusNotifierItem.ItemStatus.Passive
        )

    def _handle_calibration_started(
        self,
        window_count: int,
        step: int = 0,
        summary: str | None = None,
    ) -> None:
        """Notify the user about the current calibration step."""
        if self.notification_manager is None:
            return

        if window_count == 0:
            self.notification_manager.notify_calibration_no_windows()

        elif window_count == 1:
            self.notification_manager.notify_calibration_one_window()

        else:
            self.notification_manager.notify_calibration_multiple_windows(
                window_count=window_count,
                step=step,
                summary=summary,
            )

    def _handle_calibration_already_selected(self) -> None:
        if self.notification_manager is None:
            return

        self.notification_manager.notify_calibration_already_selected()

    def _handle_calibration_cancelled(self) -> None:
        if self.notification_manager is None:
            return

        self.notification_manager.notify_calibration_cancelled()

    def _handle_new_window_detected(self) -> None:
        if self.notification_manager is None:
            return

        self.notification_manager.notify_new_window()

    def _handle_shortcut_action(
        self,
        action: str,
    ) -> None:
        """Dispatch a shortcut action to the D-Bus bridge."""
        if (
            self.bridge is None
            or self.dbus_loop is None
        ):
            return

        if action == "calibration":
            self.dbus_loop.call_soon_threadsafe(
                self.bridge.start_calibration,
            )

        elif action == "next":
            self.dbus_loop.call_soon_threadsafe(
                self.bridge.dofus_focus,
                1,
            )

        elif action == "previous":
            self.dbus_loop.call_soon_threadsafe(
                self.bridge.dofus_focus,
                -1,
            )

    def _run_shortcuts(self) -> None:
        """Run the shortcut service in its dedicated thread."""
        keyboard_layout = KeyboardLayout()

        try:
            asyncio.run(
                keyboard_layout.connect(),
            )

            configuration = ShortcutStorage(
                SHORTCUTS_FILE,
            ).load()

            self.shortcut_service = ShortcutService(
                keyboard_layout=keyboard_layout,
                configuration=configuration,
                on_action=self._handle_shortcut_action,
                stop_requested=self.shortcut_stop_event.is_set,
            )

            self.shortcut_service.run()

        finally:
            asyncio.run(
                keyboard_layout.close(),
            )

            self.shortcut_service = None

    def _start_shortcuts(self) -> None:
        self.shortcut_stop_event.clear()

        self.shortcut_thread = threading.Thread(
            target=self._run_shortcuts,
            name="ShortcutThread",
            daemon=True,
        )

        self.shortcut_thread.start()

    def _request_calibration(self) -> None:
        if (
            self.bridge is None
            or self.dbus_loop is None
        ):
            return

        self.dbus_loop.call_soon_threadsafe(
            self.bridge.start_calibration,
        )

    def _open_shortcuts_window(self) -> None:
        """Open the shortcut configuration window and pause shortcut handling."""
        if self.shortcut_service is not None:
            self.shortcut_service.set_enabled(False)
            self.shortcut_service.set_mouse_interception_enabled(False)

        if self.shortcuts_window is None:
            self.shortcuts_window = ShortcutsWindow()

            self.shortcuts_window.closed.connect(
                self._handle_shortcuts_window_closed,
            )

            self.shortcuts_window.configuration_saved.connect(
                self._handle_shortcuts_configuration_saved,
            )
        else:
            self.shortcuts_window.reload()

        self.shortcuts_window.show()
        self.shortcuts_window.raise_()
        self.shortcuts_window.activateWindow()

        if self.dbus_loop is not None:
            asyncio.run_coroutine_threadsafe(
                self.kwin_controller.set_window_keep_above(
                    os.getpid(),
                ),
                self.dbus_loop,
            )

    def _handle_shortcuts_window_closed(self) -> None:
        if self.shortcut_service is not None:
            self.shortcut_service.set_mouse_interception_enabled(True)
            self.shortcut_service.set_enabled(True)

    def _handle_shortcuts_configuration_saved(
        self,
        configuration: dict[str, ShortcutConfiguration],
    ) -> None:
        if self.shortcut_service is not None:
            self.shortcut_service.update_configuration(
                configuration,
            )

    def _stop_dbus(self) -> None:
        if (
            self.dbus_loop is None
            or self.dbus_stop_event is None
        ):
            return

        self.dbus_loop.call_soon_threadsafe(
            self.dbus_stop_event.set,
        )

    async def _run_dbus(self) -> None:
        """Run the D-Bus bridge event loop."""
        self.dbus_loop = asyncio.get_running_loop()
        self.dbus_stop_event = asyncio.Event()

        self.bus = await MessageBus().connect()

        self.bridge = DofusFocusBridge(
            on_state_changed=self.signals.state_changed.emit,
            on_calibration_started=self.signals.calibration_started.emit,
            on_calibration_already_selected=(
                self.signals.calibration_already_selected.emit
            ),
            on_new_window=self.signals.new_window_detected.emit,
            on_calibration_cancelled=(
                self.signals.calibration_cancelled.emit
            ),
        )

        self.bus.export(
            OBJECT_PATH,
            self.bridge,
        )

        await self.bus.request_name(BUS_NAME)

        logger.info("D-Bus bridge started")

        await self.dbus_stop_event.wait()

        if self.bus is not None:
            self.bus.disconnect()
            self.bus = None

        self.bridge = None
        self.dbus_stop_event = None
        self.dbus_loop = None

        logger.info("D-Bus bridge stopped")

    def _run_dbus_thread(self) -> None:
        try:
            asyncio.run(self._run_dbus())
        except Exception:
            logger.exception("D-Bus thread failed")

    def _start_dbus(self) -> None:
        self.dbus_thread = threading.Thread(
            target=self._run_dbus_thread,
            name="DBusThread",
        )

        self.dbus_thread.start()

    def _shutdown(self) -> None:
        self.shortcut_stop_event.set()

        self._stop_dbus()

        if self.shortcut_thread is not None:
            self.shortcut_thread.join()

        if self.dbus_thread is not None:
            self.dbus_thread.join()

    def run(self, args: list[str]) -> int:
        """Start the application and run the Qt event loop."""
        log_level = self._parse_args(args)
        setup_logger(log_level)

        app = QApplication.instance()

        if app is None:
            app = QApplication([])

        app.setQuitOnLastWindowClosed(False)

        self.signals.state_changed.connect(
            self._handle_state_changed,
        )

        self.signals.calibration_started.connect(
            self._handle_calibration_started,
        )

        self.signals.calibration_already_selected.connect(
            self._handle_calibration_already_selected,
        )

        self.signals.calibration_cancelled.connect(
            self._handle_calibration_cancelled,
        )

        self.signals.new_window_detected.connect(
            self._handle_new_window_detected,
        )

        self.indicator = create_indicator(
            self.icon_dir,
        )

        self.menu_widgets = create_menu(
            self.icon_dir,
        )

        self.status_view = self._create_status_view(
            self.menu_widgets,
        )

        self.menu_widgets.calibration_item.triggered.connect(
            self._request_calibration,
        )

        self.menu_widgets.shortcuts_item.triggered.connect(
            self._open_shortcuts_window,
        )

        self.indicator.setContextMenu(
            self.menu_widgets.menu,
        )

        self.notification_manager = DofusNotificationManager()

        self._start_dbus()
        self._start_shortcuts()

        exit_code = app.exec()

        self._shutdown()

        return exit_code
