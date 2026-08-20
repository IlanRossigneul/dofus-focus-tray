import json

from dataclasses import asdict, dataclass
from pathlib import Path

from shortcuts.model import Shortcut


@dataclass
class ShortcutConfiguration:
    """Store the shortcuts assigned to a configuration."""

    primary: Shortcut | None = None
    alternate: Shortcut | None = None


class ShortcutStorage:
    """Load and save shortcut configurations."""

    def __init__(self, path: Path):
        self._path = path

    def load(self) -> dict[str, ShortcutConfiguration]:
        """Load shortcut configurations from the storage file."""

        if not self._path.exists():
            return {}

        with self._path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        return {
            name: ShortcutConfiguration(
                primary=self._deserialize_shortcut(
                    configuration.get("primary"),
                ),
                alternate=self._deserialize_shortcut(
                    configuration.get("alternate"),
                ),
            )
            for name, configuration in data.items()
        }

    def save(
        self,
        configurations: dict[str, ShortcutConfiguration],
    ) -> None:
        """Save shortcut configurations to the storage file."""

        self._path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        data = {
            name: {
                "primary": self._serialize_shortcut(
                    configuration.primary,
                ),
                "alternate": self._serialize_shortcut(
                    configuration.alternate,
                ),
            }
            for name, configuration in configurations.items()
        }

        with self._path.open("w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                indent=4,
                ensure_ascii=False,
            )
            file.write("\n")

    @staticmethod
    def _serialize_shortcut(
        shortcut: Shortcut | None,
    ) -> dict | None:
        """Convert a shortcut to a JSON-compatible dictionary."""

        if shortcut is None:
            return None

        return {
            "trigger": shortcut.trigger,
            "modifiers": sorted(shortcut.modifiers),
        }

    @staticmethod
    def _deserialize_shortcut(
        data: dict | None,
    ) -> Shortcut | None:
        """Convert a stored dictionary back to a shortcut."""

        if data is None:
            return None

        return Shortcut(
            trigger=data["trigger"],
            modifiers=frozenset(data.get("modifiers", [])),
        )
