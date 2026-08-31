import asyncio
import logging
import os
import tempfile

from dbus_next import BusType
from dbus_next.aio import MessageBus

KWIN_BUS_NAME = "org.kde.KWin"
KWIN_SCRIPTING_PATH = "/Scripting"
KWIN_SCRIPTING_INTERFACE = "org.kde.kwin.Scripting"


logger = logging.getLogger(__name__)


class KWinController:
    """Control KWin through its scripting DBus interface."""

    def __init__(self) -> None:
        self._bus: MessageBus | None = None
        self._scripting = None
        self._lock = asyncio.Lock()

    async def _connect(self) -> None:
        if self._bus is not None:
            return

        self._bus = await MessageBus(
            bus_type=BusType.SESSION,
        ).connect()

        introspection = await self._bus.introspect(
            KWIN_BUS_NAME,
            KWIN_SCRIPTING_PATH,
        )

        proxy = self._bus.get_proxy_object(
            KWIN_BUS_NAME,
            KWIN_SCRIPTING_PATH,
            introspection,
        )

        self._scripting = proxy.get_interface(
            KWIN_SCRIPTING_INTERFACE,
        )

    async def activate_window(self, uuid: str) -> None:
        """Activate the KWin window identified by its UUID."""

        js_code = f"""
        var windows = workspace.windowList();

        for (var i = 0; i < windows.length; i++) {{
            if (String(windows[i].internalId) === "{uuid}") {{
                workspace.activeWindow = windows[i];
                break;
            }}
        }}
        """

        async with self._lock:
            await self._connect()

            temp_path = None
            script_id = None

            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    suffix=".js",
                    delete=False,
                ) as temp_file:
                    temp_file.write(js_code)
                    temp_path = temp_file.name

                script_id = await self._scripting.call_load_script(
                    temp_path,
                )

                await self._scripting.call_start()

            finally:
                if script_id is not None:
                    try:
                        await self._scripting.call_unload_script(
                            str(script_id),
                        )
                    except Exception:
                        logger.debug("Failed to unload KWin script", exc_info=True)

                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)

    async def close(self) -> None:
        """Close the DBus connection."""

        if self._bus is None:
            return

        self._bus.disconnect()

        self._bus = None
        self._scripting = None

    async def set_window_keep_above(
        self,
        pid: int,
        enabled: bool = True,
    ) -> None:
        """Set or clear the KeepAbove state for a window by PID."""
        js_code = f"""
        var windows = workspace.windowList();

        for (var i = 0; i < windows.length; i++) {{
            var window = windows[i];

            if (window.pid !== {pid}) {{
                continue;
            }}

            window.keepAbove = {str(enabled).lower()};
            break;
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

            await scripting.call_start()

            await asyncio.sleep(0.2)

            await scripting.call_unload_script(
                str(script_id),
            )

        except Exception:
            logger.exception("Failed to set window keepAbove")

        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

            if kwin_bus:
                kwin_bus.disconnect()
