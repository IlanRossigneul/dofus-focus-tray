import json
import math
from typing import Any

PROTOCOL_VERSION = 1
MAX_COMMAND_SIZE = 64 * 1024

SHORTCUT_ACTIONS = frozenset(
    {
        "calibration",
        "next",
        "previous",
    }
)


# Tray → helper

COMMAND_HELLO = "hello"

COMMAND_START = "start"
COMMAND_STOP = "stop"

COMMAND_SET_SHORTCUT_CONFIGURATION = "set_shortcut_configuration"

COMMAND_SET_MOUSE_INTERCEPTION = "set_mouse_interception"
COMMAND_SET_INTERCEPTED_MOUSE_BUTTONS = "set_intercepted_mouse_buttons"

COMMAND_START_CAPTURE = "start_capture"
COMMAND_STOP_CAPTURE = "stop_capture"

COMMAND_GRAB_SELECTED_MOUSE = "grab_selected_mouse"
COMMAND_RELEASE_SELECTED_MOUSE = "release_selected_mouse"

COMMANDS = frozenset(
    {
        COMMAND_HELLO,
        COMMAND_START,
        COMMAND_STOP,
        COMMAND_SET_SHORTCUT_CONFIGURATION,
        COMMAND_SET_MOUSE_INTERCEPTION,
        COMMAND_SET_INTERCEPTED_MOUSE_BUTTONS,
        COMMAND_START_CAPTURE,
        COMMAND_STOP_CAPTURE,
        COMMAND_GRAB_SELECTED_MOUSE,
        COMMAND_RELEASE_SELECTED_MOUSE,
    }
)


# Helper → tray

EVENT_HELLO_ACK = "hello_ack"

EVENT_KEYBOARD_SELECTED = "keyboard_selected"
EVENT_KEYBOARD_SELECTED_LOST = "keyboard_selected_lost"
EVENT_MOUSE_SELECTED = "mouse_selected"
EVENT_MOUSE_SELECTED_LOST = "mouse_selected_lost"

EVENT_MOUSE_INTERCEPTION_STARTED = "mouse_interception_started"
EVENT_MOUSE_INTERCEPTION_STOPPED = "mouse_interception_stopped"

EVENT_KEYBOARD_EVENT = "keyboard_event"
EVENT_MOUSE_RELATIVE_EVENT = "mouse_relative_event"
EVENT_MOUSE_BUTTON_EVENT = "mouse_button_event"

EVENT_SHORTCUT = "shortcut"
EVENT_ERROR = "error"

EVENTS = frozenset(
    {
        EVENT_HELLO_ACK,
        EVENT_KEYBOARD_SELECTED,
        EVENT_KEYBOARD_SELECTED_LOST,
        EVENT_MOUSE_SELECTED,
        EVENT_MOUSE_SELECTED_LOST,
        EVENT_MOUSE_INTERCEPTION_STARTED,
        EVENT_MOUSE_INTERCEPTION_STOPPED,
        EVENT_KEYBOARD_EVENT,
        EVENT_MOUSE_RELATIVE_EVENT,
        EVENT_MOUSE_BUTTON_EVENT,
        EVENT_SHORTCUT,
        EVENT_ERROR,
    }
)


# Protocol error codes

ERROR_INVALID_MESSAGE = "invalid_message"
ERROR_INVALID_COMMAND = "invalid_command"
ERROR_INVALID_ARGUMENT = "invalid_argument"
ERROR_UNSUPPORTED_PROTOCOL = "unsupported_protocol"
ERROR_HELPER_NOT_READY = "helper_not_ready"
ERROR_DEVICE_ERROR = "device_error"
ERROR_MOUSE_INTERCEPTION_FAILED = "mouse_interception_failed"
ERROR_INTERNAL = "internal_error"

ERROR_CODES = frozenset(
    {
        ERROR_INVALID_MESSAGE,
        ERROR_INVALID_COMMAND,
        ERROR_INVALID_ARGUMENT,
        ERROR_UNSUPPORTED_PROTOCOL,
        ERROR_HELPER_NOT_READY,
        ERROR_DEVICE_ERROR,
        ERROR_MOUSE_INTERCEPTION_FAILED,
        ERROR_INTERNAL,
    }
)


class ProtocolError(ValueError):
    """Raised when an IPC message violates the protocol."""

    def __init__(
        self,
        message: str,
        code: str = ERROR_INVALID_MESSAGE,
    ) -> None:
        super().__init__(message)
        self.code = code


def _is_strict_bool(value: Any) -> bool:
    return type(value) is bool


def _is_strict_int(value: Any) -> bool:
    return type(value) is int


