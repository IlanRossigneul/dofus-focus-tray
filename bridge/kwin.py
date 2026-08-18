import asyncio
import os
import tempfile

from dbus_next import BusType
from dbus_next.aio import MessageBus


KWIN_BUS_NAME = "org.kde.KWin"
KWIN_SCRIPTING_PATH = "/Scripting"
KWIN_SCRIPTING_INTERFACE = "org.kde.kwin.Scripting"


class KWinController:
    """Control KWin window activation."""

    async def activate_window(self, internal_id: str) -> None:
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
