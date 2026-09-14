import evdev

from helper.xkb import Xkb

from .model import Shortcut

MODIFIER_KEYS = {
    evdev.ecodes.KEY_LEFTCTRL: "CTRL",
    evdev.ecodes.KEY_RIGHTCTRL: "CTRL",
    evdev.ecodes.KEY_LEFTALT: "ALT",
    evdev.ecodes.KEY_RIGHTALT: "ALTGR",
    evdev.ecodes.KEY_LEFTSHIFT: "SHIFT",
    evdev.ecodes.KEY_RIGHTSHIFT: "SHIFT",
    evdev.ecodes.KEY_LEFTMETA: "META",
    evdev.ecodes.KEY_RIGHTMETA: "META",
}


MOUSE_BUTTON_CODES = {
    value
    for name, value in vars(evdev.ecodes).items()
    if name.startswith("BTN_") and isinstance(value, int)
}

IGNORED_MOUSE_BUTTONS = {
    evdev.ecodes.BTN_LEFT,
    evdev.ecodes.BTN_RIGHT,
    evdev.ecodes.BTN_MIDDLE,
}

MOUSE_TRIGGERS = {
    button: name
    for name, button in vars(evdev.ecodes).items()
    if (
        name.startswith("BTN_")
        and isinstance(button, int)
        and button not in IGNORED_MOUSE_BUTTONS
    )
}


class ShortcutCaptureRejected(Exception):
    """Raised when an input event is rejected during shortcut capture."""

    def __init__(
        self,
        trigger: str,
    ) -> None:
        super().__init__(trigger)
        self.trigger = trigger


def get_rejected_mouse_button(
    event,
    allowed_mouse_buttons: set[int],
) -> str | None:
    """Return the mouse button rejected during shortcut capture."""

    if event.event_type != evdev.ecodes.EV_KEY:
        return None

    if event.value != 1:
        return None

    if event.event_code not in MOUSE_BUTTON_CODES:
        return None

    if event.event_code in allowed_mouse_buttons:
        return None

    button_name = evdev.ecodes.bytype[evdev.ecodes.EV_KEY].get(
        event.event_code,
        f"BTN_{event.event_code}",
    )

    if isinstance(button_name, tuple):
        return button_name[0]

    return button_name


def get_trigger(
    event,
    xkb: Xkb,
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

    return xkb.keycode_to_key(
        event.event_code,
    )


def get_configured_mouse_buttons(
    configuration: dict,
) -> set[int]:
    """Return evdev codes for configured mouse-button shortcuts."""

    buttons = set()

    for shortcut_configuration in configuration.values():
        for shortcut in (
            shortcut_configuration.primary,
            shortcut_configuration.alternate,
        ):
            if shortcut is None:
                continue

            if not shortcut.trigger.startswith("BTN_"):
                continue

            event_code = getattr(
                evdev.ecodes,
                shortcut.trigger,
                None,
            )

            if event_code is not None:
                buttons.add(event_code)

    return buttons


class ShortcutCapture:
    """Capture one keyboard or supported mouse-button shortcut."""

    def __init__(
        self,
        xkb: Xkb,
        allowed_mouse_buttons: set[int] | None = None,
    ):
        self._xkb = xkb
        self._allowed_mouse_buttons = (
            allowed_mouse_buttons
            if allowed_mouse_buttons is not None
            else set(MOUSE_TRIGGERS)
        )
        self._completed = False

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

        trigger = get_trigger(
            event,
            self._xkb,
        )

        if trigger is None:
            return None

        if event.value != 1:
            return None

        shortcut = Shortcut(
            trigger=trigger,
            modifiers=event.modifiers,
        )

        self._completed = True

        return shortcut
