import json

import pytest

from helper.protocol import (
    COMMAND_HELLO,
    COMMAND_SET_INTERCEPTED_MOUSE_BUTTONS,
    COMMAND_SET_MOUSE_INTERCEPTION,
    COMMAND_SET_SHORTCUT_CONFIGURATION,
    COMMAND_START,
    COMMAND_STOP,
    ERROR_INVALID_ARGUMENT,
    ERROR_INVALID_COMMAND,
    ERROR_INVALID_MESSAGE,
    ERROR_UNSUPPORTED_PROTOCOL,
    EVENT_ERROR,
    EVENT_HELLO_ACK,
    EVENT_KEYBOARD_EVENT,
    EVENT_MOUSE_BUTTON_EVENT,
    EVENT_MOUSE_INTERCEPTION_STARTED,
    EVENT_MOUSE_INTERCEPTION_STOPPED,
    EVENT_MOUSE_RELATIVE_EVENT,
    EVENT_MOUSE_SELECTED,
    EVENT_MOUSE_SELECTED_LOST,
    EVENT_SHORTCUT,
    MAX_COMMAND_SIZE,
    PROTOCOL_VERSION,
    ProtocolError,
    decode_command,
    decode_event,
    encode_command,
    encode_event,
)


def assert_protocol_error(callable_obj, expected_code):
    with pytest.raises(ProtocolError) as exc_info:
        callable_obj()

    assert exc_info.value.code == expected_code


# ---------------------------------------------------------------------------
# Command encoding and decoding
# ---------------------------------------------------------------------------


def test_encode_command_produces_json_line():
    message = {
        "type": COMMAND_START,
    }

    encoded = encode_command(message)

    assert encoded.endswith(b"\n")
    assert json.loads(encoded.decode("utf-8")) == message


def test_command_round_trip():
    message = {
        "type": COMMAND_SET_MOUSE_INTERCEPTION,
        "enabled": True,
    }

    assert decode_command(encode_command(message)) == message


def test_invalid_json_is_rejected():
    assert_protocol_error(
        lambda: decode_command(b'{"type":start}\n'),
        ERROR_INVALID_MESSAGE,
    )


def test_invalid_utf8_is_rejected():
    assert_protocol_error(
        lambda: decode_command(b'{"type":"start"}\xff\n'),
        ERROR_INVALID_MESSAGE,
    )


def test_non_object_json_is_rejected():
    assert_protocol_error(
        lambda: decode_command(b'["start"]\n'),
        ERROR_INVALID_MESSAGE,
    )


def test_missing_newline_is_rejected():
    assert_protocol_error(
        lambda: decode_command(b'{"type":"start"}'),
        ERROR_INVALID_MESSAGE,
    )


def test_oversized_message_is_rejected():
    line = b"{" + b"a" * MAX_COMMAND_SIZE + b"}\n"

    assert len(line) > MAX_COMMAND_SIZE

    assert_protocol_error(
        lambda: decode_command(line),
        ERROR_INVALID_MESSAGE,
    )


# ---------------------------------------------------------------------------
# Command validation
# ---------------------------------------------------------------------------


def test_unknown_command_is_rejected():
    assert_protocol_error(
        lambda: decode_command(b'{"type":"unknown"}\n'),
        ERROR_INVALID_COMMAND,
    )


def test_missing_command_type_is_rejected():
    assert_protocol_error(
        lambda: decode_command(b'{"protocol":1}\n'),
        ERROR_INVALID_MESSAGE,
    )


def test_non_string_command_type_is_rejected():
    assert_protocol_error(
        lambda: decode_command(b'{"type":123}\n'),
        ERROR_INVALID_MESSAGE,
    )


# ---------------------------------------------------------------------------
# HELLO
# ---------------------------------------------------------------------------


def test_valid_hello():
    message = {
        "type": COMMAND_HELLO,
        "protocol": PROTOCOL_VERSION,
    }

    assert decode_command(encode_command(message)) == message


def test_hello_missing_protocol():
    assert_protocol_error(
        lambda: decode_command(b'{"type":"hello"}\n'),
        ERROR_INVALID_ARGUMENT,
    )


