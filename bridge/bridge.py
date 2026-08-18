#!/usr/bin/env python3

import asyncio
import json

from dbus_next.service import ServiceInterface, method, signal

from bridge.calibration import CalibrationController
from bridge.kwin import KWinController
from bridge.models import DofusFocusState
from bridge.windows import WindowsController


BUS_NAME = "org.ilan.DofusFocusBridge"
OBJECT_PATH = "/org/ilan/DofusFocusBridge"
INTERFACE_NAME = "org.ilan.DofusFocusBridge"

KWIN_BUS_NAME = "org.kde.KWin"
KWIN_SCRIPTING_PATH = "/Scripting"
KWIN_SCRIPTING_INTERFACE = "org.kde.kwin.Scripting"


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

    @method()
    def start_calibration(self) -> None:
        self._calibration.set_windows(self._windows_controller.windows)
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

        calibrated_windows = self.state.calibrated_windows

        # --------------------------------------------------------
        # CALIBRATION
        # --------------------------------------------------------

        if self.state.calibrating:
            self._calibration.select_window(internal_id)
            return

        # --------------------------------------------------------
        # NORMAL OPERATION
        # --------------------------------------------------------

        if not self.state.calibrated:
            return

        for index, window in enumerate(calibrated_windows):
            if window.uuid == internal_id:
                self.state.current_index = index

                print(
                    "[DOFUS FOCUS BRIDGE] Active Dofus window:",
                    internal_id,
                    "index:",
                    self.state.current_index,
                )

                return

    @method()
    async def activate_window(self, internal_id: "s") -> None:
        await self._kwin.activate_window(internal_id)

    @method()
    def dofus_focus(self, direction: "i") -> None:
        if not self.state.calibrated:
            return

        calibrated_windows = self.state.calibrated_windows

        if not calibrated_windows:
            return

        if direction not in (-1, 1):
            return

        current_index = self.state.current_index

        if current_index < 0 or current_index >= len(calibrated_windows):
            return

        target_index = (
            current_index + direction
        ) % len(calibrated_windows)

        target_window = calibrated_windows[target_index]

        self.state.current_index = target_index

        print(
            "[DOFUS FOCUS BRIDGE] Focusing Dofus window:",
            target_window.uuid,
            "index:",
            target_index,
        )

        # Schedule the activation asynchronously.
        asyncio.create_task(self._kwin.activate_window(target_window.uuid))

    @signal()
    def windows_updated(self, windows: "as") -> "as":
        return windows


async def main():
    bus = await MessageBus().connect()

    bridge = DofusFocusBridge()

    bus.export(OBJECT_PATH, bridge)

    await bus.request_name(BUS_NAME)

    print("[DOFUS FOCUS BRIDGE] Started")

    await asyncio.get_running_loop().create_future()


if __name__ == "__main__":
    asyncio.run(main())
