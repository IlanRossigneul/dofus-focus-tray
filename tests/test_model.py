import pytest

from shortcuts.model import Shortcut


def test_shortcut_normalizes_trigger_and_modifiers():
    shortcut = Shortcut("d", {"alt", "ctrl"})

    assert shortcut.trigger == "D"
    assert shortcut.modifiers == {"ALT", "CTRL"}


def test_shortcut_string_orders_modifiers():
    shortcut = Shortcut("d", {"shift", "meta", "ctrl", "alt"})

    assert str(shortcut) == "CTRL + ALT + SHIFT + META + D"


def test_shortcut_accepts_mouse_trigger():
    shortcut = Shortcut("btn_side")

    assert shortcut.trigger == "BTN_SIDE"
    assert str(shortcut) == "BTN_SIDE"


def test_shortcut_rejects_trigger_used_as_modifier():
    with pytest.raises(ValueError):
        Shortcut("ctrl", {"ctrl"})


def test_shortcut_string_orders_altgr_modifier():
    shortcut = Shortcut(
        "d",
        {"shift", "meta", "ctrl", "alt", "altgr"},
    )

    assert str(shortcut) == (
        "CTRL + ALT + ALTGR + SHIFT + META + D"
    )