def _require_fields(
    message: dict[str, Any],
    required: set[str],
    allowed: set[str],
    error_code: str = ERROR_INVALID_MESSAGE,
) -> None:
    fields = set(message)

    missing = required - fields
    if missing:
        raise ProtocolError(
            f"Missing required field(s): {', '.join(sorted(missing))}.",
            error_code,
        )

    unexpected = fields - allowed
    if unexpected:
        raise ProtocolError(
            f"Unexpected field(s): {', '.join(sorted(unexpected))}.",
            error_code,
        )


def _require_event_fields(
    message: dict[str, Any],
    required: set[str],
    allowed: set[str],
) -> None:
    _require_fields(
        message,
        required=required,
        allowed=allowed,
    )


def _require_device_id(message: dict[str, Any]) -> None:
    device_id = message["device_id"]

    if not isinstance(device_id, str) or not device_id:
        raise ProtocolError("Field 'device_id' must be a non-empty string.")


def _validate_hello(message: dict[str, Any]) -> None:
    _require_fields(
        message,
        required={"type", "protocol"},
        allowed={"type", "protocol"},
        error_code=ERROR_INVALID_ARGUMENT,
    )

    if not _is_strict_int(message["protocol"]):
        raise ProtocolError(
            "Field 'protocol' must be an integer.",
            ERROR_INVALID_ARGUMENT,
        )

    if message["protocol"] != PROTOCOL_VERSION:
        raise ProtocolError(
            f"Unsupported protocol version: {message['protocol']}.",
            ERROR_UNSUPPORTED_PROTOCOL,
        )


def _validate_no_arguments(message: dict[str, Any]) -> None:
    _require_fields(
        message,
        required={"type"},
        allowed={"type"},
        error_code=ERROR_INVALID_ARGUMENT,
    )


def _validate_mouse_interception(message: dict[str, Any]) -> None:
    _require_fields(
        message,
        required={"type", "enabled"},
        allowed={"type", "enabled"},
        error_code=ERROR_INVALID_ARGUMENT,
    )

    if not _is_strict_bool(message["enabled"]):
        raise ProtocolError(
            "Field 'enabled' must be a boolean.",
            ERROR_INVALID_ARGUMENT,
        )


def _validate_intercepted_mouse_buttons(message: dict[str, Any]) -> None:
    _require_fields(
        message,
        required={"type", "buttons"},
        allowed={"type", "buttons"},
        error_code=ERROR_INVALID_ARGUMENT,
    )

    buttons = message["buttons"]

    if not isinstance(buttons, list):
        raise ProtocolError(
            "Field 'buttons' must be an array.",
            ERROR_INVALID_ARGUMENT,
        )

    if any(not _is_strict_int(button) for button in buttons):
        raise ProtocolError(
            "Field 'buttons' must contain only integers.",
            ERROR_INVALID_ARGUMENT,
        )

    if len(buttons) > 32:
        raise ProtocolError(
            "Field 'buttons' contains too many entries.",
            ERROR_INVALID_ARGUMENT,
        )

    if len(set(buttons)) != len(buttons):
        raise ProtocolError(
            "Field 'buttons' contains duplicate entries.",
            ERROR_INVALID_ARGUMENT,
        )


def _validate_shortcut(
    shortcut: Any,
) -> None:
    if shortcut is None:
        return

    if not isinstance(shortcut, dict):
        raise ProtocolError(
            "Shortcut must be an object or null.",
            ERROR_INVALID_ARGUMENT,
        )

    _require_fields(
        shortcut,
        required={"trigger", "modifiers"},
        allowed={"trigger", "modifiers"},
        error_code=ERROR_INVALID_ARGUMENT,
    )

    if not isinstance(shortcut["trigger"], str) or not shortcut["trigger"]:
        raise ProtocolError(
            "Field 'trigger' must be a non-empty string.",
            ERROR_INVALID_ARGUMENT,
        )

    modifiers = shortcut["modifiers"]

    if not isinstance(modifiers, list):
        raise ProtocolError(
            "Field 'modifiers' must be an array.",
            ERROR_INVALID_ARGUMENT,
        )

    if any(not isinstance(modifier, str) for modifier in modifiers):
        raise ProtocolError(
            "Field 'modifiers' must contain only strings.",
            ERROR_INVALID_ARGUMENT,
        )

    if len(set(modifiers)) != len(modifiers):
        raise ProtocolError(
            "Field 'modifiers' contains duplicate entries.",
            ERROR_INVALID_ARGUMENT,
        )


