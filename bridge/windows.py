from bridge.calibration import CalibrationController
from bridge.models import DofusFocusState


class WindowsController:
    """Manage the lifecycle of detected Dofus windows."""

    def __init__(
        self,
        state: DofusFocusState,
        calibration: CalibrationController,
    ):
        self.state = state
        self._calibration = calibration
        self._windows: list[str] = []

    @property
    def windows(self) -> list[str]:
        """Return the currently detected Dofus windows."""
        return self._windows

    def update(self, windows: list[str]) -> str | None:
        """Update live windows and handle disappeared windows."""
        old_windows = list(self._windows)
        self._windows = list(windows)

        missing_uuid = next(
            (
                uuid
                for uuid in old_windows
                if uuid not in self._windows
            ),
            None,
        )

        if missing_uuid is None:
            return None

        print(
            "[DOFUS FOCUS BRIDGE] Window vanished from desktop:",
            missing_uuid,
        )

        if self.state.calibrating:
            if self._calibration.handle_window_removal(missing_uuid):
                print(
                    "[DOFUS FOCUS BRIDGE] Calibration cancelled: "
                    "a Dofus window was closed"
                )

            return missing_uuid

        if not self.state.calibrated:
            return missing_uuid

        removed_index = next(
            (
                index
                for index, window
                in enumerate(self.state.calibrated_windows)
                if window.uuid == missing_uuid
            ),
            -1,
        )

        if removed_index == -1:
            return missing_uuid

        self.state.calibrated_windows.pop(removed_index)

        if not self.state.calibrated_windows:
            print(
                "[DOFUS FOCUS BRIDGE] "
                "All calibrated Dofus windows were closed"
            )

            self._reset_state()
            return missing_uuid

        if self.state.current_index > removed_index:
            self.state.current_index -= 1
        elif (
            self.state.current_index
            >= len(self.state.calibrated_windows)
        ):
            self.state.current_index = (
                len(self.state.calibrated_windows) - 1
            )

        print(
            "[DOFUS FOCUS BRIDGE] Calibrated windows after removal:",
            self.state.calibrated_windows,
        )

        print(
            "[DOFUS FOCUS BRIDGE] Current index:",
            self.state.current_index,
        )

        return missing_uuid

    def _reset_state(self) -> None:
        self.state.calibrated = False
        self.state.calibrating = False

        self.state.original_windows = []
        self.state.calibrated_windows = []

        self.state.current_index = -1
        self.state.total_windows = 0
