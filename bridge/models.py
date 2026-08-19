from dataclasses import dataclass, field


@dataclass
class DofusWindow:
    name: str
    uuid: str
    position: int
    calibrated_order: int | None = None


@dataclass
class DofusFocusState:
    # Calibration state
    calibrated: bool = False
    calibrating: bool = False

    # Window event monitoring
    monitoring: bool = True

    # Windows registered by the calibration
    calibrated_windows: list[DofusWindow] = field(
        default_factory=list
    )

    # Currently focused calibrated Dofus window
    current_index: int = -1

    # Number of Dofus windows expected during calibration
    total_windows: int = 0
