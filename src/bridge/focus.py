from .calibration import CalibrationController
from .kwin import KWinController
from .windows import WindowsController


class FocusController:
    """Manage focus navigation between calibrated Dofus windows."""

    def __init__(
        self,
        windows: WindowsController,
        calibration: CalibrationController,
        kwin: KWinController,
    ):
        self._windows = windows
        self._calibration = calibration
        self._kwin = kwin
        self._current_index = -1

    def reset(self) -> None:
        """Reset the current focus position."""
        self._current_index = -1

    @property
    def current_index(self) -> int:
        return self._current_index

    def update_active_window(self, uuid: str) -> None:
        """Update the current calibrated order from the active Dofus window."""
        for window in self._calibration.calibrated_windows:
            if window.uuid == uuid:
                self._current_index = window.calibrated_order
                break

    async def focus(self, direction: int) -> None:
        """Focus the next or previous live Dofus window."""
        if not self._calibration.calibrated:
            return

        if direction not in (-1, 1):
            return

        live_windows = self._windows.windows

        if not live_windows:
            return

        calibrated_windows = self._calibration.calibrated_windows

        candidates = [
            window for window in calibrated_windows if window.uuid in live_windows
        ]

        if not candidates:
            return

        if direction == 1:
            next_candidates = [
                window
                for window in candidates
                if window.calibrated_order > self._current_index
            ]

            target = min(
                next_candidates,
                key=lambda window: window.calibrated_order,
                default=min(
                    candidates,
                    key=lambda window: window.calibrated_order,
                ),
            )

        else:
            previous_candidates = [
                window
                for window in candidates
                if window.calibrated_order < self._current_index
            ]

            target = max(
                previous_candidates,
                key=lambda window: window.calibrated_order,
                default=max(
                    candidates,
                    key=lambda window: window.calibrated_order,
                ),
            )

        self._current_index = target.calibrated_order

        await self._kwin.activate_window(target.uuid)
