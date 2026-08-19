import json

from dbus_next.service import ServiceInterface, method, signal

from bridge.calibration import CalibrationController
from bridge.focus import FocusController
from bridge.kwin import KWinController
from bridge.models import DofusFocusState
from bridge.windows import WindowsController


BUS_NAME = "org.ilan.DofusFocusBridge"
OBJECT_PATH = "/org/ilan/DofusFocusBridge"
INTERFACE_NAME = "org.ilan.DofusFocusBridge"


class DofusFocusBridge(ServiceInterface):
    def __init__(self):
        super().__init__(INTERFACE_NAME)

        self.state = DofusFocusState()
        self._kwin = KWinController()
        self._calibration = CalibrationController(self.state)
        self._active_window_id = None
        self._windows_controller = WindowsController(
            self.state,
            self._calibration,
        )
        self._focus = FocusController(
            self.state,
            self._kwin,
        )

    @method()
    def start_calibration(self) -> None:
        self._calibration.start(self._active_window_id)

    @method()
    def update_windows(self, windows_json: "s") -> None:
        try:
            windows = json.loads(windows_json)

            print("[DOFUS FOCUS BRIDGE] Live windows count:", len(windows))

            self._windows_controller.update(windows)

        except Exception as error:
            print("[DOFUS FOCUS BRIDGE] Error decoding JSON:", error)

    @method()
    def update_active_window(self, internal_id: "s") -> None:
        if not internal_id:
            return

        self._active_window_id = internal_id

        if self.state.calibrating:
            self._calibration.select_window(internal_id)
            return

        self._focus.update_active_window(internal_id)

    @method()
    async def activate_window(self, internal_id: "s") -> None:
        await self._kwin.activate_window(internal_id)

    @method()
    def dofus_focus(self, direction: "i") -> None:
        self._focus.focus(direction)

    @signal()
    def windows_updated(self, windows: "as") -> "as":
        return windows
