#!/usr/bin/env python3

import asyncio
import json
import os
import tempfile

from dbus_next import BusType
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method, signal


BUS_NAME = "org.ilan.DofusFocusBridge"
OBJECT_PATH = "/org/ilan/DofusFocusBridge"
INTERFACE_NAME = "org.ilan.DofusFocusBridge"

KWIN_BUS_NAME = "org.kde.KWin"
KWIN_SCRIPTING_PATH = "/Scripting"
KWIN_SCRIPTING_INTERFACE = "org.kde.kwin.Scripting"


class DofusFocusBridge(ServiceInterface):
    def __init__(self):
        super().__init__(INTERFACE_NAME)

    @method()
    def update_windows(self, windows_json: "s") -> None:
        try:
            windows = json.loads(windows_json)

            print(
                "[DOFUS FOCUS BRIDGE] Received Dofus windows:",
                len(windows),
            )

            for window in windows:
                print(
                    "[DOFUS FOCUS BRIDGE]",
                    window,
                )
        except Exception as error:
            print(
                "[DOFUS FOCUS BRIDGE] Error decoding JSON:",
                error,
            )

    @method()
    def update_active_window(self, internal_id: "s") -> None:
        print(
            "[DOFUS FOCUS BRIDGE] Active Dofus window:",
            internal_id,
        )

    @method()
    async def activate_window(self, internal_id: "s") -> None:
        js_code = f"""
var windows = workspace.windowList();

for (var i = 0; i < windows.length; i++) {{
    if (String(windows[i].internalId) === "{internal_id}") {{
        console.log("[KWIN SCRIPT] Activating Dofus window:", "{internal_id}");
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

            print(
                "[DOFUS FOCUS BRIDGE] Activating Dofus window:",
                internal_id,
            )

            kwin_bus = await MessageBus(
                bus_type=BusType.SESSION,
            ).connect()

            scripting_introspection = await kwin_bus.introspect(
                KWIN_BUS_NAME,
                KWIN_SCRIPTING_PATH,
            )

            scripting_object = kwin_bus.get_proxy_object(
                KWIN_BUS_NAME,
                KWIN_SCRIPTING_PATH,
                scripting_introspection,
            )

            scripting = scripting_object.get_interface(
                KWIN_SCRIPTING_INTERFACE,
            )

            script_id = await scripting.call_load_script(
                temp_path,
            )

            print(
                "[DOFUS FOCUS BRIDGE] KWin script loaded:",
                script_id,
            )

            await scripting.call_start()

            print(
                "[DOFUS FOCUS BRIDGE] KWin activation script started"
            )

            await asyncio.sleep(0.5)

            await scripting.call_unload_script(
                str(script_id),
            )

            print(
                "[DOFUS FOCUS BRIDGE] KWin activation script unloaded"
            )

        except Exception as error:
            print(
                "[DOFUS FOCUS BRIDGE] Failed to activate Dofus window:",
                error,
            )

        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

            if kwin_bus:
                kwin_bus.disconnect()

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
