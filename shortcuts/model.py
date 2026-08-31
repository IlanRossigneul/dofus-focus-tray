from dataclasses import dataclass


@dataclass(frozen=True)
class Shortcut:
    """Represent an input shortcut."""

    trigger: str
    modifiers: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        """Normalize the trigger and modifiers to uppercase."""
        trigger = self.trigger.upper()
        modifiers = frozenset(modifier.upper() for modifier in self.modifiers)

        if trigger in modifiers:
            raise ValueError("The trigger cannot also be a modifier.")

        object.__setattr__(self, "trigger", trigger)
        object.__setattr__(self, "modifiers", modifiers)

    def __str__(self) -> str:
        parts = [
            *sorted(self.modifiers, key=self._modifier_order),
            self.trigger,
        ]

        return " + ".join(parts)

    @staticmethod
    def _modifier_order(modifier: str) -> int:
        order = {
            "CTRL": 0,
            "ALT": 1,
            "SHIFT": 2,
            "META": 3,
        }

        return order.get(modifier, 99)
