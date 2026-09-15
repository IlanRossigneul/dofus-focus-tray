from dataclasses import dataclass


@dataclass(frozen=True)
class InputDeviceInfo:
    path: str
    name: str
    phys: str
    uniq: str
    vendor: int
    product: int
    bus: int
    capabilities: dict
