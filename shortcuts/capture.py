import evdev

from .keyboard import KeyboardLayout
from .model import Shortcut

MODIFIER_KEYS = {
    evdev.ecodes.KEY_LEFTCTRL: "CTRL",
    evdev.ecodes.KEY_RIGHTCTRL: "CTRL",
    evdev.ecodes.KEY_LEFTALT: "ALT",
    evdev.ecodes.KEY_RIGHTALT: "ALT",
    evdev.ecodes.KEY_LEFTSHIFT: "SHIFT",
    evdev.ecodes.KEY_RIGHTSHIFT: "SHIFT",
    evdev.ecodes.KEY_LEFTMETA: "META",
    evdev.ecodes.KEY_RIGHTMETA: "META",
}


MOUSE_TRIGGERS = {
    evdev.ecodes.BTN_SIDE: "BTN_SIDE",
    evdev.ecodes.BTN_EXTRA: "BTN_EXTRA",
}


IGNORED_MOUSE_BUTTONS = {
    evdev.ecodes.BTN_LEFT,
    evdev.ecodes.BTN_RIGHT,
    evdev.ecodes.BTN_MIDDLE,
}


class ShortcutCaptureRejected(Exception):
    """Raised when an input event is rejected during shortcut capture."""

    def __init__(
        self,
        trigger: str,
    ) -> None:
        super().__init__(trigger)
        self.trigger = trigger


def get_modifier(event) -> str | None:
    """Return the modifier represented by an event."""

    if event.event_type != evdev.ecodes.EV_KEY:
        return None

    return MODIFIER_KEYS.get(event.event_code)


def get_rejected_mouse_button(
    event,
    allowed_mouse_buttons: set[int],
) -> str | None:
    """Return the mouse button rejected during shortcut capture."""

    if event.event_type != evdev.ecodes.EV_KEY:
        return None

    if event.value != 1:
        return None

    mouse_buttons = {
        evdev.ecodes.BTN_LEFT: "BTN_LEFT",
        evdev.ecodes.BTN_MIDDLE: "BTN_MIDDLE",
        evdev.ecodes.BTN_RIGHT: "BTN_RIGHT",
        evdev.ecodes.BTN_SIDE: "BTN_SIDE",
        evdev.ecodes.BTN_EXTRA: "BTN_EXTRA",
    }

    if event.event_code not in mouse_buttons:
        return None

    if event.event_code in allowed_mouse_buttons:
        return None

    return mouse_buttons[event.event_code]


def get_trigger(
    event,
    keyboard_layout: KeyboardLayout,
) -> str | None:
    """Return the supported trigger represented by an event."""

    if event.event_type != evdev.ecodes.EV_KEY:
        return None

    if event.event_code in IGNORED_MOUSE_BUTTONS:
        return None

    mouse_trigger = MOUSE_TRIGGERS.get(event.event_code)

    if mouse_trigger is not None:
        return mouse_trigger

    if event.event_code in MODIFIER_KEYS:
        return None

    return keyboard_layout.keycode_to_key(
        event.event_code,
    )


class ShortcutCapture:
    """Capture one keyboard or supported mouse-button shortcut."""

    def __init__(
        self,
        keyboard_layout: KeyboardLayout,
        allowed_mouse_buttons: set[int] | None = None,
    ):
        self._keyboard_layout = keyboard_layout
        self._allowed_mouse_buttons = (
            allowed_mouse_buttons
            if allowed_mouse_buttons is not None
            else set(MOUSE_TRIGGERS)
        )
        self._pressed_modifiers = set()
        self._completed = False

    @property
    def completed(self) -> bool:
        """Return whether a valid shortcut has been captured."""

        return self._completed

    def process_event(self, event) -> Shortcut | None:
        """Process one event and return the first valid shortcut."""

        if self._completed:
            return None

        if event.event_type != evdev.ecodes.EV_KEY:
            return None

        # Ignore key-repeat events.
        if event.value == 2:
            return None

        rejected_mouse_button = get_rejected_mouse_button(
            event,
            self._allowed_mouse_buttons,
        )

        if rejected_mouse_button is not None:
            raise ShortcutCaptureRejected(
                rejected_mouse_button,
            )

        modifier = get_modifier(event)

        if modifier is not None:
            if event.value == 1:
                self._pressed_modifiers.add(modifier)
            elif event.value == 0:
                self._pressed_modifiers.discard(modifier)

            return None

        trigger = get_trigger(
            event,
            self._keyboard_layout,
        )

        if trigger is None:
            return None

        if event.value != 1:
            return None

        shortcut = Shortcut(
            trigger=trigger,
            modifiers=frozenset(self._pressed_modifiers),
        )

        self._completed = True

        return shortcut
