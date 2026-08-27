import asyncio
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
    """Expose the Dofus focus bridge through DBus."""

    def __init__(
        self,
        on_state_changed: Callable[
            [DofusFocusState, int],
            None,
        ] | None = None,
        on_calibration_started: Callable[
            [int, int, str | None],
            None,
        ] | None = None,
        on_new_window: Callable[
            [],
            None,
        ] | None = None,
        on_calibration_already_selected: Callable[
            [],
            None,
        ] | None = None,
        on_calibration_cancelled: Callable[
            [],
            None,
        ] | None = None,
    ):
        super().__init__(INTERFACE_NAME)

        self._on_state_changed = on_state_changed
        self._on_calibration_started = on_calibration_started
        self._on_new_window = on_new_window
        self._on_calibration_already_selected = (
            on_calibration_already_selected
        )
        self._on_calibration_cancelled = on_calibration_cancelled

        self._windows = WindowsController()
        self._calibration = CalibrationController()
        self._kwin = KWinController()

        self._focus = FocusController(
            self._windows,
            self._calibration,
            self._kwin,
        )

        # Ignore the next active-window update after a calibration
        # cancellation caused by a calibrated window disappearing.
        self._ignore_next_active_window = False
        self._pending_already_selected_task: asyncio.Task[None] | None = None

    async def _notify_calibration_already_selected(
        self,
    ) -> None:
        """Notify after allowing pending window updates to be processed."""
        try:
            await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            return

        if (
            self._calibration.calibrating
            and self._on_calibration_already_selected is not None
        ):
            print(
                "[BRIDGE DEBUG] Already selected notification",
                flush=True,
            )

            self._on_calibration_already_selected()

            self._notify_state_changed()

        self._pending_already_selected_task = None

    def _build_state(self) -> DofusFocusState:
        """Build a snapshot of the current bridge state."""
        return DofusFocusState(
            calibrated=self._calibration.calibrated,
            calibrating=self._calibration.calibrating,
            calibrated_windows=deepcopy(
                self._calibration.calibrated_windows,
            ),
            current_index=self._focus.current_index,
            total_windows=self._calibration.total_windows,
        )

    def _notify_state_changed(self) -> None:
        if self._on_state_changed is None:
            return

        self._on_state_changed(
            self._build_state(),
            len(self._windows.windows),
        )

    def _get_calibration_summary(self) -> str | None:
        if not self._calibration.calibrated:
            return None

        windows = [
            window.name
            for window in self._calibration.calibrated_windows
        ]

        if len(windows) <= 1:
            return None

        if len(windows) == 2:
            return " et ".join(windows)

        return ", ".join(windows[:-1]) + " et " + windows[-1]

    def _handle_new_window(self) -> None:
        if not self._calibration.calibrated:
            return

        if self._on_new_window is not None:
            self._on_new_window()

    async def _focus_direction(self, direction: int) -> None:
        """Focus the next or previous calibrated Dofus window."""
        previous_index = self._focus.current_index

        await self._focus.focus(direction)

        if self._focus.current_index != previous_index:
            self._notify_state_changed()

    @method()
    def start_calibration(self) -> None:
        """Start calibration using the currently detected windows."""
        print(
            "[BRIDGE DEBUG] start_calibration",
            f"windows={self._windows.windows}",
            f"active_window={self._windows.active_window}",
            f"calibrated_before={self._calibration.calibrated}",
            f"calibrating_before={self._calibration.calibrating}",
            flush=True,
        )

        self._ignore_next_active_window = False

        self._focus.reset()

        self._calibration.start(
            self._windows.windows,
        )

        print(
            "[BRIDGE DEBUG] after calibration.start",
            f"calibrating={self._calibration.calibrating}",
            f"calibrated={self._calibration.calibrated}",
            f"calibrated_windows="
            f"{self._calibration.calibrated_windows}",
            f"total_windows={self._calibration.total_windows}",
            flush=True,
        )

        if (
            self._calibration.calibrating
            and self._windows.active_window
        ):
            print(
                "[BRIDGE DEBUG] start_calibration: "
                "trying automatic selection",
                f"active_window={self._windows.active_window}",
                flush=True,
            )

            selected = self._calibration.select_window(
                self._windows.active_window,
            )

            print(
                "[BRIDGE DEBUG] start_calibration: "
                "automatic selection result",
                f"selected={selected}",
                f"calibrating={self._calibration.calibrating}",
                f"calibrated={self._calibration.calibrated}",
                f"calibrated_windows="
                f"{self._calibration.calibrated_windows}",
                flush=True,
            )

        if self._on_calibration_started is not None:
            step = 0

            if self._calibration.calibrating:
                step = len(
                    self._calibration.calibrated_windows,
                )
            elif self._calibration.calibrated:
                step = len(
                    self._calibration.calibrated_windows,
                )

            self._on_calibration_started(
                len(self._windows.windows),
                step,
                self._get_calibration_summary(),
            )

        self._notify_state_changed()

    @method()
    def update_windows(self, windows_json: "s") -> None:
        """Update the list of live Dofus windows."""
        windows = json.loads(windows_json)

        previous_windows = set(
            self._windows.windows,
        )
        previous_calibrating = self._calibration.calibrating
        previous_calibrated = self._calibration.calibrated
        previous_calibrated_windows = deepcopy(
            self._calibration.calibrated_windows,
        )

        print(
            "[BRIDGE DEBUG] update_windows",
            f"windows={windows}",
            f"previous_windows={sorted(previous_windows)}",
            f"previous_calibrating={previous_calibrating}",
            f"previous_calibrated={previous_calibrated}",
            f"calibrated_windows_before="
            f"{previous_calibrated_windows}",
            flush=True,
        )

        self._windows.update_windows(windows)
        self._calibration.update_windows(windows)

        print(
            "[BRIDGE DEBUG] after calibration.update_windows",
            f"calibrating={self._calibration.calibrating}",
            f"calibrated={self._calibration.calibrated}",
            f"calibrated_windows="
            f"{self._calibration.calibrated_windows}",
            f"total_windows={self._calibration.total_windows}",
            f"active_window={self._windows.active_window}",
            flush=True,
        )

        current_windows = set(windows)

        removed_windows = previous_windows - current_windows

        calibrated_window_disappeared = bool(
            removed_windows
            & {
                window.uuid
                for window in previous_calibrated_windows
            }
        )

        print(
            "[BRIDGE DEBUG] window transition",
            f"removed_windows={sorted(removed_windows)}",
            f"calibrated_window_disappeared="
            f"{calibrated_window_disappeared}",
            flush=True,
        )

        if (
            self._calibration.calibrating
            and self._windows.active_window
        ):
            print(
                "[BRIDGE DEBUG] update_windows: "
                "trying automatic selection",
                f"active_window={self._windows.active_window}",
                flush=True,
            )

            selected = self._calibration.select_window(
                self._windows.active_window,
            )

            print(
                "[BRIDGE DEBUG] update_windows: "
                "automatic selection result",
                f"selected={selected}",
                f"calibrating={self._calibration.calibrating}",
                f"calibrated={self._calibration.calibrated}",
                f"calibrated_windows="
                f"{self._calibration.calibrated_windows}",
                flush=True,
            )

            if selected and self._on_calibration_started is not None:
                self._on_calibration_started(
                    len(self._windows.windows),
                    len(self._calibration.calibrated_windows),
                    self._get_calibration_summary(),
                )

        new_window_detected = bool(
            current_windows - previous_windows
        )

        if (
            new_window_detected
            and previous_calibrated
        ):
            print(
                "[BRIDGE DEBUG] New window detected after calibration",
                f"new_windows="
                f"{sorted(current_windows - previous_windows)}",
                flush=True,
            )

            self._handle_new_window()

        if (
            previous_calibrating
            and not self._calibration.calibrating
            and self._calibration.calibrated
        ):
            print(
                "[BRIDGE DEBUG] Calibration completed",
                f"calibrated_windows="
                f"{self._calibration.calibrated_windows}",
                flush=True,
            )

            if self._on_calibration_started is not None:
                self._on_calibration_started(
                    len(self._windows.windows),
                    len(
                        self._calibration.calibrated_windows,
                    ),
                    self._get_calibration_summary(),
                )

        elif (
            previous_calibrating
            and not self._calibration.calibrating
            and not self._calibration.calibrated
        ):
            if (
                calibrated_window_disappeared
                and self._pending_already_selected_task is not None
            ):
                self._pending_already_selected_task.cancel()
                self._pending_already_selected_task = None

                print(
                    "[BRIDGE DEBUG] Cancelled pending "
                    "already-selected notification",
                    flush=True,
                )

            print(
                "[BRIDGE DEBUG] Calibration cancelled",
                "reason=calibrated window disappeared",
                flush=True,
            )

            # The active-window update generated by KWin when focus
            # returns to another window must not be interpreted as a
            # calibration selection after this cancellation.
            if calibrated_window_disappeared:
                self._ignore_next_active_window = True

                print(
                    "[BRIDGE DEBUG] Calibration cancellation armed "
                    "active-window update suppression",
                    flush=True,
                )

            if self._on_calibration_cancelled is not None:
                self._on_calibration_cancelled()

        elif (
            previous_calibrated
            and self._calibration.calibrating
        ):
            print(
                "[BRIDGE DEBUG] Calibration restarted/started",
                f"calibrated_windows="
                f"{self._calibration.calibrated_windows}",
                flush=True,
            )

            if self._on_calibration_started is not None:
                self._on_calibration_started(
                    len(self._windows.windows),
                    len(
                        self._calibration.calibrated_windows,
                    ),
                    self._get_calibration_summary(),
                )

        print(
            "[BRIDGE DEBUG] update_windows complete",
            f"calibrating={self._calibration.calibrating}",
            f"calibrated={self._calibration.calibrated}",
            f"calibrated_windows="
            f"{self._calibration.calibrated_windows}",
            f"ignore_next_active_window="
            f"{self._ignore_next_active_window}",
            flush=True,
        )

        self._notify_state_changed()

    @method()
    def update_active_window(self, uuid: "s") -> None:
        """Update the currently active Dofus window."""
        print(
            "[BRIDGE DEBUG] update_active_window",
            f"uuid={uuid}",
            f"calibrating_before={self._calibration.calibrating}",
            f"calibrated_before={self._calibration.calibrated}",
            f"calibrated_windows="
            f"{self._calibration.calibrated_windows}",
            f"active_window_before={self._windows.active_window}",
            f"ignore_next_active_window="
            f"{self._ignore_next_active_window}",
            flush=True,
        )

        self._windows.update_active_window(uuid)

        print(
            "[BRIDGE DEBUG] after windows.update_active_window",
            f"uuid={uuid}",
            f"active_window={self._windows.active_window}",
            f"calibrating={self._calibration.calibrating}",
            f"calibrated={self._calibration.calibrated}",
            flush=True,
        )

        if self._ignore_next_active_window:
            print(
                "[BRIDGE DEBUG] Ignoring active-window update after "
                "calibration cancellation",
                f"uuid={uuid}",
                flush=True,
            )

            self._ignore_next_active_window = False

            print(
                "[BRIDGE DEBUG] Active-window update suppression consumed",
                flush=True,
            )

            self._notify_state_changed()
            return

        if self._calibration.calibrating:
            already_selected = any(
                window.uuid == uuid
                for window in self._calibration.calibrated_windows
            )

            print(
                "[BRIDGE DEBUG] calibration selection",
                f"uuid={uuid}",
                f"already_selected={already_selected}",
                f"calibrated_windows_before="
                f"{self._calibration.calibrated_windows}",
                flush=True,
            )

            selected = self._calibration.select_window(uuid)

            print(
                "[BRIDGE DEBUG] selection result",
                f"selected={selected}",
                f"calibrating={self._calibration.calibrating}",
                f"calibrated={self._calibration.calibrated}",
                f"calibrated_windows_after="
                f"{self._calibration.calibrated_windows}",
                flush=True,
            )

            if selected:
                if self._on_calibration_started is not None:
                    self._on_calibration_started(
                        len(self._windows.windows),
                        len(
                            self._calibration.calibrated_windows,
                        ),
                        self._get_calibration_summary(),
                    )

                if self._calibration.calibrated:
                    self._focus.update_active_window(uuid)

            elif (
                already_selected
                and self._on_calibration_already_selected is not None
            ):
                print(
                    "[BRIDGE DEBUG] Delaying already-selected notification",
                    f"uuid={uuid}",
                    flush=True,
                )

                if self._pending_already_selected_task is not None:
                    self._pending_already_selected_task.cancel()

                self._pending_already_selected_task = asyncio.create_task(
                    self._notify_calibration_already_selected(),
                )

            self._notify_state_changed()
            return

        print(
            "[BRIDGE DEBUG] update_active_window: "
            "not calibrating, updating focus",
            f"uuid={uuid}",
            flush=True,
        )

        self._focus.update_active_window(uuid)
        self._notify_state_changed()

    @method()
    def activate_window(self, uuid: "s") -> None:
        """Activate a Dofus window through KWin."""
        print(
            "[BRIDGE DEBUG] activate_window",
            f"uuid={uuid}",
            flush=True,
        )

        asyncio.create_task(
            self._kwin.activate_window(uuid),
        )

    @method()
    def dofus_focus(self, direction: "i") -> None:
        """Focus the next or previous calibrated Dofus window."""
        print(
            "[BRIDGE DEBUG] dofus_focus",
            f"direction={direction}",
            flush=True,
        )

        asyncio.create_task(
            self._focus_direction(direction),
        )

    @method()
    def focus(self, direction: "i") -> None:
        """Focus the next or previous calibrated Dofus window."""
        self.dofus_focus(direction)

    @signal()
    def windows_updated(
        self,
        windows: "as",
    ) -> "as":
        return windows

    async def close(self) -> None:
        """Close bridge resources."""
        print(
            "[BRIDGE DEBUG] close",
            flush=True,
        )

        await self._kwin.close()