def _validate_shortcut_configuration(
    message: dict[str, Any],
) -> None:
    _require_fields(
        message,
        required={"type", "configuration"},
        allowed={"type", "configuration"},
        error_code=ERROR_INVALID_ARGUMENT,
    )

    configuration = message["configuration"]

    if not isinstance(configuration, dict):
        raise ProtocolError(
            "Field 'configuration' must be an object.",
            ERROR_INVALID_ARGUMENT,
        )

    if set(configuration) != SHORTCUT_ACTIONS:
        raise ProtocolError(
            "Field 'configuration' contains invalid actions.",
            ERROR_INVALID_ARGUMENT,
        )

    for action in SHORTCUT_ACTIONS:
        action_configuration = configuration[action]

        if not isinstance(action_configuration, dict):
            raise ProtocolError(
                f"Configuration for action '{action}' must be an object.",
                ERROR_INVALID_ARGUMENT,
            )

        _require_fields(
            action_configuration,
            required={"primary", "alternate"},
            allowed={"primary", "alternate"},
            error_code=ERROR_INVALID_ARGUMENT,
        )

        _validate_shortcut(action_configuration["primary"])
        _validate_shortcut(action_configuration["alternate"])


def _validate_start_capture(message: dict[str, Any]) -> None:
    _require_fields(
        message,
        required={"type", "allowed_mouse_buttons"},
        allowed={"type", "allowed_mouse_buttons"},
        error_code=ERROR_INVALID_ARGUMENT,
    )

    buttons = message["allowed_mouse_buttons"]

    if buttons is None:
        return

    if not isinstance(buttons, list):
        raise ProtocolError(
            "Field 'allowed_mouse_buttons' must be an array or null.",
            ERROR_INVALID_ARGUMENT,
        )

    if any(not _is_strict_int(button) for button in buttons):
        raise ProtocolError(
            "Field 'allowed_mouse_buttons' must contain only integers.",
            ERROR_INVALID_ARGUMENT,
        )

    if len(buttons) > 32:
        raise ProtocolError(
            "Field 'allowed_mouse_buttons' contains too many entries.",
            ERROR_INVALID_ARGUMENT,
        )

    if len(set(buttons)) != len(buttons):
        raise ProtocolError(
            "Field 'allowed_mouse_buttons' contains duplicate entries.",
            ERROR_INVALID_ARGUMENT,
        )


def _validate_hello_ack(message: dict[str, Any]) -> None:
    _require_event_fields(
        message,
        required={"type", "protocol"},
        allowed={"type", "protocol"},
    )

    if not _is_strict_int(message["protocol"]):
        raise ProtocolError("Field 'protocol' must be an integer.")

    if message["protocol"] != PROTOCOL_VERSION:
        raise ProtocolError(f"Unsupported protocol version: {message['protocol']}.")


def _validate_device_event(message: dict[str, Any]) -> None:
    _require_event_fields(
        message,
        required={"type", "device_id"},
        allowed={"type", "device_id"},
    )

    _require_device_id(message)


def _validate_selected_device_lost(message: dict[str, Any]) -> None:
    _require_event_fields(
        message,
        required={"type"},
        allowed={"type"},
    )


def _validate_shortcut_event(message: dict[str, Any]) -> None:
    """Validate a recognized shortcut event."""

    _require_event_fields(
        message,
        required={"type", "action"},
        allowed={"type", "action"},
    )

    if message["action"] not in SHORTCUT_ACTIONS:
        raise ProtocolError("Unknown shortcut action.")


def _validate_input_event(message: dict[str, Any]) -> None:
    _require_event_fields(
        message,
        required={
            "type",
            "device_id",
            "code",
            "value",
            "timestamp",
        },
        allowed={
            "type",
            "device_id",
            "code",
            "value",
            "timestamp",
            "modifiers",
        },
    )

    _require_device_id(message)

    if not _is_strict_int(message["code"]):
        raise ProtocolError("Field 'code' must be an integer.")

    if not _is_strict_int(message["value"]):
        raise ProtocolError("Field 'value' must be an integer.")

    timestamp = message["timestamp"]

    if type(timestamp) not in {int, float}:
        raise ProtocolError("Field 'timestamp' must be a number.")

    if isinstance(timestamp, float) and not math.isfinite(timestamp):
        raise ProtocolError("Field 'timestamp' must be finite.")

    modifiers = message.get("modifiers")

    if modifiers is not None:
        if not isinstance(modifiers, list):
            raise ProtocolError(
                "Field 'modifiers' must be an array.",
            )

        if any(not isinstance(modifier, str) for modifier in modifiers):
            raise ProtocolError(
                "Field 'modifiers' must contain only strings.",
            )

        if len(set(modifiers)) != len(modifiers):
            raise ProtocolError(
                "Field 'modifiers' contains duplicate entries.",
            )


