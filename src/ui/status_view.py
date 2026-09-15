from PySide6.QtGui import QAction

from bridge.models import DofusFocusState


class StatusView:
    """Update tray menu items from the current Dofus Focus state."""

    def __init__(
        self,
        windows_item: QAction,
        order_item: QAction,
        active_window_item: QAction,
    ):
        self.windows_item = windows_item
        self.order_item = order_item
        self.active_window_item = active_window_item

    def _format_window_order(
        self,
        state: DofusFocusState,
    ) -> str:
        """Format the calibrated window names as a human-readable list."""
        windows = [
            window.name
            for window in state.calibrated_windows
        ]

        if len(windows) <= 1:
            return "".join(windows)

        if len(windows) == 2:
            return " et ".join(windows)

        return ", ".join(windows[:-1]) + " et " + windows[-1]

    def update(
        self,
        state: DofusFocusState,
        window_count: int,
    ) -> None:
        """Update the tray status items from the current application state."""
        window_label = "Fenêtre" if window_count in (0, 1) else "Fenêtres"

        self.windows_item.setText(
            f"{window_label} : {window_count}"
        )

        if not state.calibrated:
            self.order_item.setVisible(False)
            self.active_window_item.setVisible(False)
            return

        self.order_item.setVisible(True)
        self.active_window_item.setVisible(True)

        self.order_item.setText(
            f"Ordre : {self._format_window_order(state)}"
        )

        if 0 <= state.current_index < len(
            state.calibrated_windows
        ):
            active_window = state.calibrated_windows[
                state.current_index
            ]

            self.active_window_item.setText(
                f"Dernière fenêtre active : {active_window.name}"
            )
        else:
            self.active_window_item.setText(
                "Dernière fenêtre active : —"
            )
