import evdev

from helper.keyboard import KeyboardState


def make_key_event(code: int, value: int) -> evdev.InputEvent:
    return evdev.InputEvent(
        0,
        0,
        evdev.ecodes.EV_KEY,
        code,
        value,
    )


def test_initial_state_is_empty():
    state = KeyboardState()

    assert state.get_modifiers() == frozenset()
    assert not state.is_pressed(evdev.ecodes.KEY_N)


def test_modifier_press_is_tracked():
    state = KeyboardState()

    state.update(
        make_key_event(
            evdev.ecodes.KEY_LEFTMETA,
            1,
        ),
    )

    assert state.is_pressed(evdev.ecodes.KEY_LEFTMETA)
    assert state.get_modifiers() == frozenset({"META"})


def test_non_modifier_key_is_tracked():
    state = KeyboardState()

    state.update(
        make_key_event(
            evdev.ecodes.KEY_N,
            1,
        ),
    )

    assert state.is_pressed(evdev.ecodes.KEY_N)
    assert state.get_modifiers() == frozenset()


def test_modifier_and_trigger_are_tracked_together():
    state = KeyboardState()

    state.update(
        make_key_event(
            evdev.ecodes.KEY_LEFTMETA,
            1,
        ),
    )
    state.update(
        make_key_event(
            evdev.ecodes.KEY_N,
            1,
        ),
    )

    assert state.is_pressed(evdev.ecodes.KEY_LEFTMETA)
    assert state.is_pressed(evdev.ecodes.KEY_N)
    assert state.get_modifiers() == frozenset({"META"})


def test_key_release_removes_key():
    state = KeyboardState()

    state.update(
        make_key_event(
            evdev.ecodes.KEY_N,
            1,
        ),
    )
    state.update(
        make_key_event(
            evdev.ecodes.KEY_N,
            0,
        ),
    )

    assert not state.is_pressed(evdev.ecodes.KEY_N)


def test_modifier_release_removes_modifier():
    state = KeyboardState()

    state.update(
        make_key_event(
            evdev.ecodes.KEY_LEFTMETA,
            1,
        ),
    )
    state.update(
        make_key_event(
            evdev.ecodes.KEY_LEFTMETA,
            0,
        ),
    )

    assert state.get_modifiers() == frozenset()


def test_key_repeat_does_not_change_state():
    state = KeyboardState()

    state.update(
        make_key_event(
            evdev.ecodes.KEY_N,
            1,
        ),
    )
    state.update(
        make_key_event(
            evdev.ecodes.KEY_N,
            2,
        ),
    )

    assert state.is_pressed(evdev.ecodes.KEY_N)


def test_non_key_event_is_ignored():
    state = KeyboardState()

    state.update(
        evdev.InputEvent(
            0,
            0,
            evdev.ecodes.EV_REL,
            evdev.ecodes.REL_X,
            10,
        ),
    )

    assert state.get_modifiers() == frozenset()


def test_reset_clears_pressed_keys():
    state = KeyboardState()

    state.update(
        make_key_event(
            evdev.ecodes.KEY_LEFTMETA,
            1,
        ),
    )
    state.update(
        make_key_event(
            evdev.ecodes.KEY_N,
            1,
        ),
    )

    state.reset()

    assert not state.is_pressed(evdev.ecodes.KEY_LEFTMETA)
    assert not state.is_pressed(evdev.ecodes.KEY_N)
    assert state.get_modifiers() == frozenset()


def test_left_and_right_modifier_keys_share_modifier_name():
    state = KeyboardState()

    state.update(
        make_key_event(
            evdev.ecodes.KEY_LEFTCTRL,
            1,
        ),
    )
    state.update(
        make_key_event(
            evdev.ecodes.KEY_RIGHTSHIFT,
            1,
        ),
    )

    assert state.get_modifiers() == frozenset({"CTRL", "SHIFT"})


def test_get_pressed_keys_returns_current_keys():
    state = KeyboardState()

    state.update(
        make_key_event(
            evdev.ecodes.KEY_LEFTMETA,
            1,
        ),
    )
    state.update(
        make_key_event(
            evdev.ecodes.KEY_N,
            1,
        ),
    )

    assert state.get_pressed_keys() == frozenset(
        {
            evdev.ecodes.KEY_LEFTMETA,
            evdev.ecodes.KEY_N,
        },
    )
