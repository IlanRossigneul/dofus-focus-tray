import asyncio

from bridge.kwin import KWinController
from bridge.models import DofusFocusState


class FocusController:
    def __init__(
        self,
        state: DofusFocusState,
        kwin: KWinController,
    ):
        self._state = state
        self._kwin = kwin

    def update_active_window(self, internal_id: str) -> None:
        for index, window in enumerate(self._state.calibrated_windows):
            if window.uuid == internal_id:
                self._state.current_index = index
                break

    def focus(self, direction: int) -> None:
        if not self._state.calibrated:
            return

        windows = self._state.calibrated_windows

        if not windows:
            return

        if direction not in (-1, 1):
            return

        current_index = self._state.current_index

        if current_index < 0 or current_index >= len(windows):
            return

        next_index = (
            current_index + direction
        ) % len(windows)

        self._state.current_index = next_index

        window = windows[next_index]

        print(
            "[DOFUS FOCUS BRIDGE] Focusing Dofus window:",
            window.uuid,
            "index:",
            next_index,
        )

        asyncio.create_task(
            self._kwin.activate_window(window.uuid)
        )
