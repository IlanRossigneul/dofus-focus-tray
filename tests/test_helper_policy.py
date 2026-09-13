import evdev
import pytest

from helper.policy import (
    InputPolicy,
    KeyboardCombination,
    KeyboardRule,
    MouseRule,
    ShortcutAction,
)
from shortcuts.model import Shortcut
from shortcuts.storage import ShortcutConfiguration


def make_configuration(
    calibration: tuple[Shortcut | None, Shortcut | None] = (None, None),
    next_shortcuts: tuple[Shortcut | None, Shortcut | None] = (None, None),
    previous: tuple[Shortcut | None, Shortcut | None] = (None, None),
) -> dict[str, ShortcutConfiguration]:
    """Build a complete shortcut configuration for policy tests."""
    return {
        "calibration": ShortcutConfiguration(
            primary=calibration[0],
            alternate=calibration[1],
        ),
        "next": ShortcutConfiguration(
            primary=next_shortcuts[0],
            alternate=next_shortcuts[1],
        ),
        "previous": ShortcutConfiguration(
            primary=previous[0],
            alternate=previous[1],
        ),
    }


def test_from_configuration_builds_keyboard_rules() -> None:
    configuration = make_configuration(
        calibration=(
            Shortcut("F1", frozenset({"CTRL"})),
            None,
        ),
        next_shortcuts=(
            Shortcut("N", frozenset({"META"})),
            None,
        ),
        previous=(
            Shortcut("N", frozenset({"META", "SHIFT"})),
            None,
        ),
    )

    policy = InputPolicy.from_configuration(configuration)

    assert policy.keyboard_rules == frozenset(
        {
            KeyboardRule(
                KeyboardCombination(
                    trigger="F1",
                    modifiers=frozenset({"CTRL"}),
                ),
                ShortcutAction.CALIBRATION,
            ),
            KeyboardRule(
                KeyboardCombination(
                    trigger="N",
                    modifiers=frozenset({"META"}),
                ),
                ShortcutAction.NEXT,
            ),
            KeyboardRule(
                KeyboardCombination(
                    trigger="N",
                    modifiers=frozenset({"META", "SHIFT"}),
                ),
                ShortcutAction.PREVIOUS,
            ),
        },
    )


def test_from_configuration_builds_mouse_rules() -> None:
    configuration = make_configuration(
        next_shortcuts=(
            Shortcut("BTN_EXTRA"),
            None,
        ),
        previous=(
            Shortcut("BTN_SIDE"),
            None,
        ),
    )

    policy = InputPolicy.from_configuration(configuration)

    assert policy.mouse_rules == frozenset(
        {
            MouseRule(
                button=evdev.ecodes.BTN_EXTRA,
                action=ShortcutAction.NEXT,
            ),
            MouseRule(
                button=evdev.ecodes.BTN_SIDE,
                action=ShortcutAction.PREVIOUS,
            ),
        },
    )


def test_keyboard_shortcut_requires_modifier() -> None:
    configuration = make_configuration(
        calibration=(
            Shortcut("F1"),
            None,
        ),
    )

    with pytest.raises(ValueError, match="at least one modifier"):
        InputPolicy.from_configuration(configuration)


@pytest.mark.parametrize(
    "button",
    [
        "BTN_LEFT",
        "BTN_MIDDLE",
        "BTN_RIGHT",
    ],
)
def test_forbidden_mouse_buttons_are_rejected(button: str) -> None:
    configuration = make_configuration(
        next_shortcuts=(
            Shortcut(button),
            None,
        ),
    )

    with pytest.raises(ValueError, match="not allowed"):
        InputPolicy.from_configuration(configuration)


def test_unknown_mouse_button_is_rejected() -> None:
    configuration = make_configuration(
        next_shortcuts=(
            Shortcut("BTN_DOES_NOT_EXIST"),
            None,
        ),
    )

    with pytest.raises(TypeError, match="Invalid mouse button"):
        InputPolicy.from_configuration(configuration)


@pytest.mark.parametrize(
    "configuration",
    [
        {},
        {
            "calibration": ShortcutConfiguration(),
            "next": ShortcutConfiguration(),
        },
        {
            "calibration": ShortcutConfiguration(),
            "next": ShortcutConfiguration(),
            "previous": ShortcutConfiguration(),
            "other": ShortcutConfiguration(),
        },
    ],
)
def test_invalid_actions_are_rejected(
    configuration: dict[str, ShortcutConfiguration],
) -> None:
    with pytest.raises(ValueError, match="Invalid shortcut actions"):
        InputPolicy.from_configuration(configuration)


def test_get_keyboard_action() -> None:
    configuration = make_configuration(
        next_shortcuts=(
            Shortcut("N", frozenset({"META"})),
            None,
        ),
    )

    policy = InputPolicy.from_configuration(configuration)

    assert (
        policy.get_keyboard_action(
            "N",
            frozenset({"META"}),
        )
        == ShortcutAction.NEXT
    )

    assert (
        policy.get_keyboard_action(
            "N",
            frozenset({"CTRL"}),
        )
        is None
    )


def test_get_mouse_action() -> None:
    configuration = make_configuration(
        next_shortcuts=(
            Shortcut("BTN_EXTRA"),
            None,
        ),
    )

    policy = InputPolicy.from_configuration(configuration)

    assert (
        policy.get_mouse_action(evdev.ecodes.BTN_EXTRA)
        == ShortcutAction.NEXT
    )

    assert (
        policy.get_mouse_action(evdev.ecodes.BTN_SIDE)
        is None
    )


def test_mouse_shortcut_cannot_have_modifiers() -> None:
    configuration = make_configuration(
        next_shortcuts=(
            Shortcut("BTN_SIDE", frozenset({"CTRL"})),
            None,
        ),
    )

    with pytest.raises(
        ValueError,
        match="Mouse shortcuts cannot have modifiers",
    ):
        InputPolicy.from_configuration(configuration)


def test_keyboard_shortcut_cannot_be_assigned_to_multiple_actions() -> None:
    configuration = make_configuration(
        next_shortcuts=(
            Shortcut("N", frozenset({"META"})),
            None,
        ),
        previous=(
            Shortcut("N", frozenset({"META"})),
            None,
        ),
    )

    with pytest.raises(
        ValueError,
        match="assigned to multiple actions",
    ):
        InputPolicy.from_configuration(configuration)


def test_mouse_button_cannot_be_assigned_to_multiple_actions() -> None:
    configuration = make_configuration(
        next_shortcuts=(
            Shortcut("BTN_SIDE"),
            None,
        ),
        previous=(
            Shortcut("BTN_SIDE"),
            None,
        ),
    )

    with pytest.raises(
        ValueError,
        match="assigned to multiple actions",
    ):
        InputPolicy.from_configuration(configuration)


def test_policies_are_equal_for_identical_configuration() -> None:
    configuration = make_configuration(
        next_shortcuts=(
            Shortcut("N", frozenset({"META"})),
            None,
        ),
    )

    first_policy = InputPolicy.from_configuration(configuration)
    second_policy = InputPolicy.from_configuration(configuration)

    assert first_policy == second_policy


def test_policies_are_different_when_configuration_changes() -> None:
    first_configuration = make_configuration(
        next_shortcuts=(
            Shortcut("N", frozenset({"META"})),
            None,
        ),
    )
    second_configuration = make_configuration(
        next_shortcuts=(
            Shortcut("N", frozenset({"CTRL"})),
            None,
        ),
    )

    first_policy = InputPolicy.from_configuration(first_configuration)
    second_policy = InputPolicy.from_configuration(second_configuration)

    assert first_policy != second_policy
