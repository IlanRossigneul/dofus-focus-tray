#!/usr/bin/env python3

import asyncio
import json
import os
import tempfile

from dbus_next import BusType
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method, signal

from bridge.models import DofusFocusState, DofusWindow

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
        self._windows = []

    def create_original_windows(self, windows: list[str]) -> None:
        self.state.original_windows = [
            DofusWindow(
                name=f"Compte {index + 1}",
                uuid=internal_id,
                position=index,
            )
            for index, internal_id in enumerate(windows)
        ]

        self.state.total_windows = len(
            self.state.original_windows
        )

    def _start_calibration(self) -> None:
        self.state.calibrated = False
        self.state.calibrating = False

        self.state.original_windows = []
        self.state.calibrated_windows = []

        self.state.current_index = -1
        self.state.total_windows = 0

        if not self._windows:
            print(
                "[DOFUS FOCUS BRIDGE] Calibration cancelled: no Dofus windows found"
            )
            return

        self.state.calibrating = True

        self.create_original_windows(self._windows)

        print(
            "[DOFUS FOCUS BRIDGE] Calibration started:",
            self.state.total_windows,
            "Dofus windows",
        )

        for window in self.state.original_windows:
            print("[DOFUS FOCUS BRIDGE]", window)

    def _reset_state(self) -> None:
        self.state.calibrated = False
        self.state.calibrating = False

        self.state.original_windows = []
        self.state.calibrated_windows = []

        self.state.current_index = -1
        self.state.total_windows = 0

    @method()
    def start_calibration(self) -> None:
        self._start_calibration()

    @method()
    def update_windows(self, windows_json: "s") -> None:
        try:
            windows = json.loads(windows_json)

            old_live_windows = list(self._windows)
            self._windows = windows

            print("[DOFUS FOCUS BRIDGE] Live windows count:", len(windows))

            # --------------------------------------------------------
            # CALIBRATION IN PROGRESS
            # --------------------------------------------------------

            if self.state.calibrating:
                for window in self.state.original_windows:
                    if window.uuid not in self._windows:
                        self._reset_state()

                        print(
                            "[DOFUS FOCUS BRIDGE] Calibration cancelled: "
                            "a Dofus window was closed"
                        )

                        return

                return

            # --------------------------------------------------------
            # CALIBRATION COMPLETED
            # --------------------------------------------------------

            if not self.state.calibrated:
                return

            # Find the window that disappeared since the previous update.
            missing_uuid = None

            for uuid in old_live_windows:
                if uuid not in self._windows:
                    missing_uuid = uuid
                    break

            if missing_uuid is None:
                return

            print(
                "[DOFUS FOCUS BRIDGE] Window vanished from desktop:",
                missing_uuid,
            )

            # Remove the vanished window from the calibrated list.
            removed_index = -1

            for index, window in enumerate(self.state.calibrated_windows):
                if window.uuid == missing_uuid:
                    removed_index = index
                    break

            if removed_index == -1:
                return

            self.state.calibrated_windows.pop(removed_index)

            # No calibrated Dofus windows remain.
            if not self.state.calibrated_windows:
                print(
                    "[DOFUS FOCUS BRIDGE] All calibrated Dofus windows were closed"
                )

                self._reset_state()
                return

            # Keep current_index pointing to the same focused window
            # when the removed window was before it in the list.
            if self.state.current_index > removed_index:
                self.state.current_index -= 1

            # If the current index is now outside the list, clamp it
            # to the last remaining window.
            elif self.state.current_index >= len(self.state.calibrated_windows):
                self.state.current_index = (len(self.state.calibrated_windows) - 1)

            print(
                "[DOFUS FOCUS BRIDGE] Calibrated windows after removal:",
                self.state.calibrated_windows,
            )

            print("[DOFUS FOCUS BRIDGE] Current index:", self.state.current_index)

        except Exception as error:
            print("[DOFUS FOCUS BRIDGE] Error decoding JSON:", error)

    @method()
    def update_active_window(self, internal_id: "s") -> None:
        if not internal_id:
            return

        calibrated_windows = self.state.calibrated_windows

        # --------------------------------------------------------
        # CALIBRATION
        # --------------------------------------------------------

        if self.state.calibrating:
            for window in calibrated_windows:
                if window.uuid == internal_id:
                    return

            original_window = None

            for window in self.state.original_windows:
                if window.uuid == internal_id:
                    original_window = window
                    break

            if original_window is None:
                return

            calibrated_window = DofusWindow(
                name=original_window.name,
                uuid=original_window.uuid,
                position=original_window.position,
                calibrated_order=len(calibrated_windows),
            )

            calibrated_windows.append(calibrated_window)

            print(
                "[DOFUS FOCUS BRIDGE] Calibration selection:",
                calibrated_window,
            )

            if len(calibrated_windows) == self.state.total_windows:
                self.state.calibrating = False
                self.state.calibrated = True
                self.state.current_index = len(calibrated_windows) - 1

                print("[DOFUS FOCUS BRIDGE] Calibration completed")

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

    async def _activate_window(self, internal_id: str) -> None:
        js_code = f"""
        var windows = workspace.windowList();

        for (var i = 0; i < windows.length; i++) {{
            if (String(windows[i].internalId) === "{internal_id}") {{
                console.log(
                    "[KWIN SCRIPT] Activating Dofus window:",
                    "{internal_id}"
                );

                workspace.activeWindow = windows[i];
                break;
            }}
        }}
        """

        temp_path = None
        kwin_bus = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".js",
                delete=False,
            ) as temp_file:
                temp_file.write(js_code)
                temp_path = temp_file.name

            kwin_bus = await MessageBus(bus_type=BusType.SESSION).connect()

            scripting_introspection = await kwin_bus.introspect(
                KWIN_BUS_NAME,
                KWIN_SCRIPTING_PATH,
            )

            scripting_object = kwin_bus.get_proxy_object(
                KWIN_BUS_NAME,
                KWIN_SCRIPTING_PATH,
                scripting_introspection,
            )

            scripting = scripting_object.get_interface(KWIN_SCRIPTING_INTERFACE)

            script_id = await scripting.call_load_script(temp_path)

            await scripting.call_start()

            await asyncio.sleep(0.5)

            await scripting.call_unload_script(str(script_id))

        except Exception as error:
            print(
                "[DOFUS FOCUS BRIDGE] Failed to activate "
                "Dofus window:",
                error,
            )

        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

            if kwin_bus:
                kwin_bus.disconnect()

    @method()
    async def activate_window(self, internal_id: "s") -> None:
        await self._activate_window(internal_id)

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
        asyncio.create_task(
            self._activate_window(target_window.uuid)
        )

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
