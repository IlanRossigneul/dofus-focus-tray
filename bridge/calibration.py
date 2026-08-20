from bridge.models import DofusFocusState, DofusWindow


class CalibrationController:
    """Manage Dofus window calibration."""

    def __init__(self, state: DofusFocusState):
        self.state = state
        self._windows: list[str] = []

    def set_windows(self, windows: list[str]) -> None:
        """Update the currently detected Dofus windows."""
        new_windows = list(windows)

        if not self.state.calibrating:
            self._windows = new_windows
            return

        removed_windows = set(self._windows) - set(new_windows)

        if any(
            window.uuid in removed_windows
            for window in self.state.calibrated_windows
        ):
            self._windows = new_windows
            self.reset()
            return

        self._windows = new_windows
        self.state.total_windows = len(new_windows)

        calibrated_ids = {
            window.uuid
            for window in self.state.calibrated_windows
        }

        if new_windows and calibrated_ids == set(new_windows):
            self.state.calibrating = False
            self.state.calibrated = True
            self.state.current_index = (
                len(self.state.calibrated_windows) - 1
            )

    def start(self, active_window_id: str | None = None) -> None:
        """Start a new calibration."""
        self.reset()

        window_count = len(self._windows)

        if window_count == 0:
            return

        self.state.total_windows = window_count

        # A single Dofus window does not require ordering.
        if window_count == 1:
            self.state.calibrated_windows = [
                DofusWindow(
                    name="Compte 1",
                    uuid=self._windows[0],
                    position=0,
                    calibrated_order=0,
                )
            ]
            self.state.current_index = 0
            self.state.calibrated = True
            return

        self.state.calibrating = True

        if active_window_id in self._windows:
            self.select_window(active_window_id)

    def select_window(self, internal_id: str) -> bool:
        """Register a Dofus window as the next calibrated window."""
        if not self.state.calibrating:
            return False

        if internal_id in (
            window.uuid
            for window in self.state.calibrated_windows
        ):
            return False

        position = self._windows.index(internal_id)

        calibrated_window = DofusWindow(
            name=f"Compte {position + 1}",
            uuid=internal_id,
            position=position,
            calibrated_order=len(self.state.calibrated_windows),
        )

        self.state.calibrated_windows.append(calibrated_window)

        if len(self.state.calibrated_windows) == self.state.total_windows:
            self.state.calibrating = False
            self.state.calibrated = True
            self.state.current_index = len(
                self.state.calibrated_windows
            ) - 1

        return True

    def reset(self) -> None:
        self.state.calibrated = False
        self.state.calibrating = False

        self.state.calibrated_windows = []

        self.state.current_index = -1
        self.state.total_windows = 0
