from dataclasses import dataclass, field

from .devices import HelperDevice
from .mouse import MouseGrabber, MouseInterceptor
from .policy import InputPolicy


@dataclass
class HelperState:
    """Store mutable runtime state shared by the helper."""

    handshake_completed: bool = False
    input_monitoring_active: bool = False
    capture_active: bool = False

    current_devices: list[HelperDevice] = field(default_factory=list)

    selected_keyboard: HelperDevice | None = None
    selected_mouse: HelperDevice | None = None

    mouse_interceptor: MouseInterceptor | None = None
    mouse_grabber: MouseGrabber | None = None

    intercepted_mouse_buttons: set[int] = field(default_factory=set)

    input_policy: InputPolicy = field(
        default_factory=InputPolicy,
    )

    next_mouse_discovery: float | None = None
