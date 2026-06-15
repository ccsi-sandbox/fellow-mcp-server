"""Input validation for MCP tool call arguments.

Validates tool call parameters against defined schemas, collecting ALL
validation errors before returning rather than failing on the first issue.
Unrecognized parameters are silently ignored.
"""

import re
from typing import Any


# --- Enum allowed values ---

SCOPE_VALUES = ["assigned_to_me", "assigned_to_others", "all"]
ORDERING_VALUES = ["created_at_desc", "created_at_asc", "due_date"]
NOTE_INCLUDE_VALUES = ["event_attendees", "content_markdown"]
RECORDING_INCLUDE_VALUES = ["transcript", "ai_notes", "media_url"]
ENABLED_EVENTS_VALUES = [
    "ai_note.shared_to_channel",
    "ai_note.generated",
    "action_item.assigned",
    "action_item.completed",
]
WEBHOOK_STATUS_VALUES = ["active", "inactive"]

# ISO 8601 date pattern: YYYY-MM-DD
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _is_valid_date(value: str) -> bool:
    """Check if a string is a valid ISO 8601 date (YYYY-MM-DD).

    Validates both the format and the date component ranges.
    """
    if not _DATE_PATTERN.match(value):
        return False
    try:
        year, month, day = value.split("-")
        year_int = int(year)
        month_int = int(month)
        day_int = int(day)
        if month_int < 1 or month_int > 12:
            return False
        if day_int < 1 or day_int > 31:
            return False
        # Basic month-day validation
        if month_int in (4, 6, 9, 11) and day_int > 30:
            return False
        if month_int == 2:
            is_leap = (year_int % 4 == 0 and year_int % 100 != 0) or (
                year_int % 400 == 0
            )
            if day_int > (29 if is_leap else 28):
                return False
        return True
    except (ValueError, IndexError):
        return False


# --- Tool parameter definitions ---

# Each tool schema defines:
#   "required": list of required parameter names
#   "params": dict of param_name -> param_spec
#
# param_spec keys:
#   "type": "string" | "bool" | "int" | "enum" | "enum_list" | "id" | "date" | "url"
#   "enum_values": list (for enum and enum_list types)
#   "min": int (for int type)
#   "max": int (for int type)
#   "max_length": int (for string/id/url types)

TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "list_action_items": {
        "required": [],
        "params": {
            "completed": {"type": "bool"},
            "archived": {"type": "bool"},
            "ai_detected": {"type": "bool"},
            "scope": {"type": "enum", "enum_values": SCOPE_VALUES},
            "ordering": {"type": "enum", "enum_values": ORDERING_VALUES},
        },
    },
    "get_action_item": {
        "required": ["id"],
        "params": {
            "id": {"type": "id"},
        },
    },
    "complete_action_item": {
        "required": ["id", "completed"],
        "params": {
            "id": {"type": "id"},
            "completed": {"type": "bool"},
        },
    },
    "archive_action_item": {
        "required": ["id"],
        "params": {
            "id": {"type": "id"},
        },
    },
    "list_notes": {
        "required": [],
        "params": {
            "event_guid": {"type": "string"},
            "created_at_start": {"type": "date"},
            "created_at_end": {"type": "date"},
            "updated_at_start": {"type": "date"},
            "updated_at_end": {"type": "date"},
            "channel_id": {"type": "string"},
            "title": {"type": "string"},
            "event_attendees": {"type": "string"},
            "include": {"type": "enum_list", "enum_values": NOTE_INCLUDE_VALUES},
        },
    },
    "get_note": {
        "required": ["id"],
        "params": {
            "id": {"type": "id"},
        },
    },
    "delete_note": {
        "required": ["id"],
        "params": {
            "id": {"type": "id"},
        },
    },
    "list_recordings": {
        "required": [],
        "params": {
            "event_guid": {"type": "string"},
            "created_at_start": {"type": "date"},
            "created_at_end": {"type": "date"},
            "updated_at_start": {"type": "date"},
            "updated_at_end": {"type": "date"},
            "channel_id": {"type": "string"},
            "title": {"type": "string"},
            "include": {"type": "enum_list", "enum_values": RECORDING_INCLUDE_VALUES},
            "media_url": {"type": "bool"},
        },
    },
    "get_recording": {
        "required": ["id"],
        "params": {
            "id": {"type": "id"},
            "include": {"type": "enum_list", "enum_values": RECORDING_INCLUDE_VALUES},
        },
    },
    "delete_recording": {
        "required": ["id"],
        "params": {
            "id": {"type": "id"},
        },
    },
    "list_webhooks": {
        "required": [],
        "params": {
            "limit": {"type": "int", "min": 1, "max": 50},
            "cursor": {"type": "string"},
        },
    },
    "get_webhook": {
        "required": ["id"],
        "params": {
            "id": {"type": "id"},
        },
    },
    "create_webhook": {
        "required": ["url", "enabled_events"],
        "params": {
            "url": {"type": "url"},
            "enabled_events": {
                "type": "enum_list",
                "enum_values": ENABLED_EVENTS_VALUES,
            },
            "description": {"type": "string"},
            "status": {"type": "enum", "enum_values": WEBHOOK_STATUS_VALUES},
        },
    },
    "update_webhook": {
        "required": ["id"],
        "params": {
            "id": {"type": "id"},
            "url": {"type": "url"},
            "enabled_events": {
                "type": "enum_list",
                "enum_values": ENABLED_EVENTS_VALUES,
            },
            "description": {"type": "string"},
            "status": {"type": "enum", "enum_values": WEBHOOK_STATUS_VALUES},
        },
    },
    "delete_webhook": {
        "required": ["id"],
        "params": {
            "id": {"type": "id"},
        },
    },
    "get_current_user": {
        "required": [],
        "params": {},
    },
}


