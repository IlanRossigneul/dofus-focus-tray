from bridge.models import DofusFocusState, DofusWindow


class CalibrationController:
    """Manage Dofus window calibration."""

    def __init__(self, state: DofusFocusState):
        self.state = state
        self._windows: list[str] = []

    def set_windows(self, windows: list[str]) -> None:
        """Update the currently detected Dofus windows."""
        self._windows = list(windows)

    def start(self, active_window_id: str | None = None) -> None:
        """Start a new calibration."""
        self._reset()

        window_count = len(self._windows)

        if window_count == 0:
            return

        self.state.original_windows = [
            DofusWindow(
                name=f"Compte {index + 1}",
                uuid=internal_id,
                position=index,
            )
            for index, internal_id in enumerate(self._windows)
        ]

        self.state.total_windows = window_count

        # A single Dofus window does not require ordering.
        if window_count == 1:
            self.state.calibrated_windows = [
                self.state.original_windows[0]
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

        original_window = next(
            (
                window
                for window in self.state.original_windows
                if window.uuid == internal_id
            ),
            None,
        )

        if original_window is None:
            return False

        calibrated_window = DofusWindow(
            name=original_window.name,
            uuid=original_window.uuid,
            position=original_window.position,
            calibrated_order=len(self.state.calibrated_windows),
        )

        self.state.calibrated_windows.append(calibrated_window)

        if len(self.state.calibrated_windows) == self.state.total_windows:
            self.state.calibrating = False
            self.state.calibrated = True
            self.state.current_index = len(self.state.calibrated_windows) - 1

        return True

    def handle_window_removal(self, internal_id: str) -> bool:
        """Cancel calibration if a calibrated source window disappears."""
        if not self.state.calibrating:
            return False

        if not any(
            window.uuid == internal_id
            for window in self.state.original_windows
        ):
            return False

        self._reset()
        return True

    def _reset(self) -> None:
        self.state.calibrated = False
        self.state.calibrating = False

        self.state.original_windows = []
        self.state.calibrated_windows = []

        self.state.current_index = -1
        self.state.total_windows = 0
