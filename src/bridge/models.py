from dataclasses import dataclass, field


@dataclass
class DofusWindow:
    uuid: str
    position: int
    calibrated_order: int | None = None

    @property
    def name(self) -> str:
        return f"Compte {self.position + 1}"


@dataclass
class DofusFocusState:
    calibrated: bool = False
    calibrating: bool = False
    calibrated_windows: list[DofusWindow] = field(
        default_factory=list,
    )
    current_index: int = -1
    total_windows: int = 0
