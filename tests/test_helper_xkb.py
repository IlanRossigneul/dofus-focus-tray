import evdev

from helper.xkb import Xkb


def test_xkb_key_translation() -> None:
    xkb = Xkb()

    try:
        xkb.load_wayland_keymap()

        tests = {
            evdev.ecodes.KEY_C: "c",
            evdev.ecodes.KEY_N: "n",
            evdev.ecodes.KEY_SEMICOLON: "m",
        }

        for evdev_code, expected in tests.items():
            assert xkb.keycode_to_key(evdev_code) == expected
    finally:
        xkb.close()


def test_xkb_modifier_translation() -> None:
    xkb = Xkb()

    try:
        xkb.load_wayland_keymap()

        tests = {
            evdev.ecodes.KEY_LEFTCTRL: "Control_L",
            evdev.ecodes.KEY_LEFTSHIFT: "Shift_L",
            evdev.ecodes.KEY_LEFTMETA: "Super_L",
        }

        for evdev_code, expected in tests.items():
            assert xkb.keycode_to_key(evdev_code) == expected
    finally:
        xkb.close()


def test_xkb_modifier_state() -> None:
    xkb = Xkb()

    try:
        xkb.load_wayland_keymap()

        ctrl = evdev.ecodes.KEY_LEFTCTRL
        meta = evdev.ecodes.KEY_LEFTMETA
        shift = evdev.ecodes.KEY_LEFTSHIFT
        n = evdev.ecodes.KEY_N

        xkb.update_key(ctrl, 1)

        assert xkb.keycode_to_key(ctrl) == "Control_L"
        assert xkb.keycode_to_key(n) == "n"

        xkb.update_key(n, 1)
        xkb.update_key(n, 0)
        xkb.update_key(ctrl, 0)

        xkb.update_key(meta, 1)
        xkb.update_key(shift, 1)

        assert xkb.keycode_to_key(meta) == "Super_L"
        assert xkb.keycode_to_key(shift) == "Shift_L"
        assert xkb.keycode_to_key(n) == "N"

        xkb.update_key(shift, 0)
        xkb.update_key(meta, 0)
    finally:
        xkb.close()


def test_xkb_reset_clears_modifier_state() -> None:
    xkb = Xkb()

    try:
        xkb.load_wayland_keymap()

        meta = evdev.ecodes.KEY_LEFTMETA
        shift = evdev.ecodes.KEY_LEFTSHIFT
        n = evdev.ecodes.KEY_N

        xkb.update_key(meta, 1)
        xkb.update_key(shift, 1)

        assert xkb.keycode_to_key(n) == "N"

        xkb.reset()

        assert xkb.keycode_to_key(n) == "n"
    finally:
        xkb.close()