class InputValidator:
    """Validates tool call arguments against defined schemas.

    Collects ALL validation errors rather than failing on the first.
    Ignores unrecognized parameters silently.
    """

    def validate(self, tool_name: str, arguments: dict[str, Any]) -> list[str]:
        """Validate arguments for a tool. Returns list of error messages (empty = valid).

        Collects ALL validation errors rather than failing on first.
        Ignores unrecognized parameters.

        Args:
            tool_name: The name of the MCP tool being called.
            arguments: The arguments dict provided by the caller.

        Returns:
            A list of validation error messages. Empty list means valid.
        """
        schema = TOOL_SCHEMAS.get(tool_name)
        if schema is None:
            return [f"Unknown tool: {tool_name}"]

        errors: list[str] = []

        # Check required parameters
        for param_name in schema["required"]:
            if param_name not in arguments:
                errors.append(f"Missing required parameter: {param_name}")

        # Validate each recognized parameter that is present
        for param_name, param_spec in schema["params"].items():
            if param_name not in arguments:
                continue
            value = arguments[param_name]
            param_errors = self._validate_param(param_name, value, param_spec)
            errors.extend(param_errors)

        return errors

    def _validate_param(
        self, name: str, value: Any, spec: dict[str, Any]
    ) -> list[str]:
        """Validate a single parameter against its spec.

        Returns a list of error messages for this parameter.
        """
        param_type = spec["type"]

        if param_type == "bool":
            return self._validate_bool(name, value)
        elif param_type == "int":
            return self._validate_int(name, value, spec.get("min"), spec.get("max"))
        elif param_type == "string":
            return self._validate_string(name, value)
        elif param_type == "id":
            return self._validate_id(name, value)
        elif param_type == "date":
            return self._validate_date(name, value)
        elif param_type == "url":
            return self._validate_url(name, value)
        elif param_type == "enum":
            return self._validate_enum(name, value, spec["enum_values"])
        elif param_type == "enum_list":
            return self._validate_enum_list(name, value, spec["enum_values"])
        else:
            return []

    def _validate_bool(self, name: str, value: Any) -> list[str]:
        """Validate a boolean parameter."""
        if not isinstance(value, bool):
            return [f"Parameter '{name}' must be a boolean"]
        return []

    def _validate_int(
        self, name: str, value: Any, min_val: int | None, max_val: int | None
    ) -> list[str]:
        """Validate an integer parameter with optional range."""
        if not isinstance(value, int) or isinstance(value, bool):
            return [f"Parameter '{name}' must be an integer"]
        errors: list[str] = []
        if min_val is not None and max_val is not None:
            if value < min_val or value > max_val:
                errors.append(
                    f"Parameter '{name}' must be between {min_val} and {max_val}"
                )
        return errors

    def _validate_string(self, name: str, value: Any) -> list[str]:
        """Validate a generic string parameter."""
        if not isinstance(value, str):
            return [f"Parameter '{name}' must be a string"]
        return []

    def _validate_id(self, name: str, value: Any) -> list[str]:
        """Validate an ID parameter (non-empty string, max 255 chars)."""
        if not isinstance(value, str):
            return [f"Parameter '{name}' must be a string"]
        errors: list[str] = []
        if len(value) == 0:
            errors.append(f"Parameter '{name}' must be non-empty")
        elif len(value) > 255:
            errors.append(
                f"Parameter '{name}' must be at most 255 characters"
            )
        return errors

    def _validate_date(self, name: str, value: Any) -> list[str]:
        """Validate a date parameter (ISO 8601 YYYY-MM-DD format)."""
        if not isinstance(value, str):
            return [f"Parameter '{name}' must be a string in YYYY-MM-DD format"]
        if not _is_valid_date(value):
            return [
                f"Parameter '{name}' must be a valid date in YYYY-MM-DD format"
            ]
        return []

    def _validate_url(self, name: str, value: Any) -> list[str]:
        """Validate a URL parameter (non-empty string, max 2048 chars)."""
        if not isinstance(value, str):
            return [f"Parameter '{name}' must be a string"]
        errors: list[str] = []
        if len(value) == 0:
            errors.append(f"Parameter '{name}' must be non-empty")
        elif len(value) > 2048:
            errors.append(
                f"Parameter '{name}' must be at most 2048 characters"
            )
        return errors

    def _validate_enum(
        self, name: str, value: Any, allowed: list[str]
    ) -> list[str]:
        """Validate an enum parameter (must be one of the allowed values)."""
        if not isinstance(value, str):
            return [
                f"Parameter '{name}' must be a string, "
                f"allowed values: {allowed}"
            ]
        if value not in allowed:
            return [
                f"Parameter '{name}' has invalid value '{value}', "
                f"allowed values: {allowed}"
            ]
        return []

    def _validate_enum_list(
        self, name: str, value: Any, allowed: list[str]
    ) -> list[str]:
        """Validate an enum list parameter (list of values from allowed set)."""
        if not isinstance(value, list):
            return [
                f"Parameter '{name}' must be a list, "
                f"allowed values: {allowed}"
            ]
        errors: list[str] = []
        for item in value:
            if not isinstance(item, str):
                errors.append(
                    f"Parameter '{name}' contains non-string value, "
                    f"allowed values: {allowed}"
                )
            elif item not in allowed:
                errors.append(
                    f"Parameter '{name}' has invalid value '{item}', "
                    f"allowed values: {allowed}"
                )
        return errors
