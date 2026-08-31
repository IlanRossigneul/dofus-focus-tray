import ctypes
from ctypes import c_char_p, c_int, c_uint32, c_void_p
from dataclasses import dataclass

from dbus_next.aio import MessageBus
from dbus_next.constants import BusType

KDE_KEYBOARD_BUS = "org.kde.keyboard"
KDE_KEYBOARD_PATH = "/Layouts"
KDE_KEYBOARD_INTERFACE = "org.kde.KeyboardLayouts"

XKB_KEYCODE_OFFSET = 8
XKB_CONTEXT_NO_FLAGS = 0
XKB_KEYMAP_COMPILE_NO_FLAGS = 0
XKB_KEYSYM_NO_SYMBOL = 0


@dataclass(frozen=True)
class KeyboardLayoutInfo:
    """Describe a keyboard layout configured in KDE."""

    layout: str
    variant: str
    name: str


class XkbRuleNames(ctypes.Structure):
    _fields_ = [
        ("rules", c_char_p),
        ("model", c_char_p),
        ("layout", c_char_p),
        ("variant", c_char_p),
        ("options", c_char_p),
    ]


class KeyboardLayout:
    """Provide access to the active KDE keyboard layout."""

    def __init__(self) -> None:
        self._bus = None
        self._interface = None
        self._layout_index = None
        self._layouts = []

        self._xkb = ctypes.CDLL("libxkbcommon.so.0")
        self._xkb_context = None
        self._xkb_keymap = None
        self._xkb_state = None

        self._configure_xkb_api()

    def _configure_xkb_api(self) -> None:
        """Configure the libxkbcommon functions used by this class."""

        self._xkb.xkb_context_new.argtypes = [c_int]
        self._xkb.xkb_context_new.restype = c_void_p

        self._xkb.xkb_context_unref.argtypes = [c_void_p]

        self._xkb.xkb_keymap_new_from_names.argtypes = [
            c_void_p,
            c_void_p,
            c_int,
        ]
        self._xkb.xkb_keymap_new_from_names.restype = c_void_p

        self._xkb.xkb_keymap_unref.argtypes = [c_void_p]

        self._xkb.xkb_state_new.argtypes = [c_void_p]
        self._xkb.xkb_state_new.restype = c_void_p

        self._xkb.xkb_state_unref.argtypes = [c_void_p]

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

    async def connect(self) -> None:
        """Connect to KDE's keyboard layout service."""

        self._bus = await MessageBus(
            bus_type=BusType.SESSION,
        ).connect()

        introspection = await self._bus.introspect(
            KDE_KEYBOARD_BUS,
            KDE_KEYBOARD_PATH,
        )

        proxy = self._bus.get_proxy_object(
            KDE_KEYBOARD_BUS,
            KDE_KEYBOARD_PATH,
            introspection,
        )

        self._interface = proxy.get_interface(
            KDE_KEYBOARD_INTERFACE,
        )

        self._interface.on_layout_changed(
            self._on_layout_changed,
        )

        await self._refresh()
        self._create_xkb_keymap()

    async def _refresh(self) -> None:
        """Refresh the current layout and configured layouts."""

        self._layout_index = await self._interface.call_get_layout()

        layouts = await self._interface.call_get_layouts_list()

        self._layouts = [
            KeyboardLayoutInfo(
                layout=layout,
                variant=variant,
                name=name,
            )
            for layout, variant, name in layouts
        ]

    async def _on_layout_changed(self, index: int) -> None:
        """Update the active layout after a KDE layout change."""

        self._layout_index = index
        self._create_xkb_keymap()

    def _create_xkb_keymap(self) -> None:
        """Create an XKB keymap for the active KDE layout."""

        layout = self.current

        if layout is None:
            return

        if self._xkb_state is not None:
            self._xkb.xkb_state_unref(self._xkb_state)
            self._xkb_state = None

        if self._xkb_keymap is not None:
            self._xkb.xkb_keymap_unref(self._xkb_keymap)
            self._xkb_keymap = None

        if self._xkb_context is None:
            self._xkb_context = self._xkb.xkb_context_new(
                XKB_CONTEXT_NO_FLAGS,
            )

        if self._xkb_context is None:
            raise RuntimeError("Failed to create XKB context.")

        names = XkbRuleNames(
            rules=b"evdev",
            model=b"pc105",
            layout=layout.layout.encode(),
            variant=layout.variant.encode() or None,
            options=None,
        )

        self._xkb_keymap = self._xkb.xkb_keymap_new_from_names(
            self._xkb_context,
            ctypes.byref(names),
            XKB_KEYMAP_COMPILE_NO_FLAGS,
        )

        if self._xkb_keymap is None:
            raise RuntimeError(
                f"Failed to create XKB keymap for layout "
                f"{layout.layout!r}, variant {layout.variant!r}."
            )

        self._xkb_state = self._xkb.xkb_state_new(
            self._xkb_keymap,
        )

        if self._xkb_state is None:
            self._xkb.xkb_keymap_unref(self._xkb_keymap)
            self._xkb_keymap = None

            raise RuntimeError("Failed to create XKB state.")

    def keycode_to_key(self, keycode: int) -> str | None:
        """Translate an evdev keycode using the active XKB layout."""

        if self._xkb_state is None:
            raise RuntimeError("Keyboard layout is not connected.")

        xkb_keycode = keycode + XKB_KEYCODE_OFFSET

        keysym = self._xkb.xkb_state_key_get_one_sym(
            self._xkb_state,
            xkb_keycode,
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

    @property
    def current(self) -> KeyboardLayoutInfo | None:
        """Return the currently active keyboard layout."""

        if self._layout_index is None:
            return None

        if not 0 <= self._layout_index < len(self._layouts):
            return None

        return self._layouts[self._layout_index]

    async def close(self) -> None:
        """Close the D-Bus connection and release XKB resources."""

        if self._xkb_state is not None:
            self._xkb.xkb_state_unref(self._xkb_state)
            self._xkb_state = None

        if self._xkb_keymap is not None:
            self._xkb.xkb_keymap_unref(self._xkb_keymap)
            self._xkb_keymap = None

        if self._xkb_context is not None:
            self._xkb.xkb_context_unref(self._xkb_context)
            self._xkb_context = None

        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
