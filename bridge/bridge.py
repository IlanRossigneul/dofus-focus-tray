import json
from copy import deepcopy
from typing import Callable

from dbus_next.service import ServiceInterface, method, signal

from bridge.calibration import CalibrationController
from bridge.focus import FocusController
from bridge.kwin import KWinController
from bridge.models import DofusFocusState
from bridge.windows import WindowsController


BUS_NAME = "org.ilan.DofusFocusBridge"
OBJECT_PATH = "/org/ilan/DofusFocusBridge"
INTERFACE_NAME = "org.ilan.DofusFocusBridge"


class DofusFocusBridge(ServiceInterface):
    def __init__(
        self,
        on_state_changed: Callable[
            [DofusFocusState, int],
            None,
        ] | None = None,
    ):
        super().__init__(INTERFACE_NAME)

        self.state = DofusFocusState()
        self._on_state_changed = on_state_changed

        self._kwin = KWinController()
        self._calibration = CalibrationController(self.state)
        self._active_window_id = None
        self._windows_controller = WindowsController(
            self.state,
            self._calibration,
        )
        self._focus = FocusController(
            self.state,
            self._kwin,
        )

        print(
            "[DOFUS FOCUS BRIDGE] Bridge initialized",
            flush=True,
        )

    def _print_calibrated_mapping(self) -> None:
        if not self.state.calibrated_windows:
            print(
                "[DOFUS FOCUS BRIDGE] Calibrated mapping: none",
                flush=True,
            )
            return

        print(
            "[DOFUS FOCUS BRIDGE] Calibrated mapping:",
            flush=True,
        )

        for index, window in enumerate(
            self.state.calibrated_windows
        ):
            marker = " <- CURRENT"

            if index != self.state.current_index:
                marker = ""

            print(
                f"    {window.name} -> "
                f"{window.uuid}"
                f"{marker}",
                flush=True,
            )

    def _notify_state_changed(self) -> None:
        if self._on_state_changed is None:
            return

        print(
            "[DOFUS FOCUS BRIDGE] "
            "Notifying Qt of state change",
            flush=True,
        )

        self._on_state_changed(
            deepcopy(self.state),
            len(self._windows_controller.windows),
        )

    @method()
    def start_calibration(self) -> None:
        print(
            "[DOFUS FOCUS BRIDGE] "
            "Calibration requested",
            flush=True,
        )

        print(
            "[DOFUS FOCUS BRIDGE] "
            f"Active window before calibration: "
            f"{self._active_window_id}",
            flush=True,
        )

        self._calibration.start(
            self._active_window_id,
        )

        print(
            "[DOFUS FOCUS BRIDGE] "
            f"Calibration state: "
            f"calibrating={self.state.calibrating}, "
            f"calibrated={self.state.calibrated}",
            flush=True,
        )

        self._print_calibrated_mapping()
        self._notify_state_changed()

    @method()
    def update_windows(self, windows_json: "s") -> None:
        try:
            windows = json.loads(windows_json)

            print(
                "[DOFUS FOCUS BRIDGE] "
                f"Live windows count: {len(windows)}",
                flush=True,
            )

            for index, window_id in enumerate(windows):
                print(
                    f"    [{index}] {window_id}",
                    flush=True,
                )

            self._windows_controller.update(windows)

            print(
                "[DOFUS FOCUS BRIDGE] "
                "Live windows state updated",
                flush=True,
            )

            self._notify_state_changed()

        except Exception as error:
            print(
                "[DOFUS FOCUS BRIDGE] "
                "Error decoding JSON:",
                error,
                flush=True,
            )

    @method()
    def update_active_window(
        self,
        internal_id: "s",
    ) -> None:
        print(
            "[DOFUS FOCUS BRIDGE] "
            f"Active window update received: "
            f"'{internal_id}'",
            flush=True,
        )

        if not internal_id:
            print(
                "[DOFUS FOCUS BRIDGE] "
                "No Dofus window is currently active",
                flush=True,
            )

            self._active_window_id = None

            self._notify_state_changed()
            return

        previous_active_window_id = self._active_window_id

        self._active_window_id = internal_id

        print(
            "[DOFUS FOCUS BRIDGE] "
            f"Previous active window ID: "
            f"'{previous_active_window_id}'",
            flush=True,
        )

        print(
            "[DOFUS FOCUS BRIDGE] "
            f"Current active window ID: "
            f"'{self._active_window_id}'",
            flush=True,
        )

        print(
            "[DOFUS FOCUS BRIDGE] "
            f"Calibration state: "
            f"calibrating={self.state.calibrating}, "
            f"calibrated={self.state.calibrated}",
            flush=True,
        )

        self._print_calibrated_mapping()

        previous_index = self.state.current_index

        if self.state.calibrating:
            print(
                "[DOFUS FOCUS BRIDGE] "
                "Calibration is active; "
                "selecting active window",
                flush=True,
            )

            selected = self._calibration.select_window(
                internal_id,
            )

            print(
                "[DOFUS FOCUS BRIDGE] "
                f"Calibration selection result: {selected}",
                flush=True,
            )
        else:
            print(
                "[DOFUS FOCUS BRIDGE] "
                "Updating focused calibrated window",
                flush=True,
            )

            self._focus.update_active_window(
                internal_id,
            )

        print(
            "[DOFUS FOCUS BRIDGE] "
            f"Current index: "
            f"{previous_index} -> "
            f"{self.state.current_index}",
            flush=True,
        )

        self._print_calibrated_mapping()
        self._notify_state_changed()

    @method()
    async def activate_window(
        self,
        internal_id: "s",
    ) -> None:
        print(
            "[DOFUS FOCUS BRIDGE] "
            f"Activate window requested: '{internal_id}'",
            flush=True,
        )

        await self._kwin.activate_window(
            internal_id,
        )

        print(
            "[DOFUS FOCUS BRIDGE] "
            f"Activate window completed: '{internal_id}'",
            flush=True,
        )

    @method()
    def dofus_focus(
        self,
        direction: "i",
    ) -> None:
        print(
            "[DOFUS FOCUS BRIDGE] "
            f"Dofus focus requested, direction={direction}",
            flush=True,
        )

        previous_index = self.state.current_index

        self._focus.focus(direction)

        print(
            "[DOFUS FOCUS BRIDGE] "
            f"Current index: "
            f"{previous_index} -> "
            f"{self.state.current_index}",
            flush=True,
        )

        self._print_calibrated_mapping()
        self._notify_state_changed()

    @signal()
    def windows_updated(
        self,
        windows: "as",
    ) -> "as":
        return windows
