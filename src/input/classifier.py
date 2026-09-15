from dataclasses import dataclass
from enum import Enum

import evdev

from .discovery import InputDeviceInfo


class DeviceClass(Enum):
    KEYBOARD = "KEYBOARD"
    MOUSE = "MOUSE"
    GAMEPAD = "GAMEPAD"
    CONSUMER_CONTROL = "CONSUMER_CONTROL"
    SWITCH = "SWITCH"
    OTHER = "OTHER"


@dataclass(frozen=True)
class Classification:
    device_class: DeviceClass


def _has_event_code(
    device: InputDeviceInfo,
    event_type: int,
    code: int,
) -> bool:
    return code in device.capabilities.get(event_type, [])


def classify_device(device: InputDeviceInfo) -> Classification:
    """Classify an evdev interface from its reported capabilities."""

    capabilities = device.capabilities

    has_key = evdev.ecodes.EV_KEY in capabilities
    has_rel = evdev.ecodes.EV_REL in capabilities
    has_abs = evdev.ecodes.EV_ABS in capabilities
    has_sw = evdev.ecodes.EV_SW in capabilities

    if has_sw and not has_key and not has_rel and not has_abs:
        return Classification(DeviceClass.SWITCH)

    if has_rel:
        mouse_score = 0

        if _has_event_code(device, evdev.ecodes.EV_REL, evdev.ecodes.REL_X):
            mouse_score += 35

        if _has_event_code(device, evdev.ecodes.EV_REL, evdev.ecodes.REL_Y):
            mouse_score += 35

        if _has_event_code(device, evdev.ecodes.EV_REL, evdev.ecodes.REL_WHEEL):
            mouse_score += 15

        if _has_event_code(device, evdev.ecodes.EV_KEY, evdev.ecodes.BTN_LEFT):
            mouse_score += 10

        if _has_event_code(device, evdev.ecodes.EV_KEY, evdev.ecodes.BTN_RIGHT):
            mouse_score += 5

        if mouse_score >= 70:
            return Classification(DeviceClass.MOUSE)

    if has_abs:
        gamepad_score = 0

        if _has_event_code(device, evdev.ecodes.EV_ABS, evdev.ecodes.ABS_X):
            gamepad_score += 25

        if _has_event_code(device, evdev.ecodes.EV_ABS, evdev.ecodes.ABS_Y):
            gamepad_score += 25

        if _has_event_code(device, evdev.ecodes.EV_ABS, evdev.ecodes.ABS_RX):
            gamepad_score += 20

        if _has_event_code(device, evdev.ecodes.EV_ABS, evdev.ecodes.ABS_RY):
            gamepad_score += 20

        if gamepad_score >= 50:
            return Classification(DeviceClass.GAMEPAD)

    if has_key:
        keyboard_score = 0

        keyboard_keys = (
            evdev.ecodes.KEY_A,
            evdev.ecodes.KEY_Z,
            evdev.ecodes.KEY_ENTER,
            evdev.ecodes.KEY_SPACE,
        )

        keyboard_score += sum(
            20
            for code in keyboard_keys
            if _has_event_code(device, evdev.ecodes.EV_KEY, code)
        )

        consumer_keys = (
            evdev.ecodes.KEY_VOLUMEUP,
            evdev.ecodes.KEY_VOLUMEDOWN,
            evdev.ecodes.KEY_MUTE,
            evdev.ecodes.KEY_PLAYPAUSE,
        )

        consumer_count = sum(
            1
            for code in consumer_keys
            if _has_event_code(device, evdev.ecodes.EV_KEY, code)
        )

        if consumer_count >= 2 and keyboard_score == 0:
            return Classification(DeviceClass.CONSUMER_CONTROL)

        if keyboard_score >= 60:
            return Classification(
                DeviceClass.KEYBOARD,
            )

    if has_key:
        return Classification(DeviceClass.CONSUMER_CONTROL)

    return Classification(DeviceClass.OTHER)
