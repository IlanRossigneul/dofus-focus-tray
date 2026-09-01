import asyncio
import json
import logging
from collections.abc import Callable
from copy import deepcopy

from dbus_next.service import ServiceInterface, method

from .calibration import CalibrationController
from .focus import FocusController
from .kwin import KWinController
from .models import DofusFocusState
from .windows import WindowsController

BUS_NAME = "org.ilan.DofusFocusBridge"
OBJECT_PATH = "/org/ilan/DofusFocusBridge"
INTERFACE_NAME = "org.ilan.DofusFocusBridge"


logger = logging.getLogger(__name__)


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
        logger.info(
            "Starting calibration: windows=%s",
            self._windows.windows,
        )

        self._ignore_next_active_window = False

        self._focus.reset()

        self._calibration.start(
            self._windows.windows,
        )

        if (
            self._calibration.calibrating
            and self._windows.active_window
        ):
            selected = self._calibration.select_window(
                self._windows.active_window,
            )

            logger.debug(
                "Automatic calibration selection result: selected=%s, "
                "calibrating=%s, calibrated=%s, calibrated_windows=%s",
                selected,
                self._calibration.calibrating,
                self._calibration.calibrated,
                self._calibration.calibrated_windows,
            )

        if self._calibration.calibrated:
            calibrated_windows = ",\n".join(
                str(window)
                for window in self._calibration.calibrated_windows
            )

            logger.info(
                "Calibration completed: calibrated_windows=[\n%s]",
                calibrated_windows,
            )

        if self._on_calibration_started is not None:
            step = 0

            if self._calibration.calibrating or self._calibration.calibrated:
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

        self._windows.update_windows(windows)
        self._calibration.update_windows(windows)

        current_windows = set(windows)

        removed_windows = previous_windows - current_windows

        calibrated_window_disappeared = bool(
            removed_windows
            & {
                window.uuid
                for window in previous_calibrated_windows
            }
        )

        if (
            self._calibration.calibrating
            and self._windows.active_window
        ):
            selected = self._calibration.select_window(
                self._windows.active_window,
            )

            logger.debug(
                "Automatic calibration selection result: selected=%s "
                "calibrating=%s calibrated=%s calibrated_windows=%s",
                selected,
                self._calibration.calibrating,
                self._calibration.calibrated,
                self._calibration.calibrated_windows,
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
            logger.info(
                "New window detected after calibration: new_windows=%s",
                sorted(current_windows - previous_windows),
            )

            self._handle_new_window()

        if (
            previous_calibrating
            and not self._calibration.calibrating
            and self._calibration.calibrated
        ):
            calibrated_windows = ",\n".join(
                str(window)
                for window in self._calibration.calibrated_windows
            )

            logger.info(
                "Calibration completed: calibrated_windows=[\n%s]",
                calibrated_windows,
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

                logger.debug(
                    "Cancelled pending already-selected notification",
                )

            logger.info(
                "Calibration cancelled: reason=calibrated window disappeared",
            )

            # The active-window update generated by KWin when focus
            # returns to another window must not be interpreted as a
            # calibration selection after this cancellation.
            if calibrated_window_disappeared:
                self._ignore_next_active_window = True

                logger.debug(
                    "Calibration cancellation armed active-window update suppression",
                )

            if self._on_calibration_cancelled is not None:
                self._on_calibration_cancelled()

        elif (
            previous_calibrated
            and self._calibration.calibrating
        ):
            if self._on_calibration_started is not None:
                self._on_calibration_started(
                    len(self._windows.windows),
                    len(
                        self._calibration.calibrated_windows,
                    ),
                    self._get_calibration_summary(),
                )

        self._notify_state_changed()

    @method()
    def update_active_window(self, uuid: "s") -> None:
        """Update the currently active Dofus window."""
        self._windows.update_active_window(uuid)

        if self._ignore_next_active_window:
            logger.debug(
                "Ignoring active-window update after calibration cancellation: "
                "uuid=%s",
                uuid,
            )

            self._ignore_next_active_window = False

            self._notify_state_changed()
            return

        if self._calibration.calibrating:
            already_selected = any(
                window.uuid == uuid
                for window in self._calibration.calibrated_windows
            )

            logger.debug(
                "Calibration window selection: uuid=%s already_selected=%s",
                uuid,
                already_selected,
            )

            selected = self._calibration.select_window(uuid)

            logger.debug(
                "Calibration selection result: selected=%s calibrating=%s calibrated=%s",
                selected,
                self._calibration.calibrating,
                self._calibration.calibrated,
            )

            if selected:
                if self._calibration.calibrated:
                    calibrated_windows = ",\n".join(
                        str(window)
                        for window in self._calibration.calibrated_windows
                    )

                    logger.info(
                        "Calibration completed: calibrated_windows=[\n%s]",
                        calibrated_windows,
                    )

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
                logger.debug(
                    "Already-selected notification: uuid=%s",
                    uuid,
                )

                if self._pending_already_selected_task is not None:
                    self._pending_already_selected_task.cancel()

                self._pending_already_selected_task = asyncio.create_task(
                    self._notify_calibration_already_selected(),
                )

            self._notify_state_changed()
            return

        self._focus.update_active_window(uuid)
        self._notify_state_changed()

    @method()
    def activate_window(self, uuid: "s") -> None:
        """Activate a Dofus window through KWin."""
        logger.debug(
            "Activating window: uuid=%s",
            uuid,
        )

        asyncio.create_task(
            self._kwin.activate_window(uuid),
        )

    @method()
    def dofus_focus(self, direction: "i") -> None:
        """Focus the next or previous calibrated Dofus window."""
        logger.debug(
            "Dofus focus: direction=%s",
            direction,
        )

        asyncio.create_task(
            self._focus_direction(direction),
        )

    @method()
    def focus(self, direction: "i") -> None:
        """Focus the next or previous calibrated Dofus window."""
        self.dofus_focus(direction)

    async def close(self) -> None:
        """Close bridge resources."""
        logger.debug("Closing bridge")

        await self._kwin.close()
