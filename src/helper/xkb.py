import ctypes
import os
import subprocess
from ctypes import (
    c_char_p,
    c_int,
    c_uint32,
    c_void_p,
)

XKB_CONTEXT_NO_FLAGS = 0
XKB_KEYMAP_FORMAT_TEXT_V1 = 1
XKB_KEYMAP_COMPILE_NO_FLAGS = 0
XKB_KEYSYM_NO_SYMBOL = 0

XKB_KEY_DOWN = 1
XKB_KEY_UP = 0
XKB_KEY_REPEATED = 2

XKB_KEYCODE_OFFSET = 8


class Xkb:
    """Provide access to the active Wayland XKB keymap."""

    def __init__(self) -> None:
        self._xkb = ctypes.CDLL("libxkbcommon.so.0")

        self._context: c_void_p | None = None
        self._keymap: c_void_p | None = None
        self._state: c_void_p | None = None

        self._configure_api()

    def _configure_api(self) -> None:
        """Configure the libxkbcommon functions used by this class."""

        self._xkb.xkb_context_new.argtypes = [c_int]
        self._xkb.xkb_context_new.restype = c_void_p

        self._xkb.xkb_context_unref.argtypes = [c_void_p]
        self._xkb.xkb_context_unref.restype = None

        self._xkb.xkb_keymap_new_from_string.argtypes = [
            c_void_p,
            c_char_p,
            c_int,
            c_int,
        ]
        self._xkb.xkb_keymap_new_from_string.restype = c_void_p

        self._xkb.xkb_keymap_unref.argtypes = [c_void_p]
        self._xkb.xkb_keymap_unref.restype = None

        self._xkb.xkb_state_new.argtypes = [c_void_p]
        self._xkb.xkb_state_new.restype = c_void_p

        self._xkb.xkb_state_unref.argtypes = [c_void_p]
        self._xkb.xkb_state_unref.restype = None

        self._xkb.xkb_state_update_key.argtypes = [
            c_void_p,
            c_uint32,
            c_int,
        ]
        self._xkb.xkb_state_update_key.restype = c_int

        self._xkb.xkb_state_key_get_one_sym.argtypes = [
            c_void_p,
            c_uint32,
        ]
        self._xkb.xkb_state_key_get_one_sym.restype = c_uint32

        self._xkb.xkb_keysym_get_name.argtypes = [
            c_uint32,
            c_char_p,
            c_int,
        ]
        self._xkb.xkb_keysym_get_name.restype = c_int

    def load_wayland_keymap(self) -> None:
        """Load the active XKB keymap from the Wayland compositor."""

        runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
        wayland_display = os.environ.get("WAYLAND_DISPLAY")

        if not runtime_dir:
            raise RuntimeError(
                "XDG_RUNTIME_DIR is not set.",
            )

        if not wayland_display:
            raise RuntimeError(
                "WAYLAND_DISPLAY is not set.",
            )

        environment = os.environ.copy()
        environment["XDG_RUNTIME_DIR"] = runtime_dir
        environment["WAYLAND_DISPLAY"] = wayland_display

        try:
            result = subprocess.run(
                ["xkbcli", "dump-keymap-wayland"],
                env=environment,
                check=True,
                capture_output=True,
            )
        except FileNotFoundError as error:
            raise RuntimeError(
                "xkbcli was not found.",
            ) from error
        except subprocess.CalledProcessError as error:
            message = error.stderr.decode(
                "utf-8",
                errors="replace",
            ).strip()

            raise RuntimeError(
                f"Failed to retrieve the Wayland XKB keymap: {message}",
            ) from error

        self._load_keymap(result.stdout)

    def _load_keymap(self, keymap_text: bytes) -> None:
        """Compile a keymap and create its XKB state."""

        self.close()

        context = self._xkb.xkb_context_new(
            XKB_CONTEXT_NO_FLAGS,
        )

        if context is None:
            raise RuntimeError(
                "Failed to create XKB context.",
            )

        self._context = context

        keymap = self._xkb.xkb_keymap_new_from_string(
            context,
            keymap_text,
            XKB_KEYMAP_FORMAT_TEXT_V1,
            XKB_KEYMAP_COMPILE_NO_FLAGS,
        )

        if keymap is None:
            self.close()
            raise RuntimeError(
                "Failed to compile the Wayland XKB keymap.",
            )

        self._keymap = keymap

        state = self._xkb.xkb_state_new(keymap)

        if state is None:
            self.close()
            raise RuntimeError(
                "Failed to create XKB state.",
            )

        self._state = state

    def _require_state(self) -> c_void_p:
        """Return the active XKB state or raise if unavailable."""

        if self._state is None:
            raise RuntimeError(
                "XKB keymap is not loaded.",
            )

        return self._state

    @staticmethod
    def _to_xkb_keycode(keycode: int) -> int:
        """Convert an evdev keycode to an XKB keycode."""

        return keycode + XKB_KEYCODE_OFFSET

    def update_key(
        self,
        keycode: int,
        value: int,
    ) -> None:
        """Update the XKB state from an evdev key event."""

        state = self._require_state()

        if value == 0:
            direction = XKB_KEY_UP
        elif value == 1:
            direction = XKB_KEY_DOWN
        elif value == 2:
            direction = XKB_KEY_REPEATED
        else:
            return

        self._xkb.xkb_state_update_key(
            state,
            self._to_xkb_keycode(keycode),
            direction,
        )

    def keycode_to_key(self, keycode: int) -> str | None:
        """Translate an evdev keycode using the active XKB state."""

        state = self._require_state()

        keysym = self._xkb.xkb_state_key_get_one_sym(
            state,
            self._to_xkb_keycode(keycode),
        )

        if keysym == XKB_KEYSYM_NO_SYMBOL:
            return None

        buffer = ctypes.create_string_buffer(64)

        result = self._xkb.xkb_keysym_get_name(
            keysym,
            buffer,
            len(buffer),
        )

        if result <= 0:
            return None

        return buffer.value.decode("ascii")

    def reset(self) -> None:
        """Reset the current XKB keyboard state."""

        if self._keymap is None:
            raise RuntimeError(
                "XKB keymap is not loaded.",
            )

        state = self._xkb.xkb_state_new(
            self._keymap,
        )

        if state is None:
            raise RuntimeError(
                "Failed to reset XKB state.",
            )

        if self._state is not None:
            self._xkb.xkb_state_unref(
                self._state,
            )

        self._state = state

    def close(self) -> None:
        """Release XKB state, keymap, and context."""

        if self._state is not None:
            self._xkb.xkb_state_unref(self._state)
            self._state = None

        if self._keymap is not None:
            self._xkb.xkb_keymap_unref(self._keymap)
            self._keymap = None

        if self._context is not None:
            self._xkb.xkb_context_unref(self._context)
            self._context = None