def test_hello_with_extra_field():
    assert_protocol_error(
        lambda: decode_command(b'{"type":"hello","protocol":1,"extra":true}\n'),
        ERROR_INVALID_ARGUMENT,
    )


def test_hello_protocol_must_be_integer():
    assert_protocol_error(
        lambda: decode_command(b'{"type":"hello","protocol":"1"}\n'),
        ERROR_INVALID_ARGUMENT,
    )


def test_hello_protocol_version_mismatch():
    assert_protocol_error(
        lambda: decode_command(b'{"type":"hello","protocol":999}\n'),
        ERROR_UNSUPPORTED_PROTOCOL,
    )


# ---------------------------------------------------------------------------
# START / STOP
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command_type",
    [COMMAND_START, COMMAND_STOP],
)
def test_no_argument_command_is_valid(command_type):
    message = {
        "type": command_type,
    }

    assert decode_command(encode_command(message)) == message


@pytest.mark.parametrize(
    "command_type",
    [COMMAND_START, COMMAND_STOP],
)
def test_no_argument_command_rejects_extra_fields(command_type):
    message = {
        "type": command_type,
        "extra": True,
    }

    assert_protocol_error(
        lambda: encode_command(message),
        ERROR_INVALID_ARGUMENT,
    )


# ---------------------------------------------------------------------------
# SET_MOUSE_INTERCEPTION
# ---------------------------------------------------------------------------


def test_set_mouse_interception_accepts_boolean():
    for enabled in (True, False):
        message = {
            "type": COMMAND_SET_MOUSE_INTERCEPTION,
            "enabled": enabled,
        }

        assert decode_command(encode_command(message)) == message


def test_set_mouse_interception_requires_enabled():
    assert_protocol_error(
        lambda: decode_command(b'{"type":"set_mouse_interception"}\n'),
        ERROR_INVALID_ARGUMENT,
    )


@pytest.mark.parametrize(
    "value",
    [0, 1, "true", None, [], {}],
)
def test_set_mouse_interception_requires_boolean(value):
    message = {
        "type": COMMAND_SET_MOUSE_INTERCEPTION,
        "enabled": value,
    }

    assert_protocol_error(
        lambda: encode_command(message),
        ERROR_INVALID_ARGUMENT,
    )


def test_set_mouse_interception_rejects_extra_fields():
    message = {
        "type": COMMAND_SET_MOUSE_INTERCEPTION,
        "enabled": True,
        "extra": True,
    }

    assert_protocol_error(
        lambda: encode_command(message),
        ERROR_INVALID_ARGUMENT,
    )


# ---------------------------------------------------------------------------
# SET_INTERCEPTED_MOUSE_BUTTONS
# ---------------------------------------------------------------------------


def test_set_intercepted_mouse_buttons_accepts_empty_list():
    message = {
        "type": COMMAND_SET_INTERCEPTED_MOUSE_BUTTONS,
        "buttons": [],
    }

    assert decode_command(encode_command(message)) == message


def test_set_intercepted_mouse_buttons_accepts_unique_integer_codes():
    message = {
        "type": COMMAND_SET_INTERCEPTED_MOUSE_BUTTONS,
        "buttons": [275, 276],
    }

    assert decode_command(encode_command(message)) == message


def test_set_intercepted_mouse_buttons_requires_buttons():
    assert_protocol_error(
        lambda: decode_command(b'{"type":"set_intercepted_mouse_buttons"}\n'),
        ERROR_INVALID_ARGUMENT,
    )


@pytest.mark.parametrize(
    "value",
    [None, "275", 275, {}, [275, "276"], [True]],
)
def test_set_intercepted_mouse_buttons_requires_integer_list(value):
    message = {
        "type": COMMAND_SET_INTERCEPTED_MOUSE_BUTTONS,
        "buttons": value,
    }

    assert_protocol_error(
        lambda: encode_command(message),
        ERROR_INVALID_ARGUMENT,
    )


