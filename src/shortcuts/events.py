from dataclasses import dataclass


@dataclass(frozen=True)
class ShortcutEvent:
    """Normalized evdev input event."""

    event_type: int
    event_code: int
    value: int
    timestamp: float
    modifiers: frozenset[str] = frozenset()
