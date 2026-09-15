from .models import DofusWindow


class CalibrationController:
    """Manage Dofus window calibration."""

    def __init__(self):
        self._calibrating = False
        self._calibrated_windows: list[DofusWindow] = []
        self._total_windows = 0
        self._windows: list[str] = []

    @property
    def calibrating(self) -> bool:
        return self._calibrating

    @property
    def calibrated(self) -> bool:
        return bool(self._calibrated_windows) and not self._calibrating

    @property
    def calibrated_windows(self) -> list[DofusWindow]:
        return list(self._calibrated_windows)

    @property
    def total_windows(self) -> int:
        return self._total_windows

    def update_windows(self, windows: list[str]) -> None:
        """Update live windows during and after calibration."""
        new_windows = list(windows)

        previous_uuids = {window.uuid for window in self._calibrated_windows}
        live_uuids = set(new_windows)

        calibrated_window_disappeared = bool(previous_uuids - live_uuids)

        self._windows = new_windows
        self._total_windows = len(new_windows)

        if self._calibrating and calibrated_window_disappeared:
            self.reset()
            return

        self._calibrated_windows = [
            window for window in self._calibrated_windows if window.uuid in live_uuids
        ]

        for window in self._calibrated_windows:
            window.position = new_windows.index(window.uuid)

        if self._calibrating and len(self._calibrated_windows) == self._total_windows:
            self._calibrating = False

    def start(self, windows: list[str]) -> None:
        """Start a new calibration."""
        self.reset()

        self._windows = list(windows)
        self._total_windows = len(self._windows)

        if not self._windows:
            return

        if len(self._windows) == 1:
            self._calibrated_windows = [
                DofusWindow(
                    uuid=self._windows[0],
                    position=0,
                    calibrated_order=0,
                )
            ]
            return

        self._calibrating = True

    def select_window(self, uuid: str) -> bool:
        """Register a Dofus window as the next calibrated window."""
        if not self._calibrating:
            return False

        if uuid not in self._windows:
            return False

        if any(window.uuid == uuid for window in self._calibrated_windows):
            return False

        position = self._windows.index(uuid)

        self._calibrated_windows.append(
            DofusWindow(
                uuid=uuid,
                position=position,
                calibrated_order=len(self._calibrated_windows),
            )
        )

        if len(self._calibrated_windows) == self._total_windows:
            self._calibrating = False

        return True

    def reset(self) -> None:
        """Reset the calibration."""
        self._calibrating = False
        self._calibrated_windows = []
        self._total_windows = 0
        self._windows = []