def test_set_intercepted_mouse_buttons_rejects_too_many_entries():
    message = {
        "type": COMMAND_SET_INTERCEPTED_MOUSE_BUTTONS,
        "buttons": list(range(33)),
    }

    assert_protocol_error(
        lambda: encode_command(message),
        ERROR_INVALID_ARGUMENT,
    )


def test_set_intercepted_mouse_buttons_rejects_duplicates():
    message = {
        "type": COMMAND_SET_INTERCEPTED_MOUSE_BUTTONS,
        "buttons": [275, 276, 275],
    }

    assert_protocol_error(
        lambda: encode_command(message),
        ERROR_INVALID_ARGUMENT,
    )


def test_set_intercepted_mouse_buttons_rejects_extra_fields():
    message = {
        "type": COMMAND_SET_INTERCEPTED_MOUSE_BUTTONS,
        "buttons": [275],
        "extra": True,
    }

    assert_protocol_error(
        lambda: encode_command(message),
        ERROR_INVALID_ARGUMENT,
    )


# ---------------------------------------------------------------------------
# Event validation
# ---------------------------------------------------------------------------


def test_valid_hello_ack():
    message = {
        "type": EVENT_HELLO_ACK,
        "protocol": PROTOCOL_VERSION,
    }

    assert decode_event(encode_event(message)) == message


def test_hello_ack_protocol_must_be_integer():
    message = {
        "type": EVENT_HELLO_ACK,
        "protocol": "1",
    }

    assert_protocol_error(
        lambda: encode_event(message),
        ERROR_INVALID_MESSAGE,
    )


def test_hello_ack_protocol_version_mismatch():
    message = {
        "type": EVENT_HELLO_ACK,
        "protocol": 999,
    }

    assert_protocol_error(
        lambda: encode_event(message),
        ERROR_INVALID_MESSAGE,
    )


@pytest.mark.parametrize(
    "event_type",
    [
        EVENT_MOUSE_SELECTED,
        EVENT_MOUSE_INTERCEPTION_STARTED,
        EVENT_MOUSE_INTERCEPTION_STOPPED,
    ],
)
def test_device_event_requires_device_id(event_type):
    message = {
        "type": event_type,
    }

    assert_protocol_error(
        lambda: encode_event(message),
        ERROR_INVALID_MESSAGE,
    )


def test_valid_input_event():
    message = {
        "type": EVENT_KEYBOARD_EVENT,
        "device_id": "keyboard-1",
        "code": 30,
        "value": 1,
        "timestamp": 123.456,
    }

    assert decode_event(encode_event(message)) == message


@pytest.mark.parametrize(
    "event_type",
    [
        EVENT_KEYBOARD_EVENT,
        EVENT_MOUSE_RELATIVE_EVENT,
        EVENT_MOUSE_BUTTON_EVENT,
    ],
)
def test_input_event_requires_device_id(event_type):
    message = {
        "type": event_type,
        "code": 30,
        "value": 1,
        "timestamp": 123.456,
    }

    assert_protocol_error(
        lambda: encode_event(message),
        ERROR_INVALID_MESSAGE,
    )


@pytest.mark.parametrize(
    "field",
    ["code", "value"],
)
def test_input_event_requires_integer_fields(field):
    message = {
        "type": EVENT_KEYBOARD_EVENT,
        "device_id": "keyboard-1",
        "code": 30,
        "value": 1,
        "timestamp": 123.456,
    }
    message[field] = "invalid"

    assert_protocol_error(
        lambda: encode_event(message),
        ERROR_INVALID_MESSAGE,
    )


def test_input_event_requires_numeric_timestamp():
    message = {
        "type": EVENT_KEYBOARD_EVENT,
        "device_id": "keyboard-1",
        "code": 30,
        "value": 1,
        "timestamp": "invalid",
    }

    assert_protocol_error(
        lambda: encode_event(message),
        ERROR_INVALID_MESSAGE,
    )


# ---------------------------------------------------------------------------
# ERROR event
# ---------------------------------------------------------------------------


def test_valid_error_event():
    message = {
        "type": EVENT_ERROR,
        "code": ERROR_INVALID_ARGUMENT,
        "message": "Invalid argument.",
    }

    assert decode_event(encode_event(message)) == message


