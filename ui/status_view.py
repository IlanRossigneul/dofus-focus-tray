from PySide6.QtGui import QAction
from KStatusNotifierItem import KStatusNotifierItem

from bridge.models import DofusFocusState


class StatusView:
    def __init__(
        self,
        indicator: KStatusNotifierItem,
        windows_item: QAction,
        order_item: QAction,
        active_window_item: QAction,
    ):
        self.indicator = indicator

        self.windows_item = windows_item
        self.order_item = order_item
        self.active_window_item = active_window_item

    def update(
        self,
        state: DofusFocusState,
        window_count: int,
    ) -> None:
        self.windows_item.setText(
            f"Fenêtres : {window_count}"
        )

        if not state.calibrated:
            self.order_item.setVisible(False)
            self.active_window_item.setVisible(False)
            return

        self.order_item.setVisible(True)
        self.active_window_item.setVisible(True)

        order = ", ".join(
            window.name
            for window in state.calibrated_windows
        )

        self.order_item.setText(
            f"Ordre : {order}"
        )

        if 0 <= state.current_index < len(
            state.calibrated_windows
        ):
            active_window = state.calibrated_windows[
                state.current_index
            ]

            self.active_window_item.setText(
                f"Fenêtre active : {active_window.name}"
            )
        else:
            self.active_window_item.setText(
                "Fenêtre active : —"
            )
