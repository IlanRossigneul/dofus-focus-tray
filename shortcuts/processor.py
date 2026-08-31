import evdev

from input.events import InputEvent

from .capture import get_modifier, get_trigger
from .keyboard import KeyboardLayout
from .model import Shortcut


class ShortcutProcessor:
    """Convert input events into shortcuts."""

    def __init__(self, keyboard_layout: KeyboardLayout):
        self._keyboard_layout = keyboard_layout
        self._pressed_modifiers = set()

    def process_event(self, event: InputEvent) -> Shortcut | None:
        """Process an input event and return a shortcut when triggered."""

        if event.event_type != evdev.ecodes.EV_KEY:
            return None

        # Ignore key-repeat events.
        if event.value == 2:
            return None

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

        return Shortcut(
            trigger=trigger,
            modifiers=frozenset(self._pressed_modifiers),
        )