def test_error_event_rejects_unknown_error_code():
    message = {
        "type": EVENT_ERROR,
        "code": "unknown_error",
        "message": "Something went wrong.",
    }

    assert_protocol_error(
        lambda: encode_event(message),
        ERROR_INVALID_MESSAGE,
    )


def test_unknown_event_is_rejected():
    assert_protocol_error(
        lambda: decode_event(b'{"type":"unknown_event"}\n'),
        ERROR_INVALID_MESSAGE,
    )


def test_valid_mouse_selected_lost():
    message = {
        "type": EVENT_MOUSE_SELECTED_LOST,
    }

    assert decode_event(encode_event(message)) == message


def test_mouse_selected_lost_rejects_extra_fields():
    message = {
        "type": EVENT_MOUSE_SELECTED_LOST,
        "device_id": "mouse-1",
    }

    assert_protocol_error(
        lambda: encode_event(message),
        ERROR_INVALID_MESSAGE,
    )


# ---------------------------------------------------------------------------
# SET_SHORTCUT_CONFIGURATION
# ---------------------------------------------------------------------------


def test_set_shortcut_configuration_accepts_valid_configuration():
    message = {
        "type": COMMAND_SET_SHORTCUT_CONFIGURATION,
        "configuration": {
            "calibration": {
                "primary": {
                    "trigger": "F1",
                    "modifiers": ["CTRL"],
                },
                "alternate": None,
            },
            "next": {
                "primary": {
                    "trigger": "N",
                    "modifiers": ["META"],
                },
                "alternate": {
                    "trigger": "BTN_EXTRA",
                    "modifiers": [],
                },
            },
            "previous": {
                "primary": {
                    "trigger": "N",
                    "modifiers": ["META", "SHIFT"],
                },
                "alternate": {
                    "trigger": "BTN_SIDE",
                    "modifiers": [],
                },
            },
        },
    }

    assert decode_command(encode_command(message)) == message


@pytest.mark.parametrize(
    "configuration",
    [
        {},
        {
            "calibration": {},
            "next": {
                "primary": None,
                "alternate": None,
            },
            "previous": {
                "primary": None,
                "alternate": None,
            },
        },
        {
            "calibration": {
                "primary": {
                    "trigger": "F1",
                    "modifiers": ["CTRL"],
                },
                "alternate": None,
            },
            "next": {
                "primary": None,
                "alternate": None,
            },
            "previous": {
                "primary": None,
                "alternate": None,
            },
            "extra": {
                "primary": None,
                "alternate": None,
            },
        },
    ],
)
def test_set_shortcut_configuration_rejects_invalid_structure(
    configuration,
):
    message = {
        "type": COMMAND_SET_SHORTCUT_CONFIGURATION,
        "configuration": configuration,
    }

    assert_protocol_error(
        lambda: encode_command(message),
        ERROR_INVALID_ARGUMENT,
    )


@pytest.mark.parametrize(
    "shortcut",
    [
        {},
        {"trigger": "F1"},
        {"modifiers": ["CTRL"]},
        {"trigger": "", "modifiers": []},
        {"trigger": "F1", "modifiers": "CTRL"},
        {"trigger": "F1", "modifiers": [1]},
        {"trigger": "F1", "modifiers": ["CTRL", "CTRL"]},
    ],
)
def test_set_shortcut_configuration_rejects_invalid_shortcut(
    shortcut,
):
    message = {
        "type": COMMAND_SET_SHORTCUT_CONFIGURATION,
        "configuration": {
            "calibration": {
                "primary": shortcut,
                "alternate": None,
            },
            "next": {
                "primary": None,
                "alternate": None,
            },
            "previous": {
                "primary": None,
                "alternate": None,
            },
        },
    }

    assert_protocol_error(
        lambda: encode_command(message),
        ERROR_INVALID_ARGUMENT,
    )


def test_valid_shortcut_event():
    message = {
        "type": EVENT_SHORTCUT,
        "action": "next",
    }

    assert decode_event(encode_event(message)) == message
