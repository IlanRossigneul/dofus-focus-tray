import asyncio

from dbus_next.aio import MessageBus

from bridge.bridge import (
    BUS_NAME,
    OBJECT_PATH,
    DofusFocusBridge,
)


class Application:
    async def _run(self) -> None:
        bus = await MessageBus().connect()

        bridge = DofusFocusBridge()

        bus.export(OBJECT_PATH, bridge)

        await bus.request_name(BUS_NAME)

        print("[DOFUS FOCUS BRIDGE] Started")

        await asyncio.get_running_loop().create_future()

    def run(self) -> int:
        asyncio.run(self._run())
        return 0
