from dataclasses import dataclass
from enum import StrEnum

import evdev

from shortcuts.model import Shortcut
from shortcuts.storage import ShortcutConfiguration

ALLOWED_MODIFIERS = frozenset(
    {
        "CTRL",
        "ALT",
        "ALTGR",
        "SHIFT",
        "META",
    },
)

FORBIDDEN_MOUSE_BUTTONS = frozenset(
    {
        evdev.ecodes.BTN_LEFT,
        evdev.ecodes.BTN_MIDDLE,
        evdev.ecodes.BTN_RIGHT,
    },
)


class ShortcutAction(StrEnum):
    """Identify an action that can be triggered by an input shortcut."""

    CALIBRATION = "calibration"
    NEXT = "next"
    PREVIOUS = "previous"


@dataclass(frozen=True)
class KeyboardCombination:
    """Represent an authorized keyboard combination."""

    trigger: str
    modifiers: frozenset[str]


@dataclass(frozen=True)
class KeyboardRule:
    """Map an authorized keyboard combination to an action."""

    combination: KeyboardCombination
    action: ShortcutAction


@dataclass(frozen=True)
class MouseRule:
    """Map an authorized mouse button to an action."""

    button: int
    action: ShortcutAction


@dataclass(frozen=True)
class InputPolicy:
    """Define the input combinations authorized by the helper."""

    keyboard_rules: frozenset[KeyboardRule] = frozenset()
    mouse_rules: frozenset[MouseRule] = frozenset()

    @classmethod
    def from_configuration(
        cls,
        configuration: dict[str, ShortcutConfiguration],
    ) -> "InputPolicy":
        """Build a policy from a validated shortcut configuration."""

        if set(configuration) != frozenset(ShortcutAction):
            raise ValueError("Invalid shortcut actions.")

        keyboard_rules: set[KeyboardRule] = set()
        mouse_rules: set[MouseRule] = set()

        for action, action_configuration in configuration.items():
            for shortcut in (
                action_configuration.primary,
                action_configuration.alternate,
            ):
                if shortcut is None:
                    continue

                cls._add_shortcut_rule(
                    keyboard_rules,
                    mouse_rules,
                    ShortcutAction(action),
                    shortcut,
                )

        return cls(
            keyboard_rules=frozenset(keyboard_rules),
            mouse_rules=frozenset(mouse_rules),
        )

    @staticmethod
    def _add_shortcut_rule(
        keyboard_rules: set[KeyboardRule],
        mouse_rules: set[MouseRule],
        action: ShortcutAction,
        shortcut: Shortcut,
    ) -> None:
        """Add one validated shortcut to the appropriate rule set."""

        if shortcut.trigger.startswith("BTN_"):
            if shortcut.modifiers:
                raise ValueError(
                    "Mouse shortcuts cannot have modifiers.",
                )

            if action == ShortcutAction.CALIBRATION:
                raise ValueError(
                    "Calibration shortcuts must use the keyboard.",
                )

            button = InputPolicy._mouse_button_code(
                shortcut.trigger,
            )

            for rule in mouse_rules:
                if rule.button == button and rule.action != action:
                    raise ValueError(
                        "Mouse button is assigned to multiple actions.",
                    )

            mouse_rules.add(
                MouseRule(
                    button=button,
                    action=action,
                ),
            )
            return

        if not shortcut.modifiers:
            raise ValueError(
                "Keyboard shortcuts require at least one modifier.",
            )

        if not shortcut.modifiers <= ALLOWED_MODIFIERS:
            raise ValueError("Invalid keyboard modifier.")

        combination = KeyboardCombination(
            trigger=shortcut.trigger,
            modifiers=frozenset(shortcut.modifiers),
        )

        for rule in keyboard_rules:
            if (
                rule.combination == combination
                and rule.action != action
            ):
                raise ValueError(
                    "Keyboard shortcut is assigned to multiple actions.",
                )

        keyboard_rules.add(
            KeyboardRule(
                combination=combination,
                action=action,
            ),
        )

    @staticmethod
    def _mouse_button_code(trigger: str) -> int:
        """Convert a mouse button name to its evdev code."""

        button = getattr(evdev.ecodes, trigger, None)

        if not isinstance(button, int):
            raise TypeError(
                f"Invalid mouse button: {trigger}.",
            )

        if button in FORBIDDEN_MOUSE_BUTTONS:
            raise ValueError(
                f"Mouse button is not allowed: {trigger}.",
            )

        return button

    def get_keyboard_action(
        self,
        trigger: str,
        modifiers: frozenset[str],
    ) -> ShortcutAction | None:
        """Return the action authorized for a keyboard combination."""

        combination = KeyboardCombination(
            trigger=trigger,
            modifiers=modifiers,
        )

        for rule in self.keyboard_rules:
            if rule.combination == combination:
                return rule.action

        return None

    def get_mouse_action(
        self,
        button: int,
    ) -> ShortcutAction | None:
        """Return the action authorized for a mouse button."""

        for rule in self.mouse_rules:
            if rule.button == button:
                return rule.action

        return None