def _validate_error(message: dict[str, Any]) -> None:
    _require_event_fields(
        message,
        required={"type", "code", "message"},
        allowed={"type", "code", "message", "command"},
    )

    if not isinstance(message["code"], str):
        raise ProtocolError("Field 'code' must be a string.")

    if message["code"] not in ERROR_CODES:
        raise ProtocolError(f"Unknown error code: {message['code']}.")

    if not isinstance(message["message"], str):
        raise ProtocolError("Field 'message' must be a string.")

    command = message.get("command")

    if command is not None and command not in COMMANDS:
        raise ProtocolError(f"Unknown error command: {message['command']}.")


def validate_command(message: Any) -> dict[str, Any]:
    """Validate a tray command and return it unchanged."""
    if not isinstance(message, dict):
        raise ProtocolError("Message must be a JSON object.")

    message_type = message.get("type")

    if not isinstance(message_type, str):
        raise ProtocolError("Field 'type' must be a string.")

    if message_type not in COMMANDS:
        raise ProtocolError(
            f"Unknown command: {message_type}.",
            ERROR_INVALID_COMMAND,
        )

    if message_type == COMMAND_HELLO:
        _validate_hello(message)
    elif message_type in {
        COMMAND_START,
        COMMAND_STOP,
        COMMAND_STOP_CAPTURE,
        COMMAND_GRAB_SELECTED_MOUSE,
        COMMAND_RELEASE_SELECTED_MOUSE,
    }:
        _validate_no_arguments(message)
    elif message_type == COMMAND_START_CAPTURE:
        _validate_start_capture(message)
    elif message_type == COMMAND_SET_MOUSE_INTERCEPTION:
        _validate_mouse_interception(message)
    elif message_type == COMMAND_SET_INTERCEPTED_MOUSE_BUTTONS:
        _validate_intercepted_mouse_buttons(message)
    elif message_type == COMMAND_SET_SHORTCUT_CONFIGURATION:
        _validate_shortcut_configuration(message)

    return message


def validate_event(message: Any) -> dict[str, Any]:
    """Validate a helper event and return it unchanged."""
    if not isinstance(message, dict):
        raise ProtocolError("Message must be a JSON object.")

    message_type = message.get("type")

    if not isinstance(message_type, str):
        raise ProtocolError("Field 'type' must be a string.")

    if message_type not in EVENTS:
        raise ProtocolError(f"Unknown event: {message_type}.")

    if message_type == EVENT_SHORTCUT:
        _validate_shortcut_event(message)
    elif message_type == EVENT_HELLO_ACK:
        _validate_hello_ack(message)
    elif message_type in {
        EVENT_KEYBOARD_SELECTED,
        EVENT_MOUSE_SELECTED,
        EVENT_MOUSE_INTERCEPTION_STARTED,
        EVENT_MOUSE_INTERCEPTION_STOPPED,
    }:
        _validate_device_event(message)
    elif message_type in {
        EVENT_KEYBOARD_SELECTED_LOST,
        EVENT_MOUSE_SELECTED_LOST,
    }:
        _validate_selected_device_lost(message)
    elif message_type in {
        EVENT_KEYBOARD_EVENT,
        EVENT_MOUSE_RELATIVE_EVENT,
        EVENT_MOUSE_BUTTON_EVENT,
    }:
        _validate_input_event(message)
    elif message_type == EVENT_ERROR:
        _validate_error(message)

    return message


def encode_command(message: dict[str, Any]) -> bytes:
    """Encode a tray command as one UTF-8 JSON Lines record."""
    validate_command(message)

    return (
        json.dumps(
            message,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def encode_event(message: dict[str, Any]) -> bytes:
    """Encode a helper event as one UTF-8 JSON Lines record."""
    validate_event(message)

    return (
        json.dumps(
            message,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _decode_json_line(line: bytes) -> dict[str, Any]:
    """Decode one UTF-8 JSON Lines record."""
    if len(line) > MAX_COMMAND_SIZE:
        raise ProtocolError("Message exceeds maximum size.")

    if not line.endswith(b"\n"):
        raise ProtocolError("JSON Lines record must end with a newline.")

    try:
        text = line[:-1].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProtocolError("Message is not valid UTF-8.") from exc

    try:
        message = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProtocolError("Message is not valid JSON.") from exc

    if not isinstance(message, dict):
        raise ProtocolError("Message must be a JSON object.")

    return message


def decode_command(line: bytes) -> dict[str, Any]:
    """Decode and validate one tray command."""
    return validate_command(_decode_json_line(line))


def decode_event(line: bytes) -> dict[str, Any]:
    """Decode and validate one helper event."""
    return validate_event(_decode_json_line(line))
