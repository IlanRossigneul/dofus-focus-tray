import asyncio
import threading

from dbus_next.aio import MessageBus
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication
from KStatusNotifierItem import KStatusNotifierItem

from bridge.bridge import (
    BUS_NAME,
    OBJECT_PATH,
    DofusFocusBridge,
)
from bridge.models import DofusFocusState
from config.paths import ICON_DIR
from ui.menu import MenuWidgets, create_menu
from ui.status_view import StatusView
from ui.tray_view import create_indicator


class ApplicationSignals(QObject):
    state_changed = Signal(object, int)


class Application:
    def __init__(self) -> None:
        self.indicator: KStatusNotifierItem | None = None
        self.status_view: StatusView | None = None
        self.menu_widgets: MenuWidgets | None = None

        self.bridge: DofusFocusBridge | None = None
        self.bus: MessageBus | None = None

        self.dbus_loop: asyncio.AbstractEventLoop | None = None
        self.dbus_stop_event: asyncio.Event | None = None
        self.dbus_thread: threading.Thread | None = None

        self.signals = ApplicationSignals()

        self.icon_dir = ICON_DIR

    def _create_status_view(
        self,
        widgets: MenuWidgets,
    ) -> StatusView:
        return StatusView(
            indicator=self.indicator,
            windows_item=widgets.windows_item,
            order_item=widgets.order_item,
            active_window_item=widgets.active_window_item,
        )

    def _handle_state_changed(
        self,
        state: DofusFocusState,
        window_count: int,
    ) -> None:
        if self.status_view is None:
            return

        self.status_view.update(
            state,
            window_count,
        )

    def _request_calibration(self) -> None:
        if (
            self.bridge is None
            or self.dbus_loop is None
        ):
            return

        self.dbus_loop.call_soon_threadsafe(
            self.bridge.start_calibration,
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
        self.dbus_loop = asyncio.get_running_loop()
        self.dbus_stop_event = asyncio.Event()

        self.bus = await MessageBus().connect()

        self.bridge = DofusFocusBridge(
            on_state_changed=self.signals.state_changed.emit,
        )

        self.bus.export(
            OBJECT_PATH,
            self.bridge,
        )

        await self.bus.request_name(BUS_NAME)

        print(
            "[DOFUS FOCUS BRIDGE] Started",
            flush=True,
        )

        await self.dbus_stop_event.wait()

        if self.bus is not None:
            self.bus.disconnect()
            self.bus = None

        self.bridge = None
        self.dbus_stop_event = None
        self.dbus_loop = None

        print(
            "[DOFUS FOCUS BRIDGE] Stopped",
            flush=True,
        )

    def _run_dbus_thread(self) -> None:
        try:
            asyncio.run(self._run_dbus())
        except Exception as error:
            print(
                "[DOFUS FOCUS BRIDGE] Thread error:",
                error,
                flush=True,
            )

    def _start_dbus(self) -> None:
        self.dbus_thread = threading.Thread(
            target=self._run_dbus_thread,
            name="DBusThread",
        )

        self.dbus_thread.start()

    def _stop(self) -> None:
        self._stop_dbus()

        if self.dbus_thread is not None:
            self.dbus_thread.join()

    def run(self) -> int:
        app = QApplication.instance()

        if app is None:
            app = QApplication([])

        app.setQuitOnLastWindowClosed(False)

        self.signals.state_changed.connect(
            self._handle_state_changed,
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

        self.indicator.setContextMenu(
            self.menu_widgets.menu,
        )

        self._start_dbus()

        exit_code = app.exec()

        self._stop()

        return exit_code
