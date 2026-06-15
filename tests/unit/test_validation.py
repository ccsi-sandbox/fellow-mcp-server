"""Unit tests for the InputValidator class."""

import pytest

from app.validation.schemas import InputValidator


@pytest.fixture
def validator():
    """Create an InputValidator instance."""
    return InputValidator()


class TestUnknownTool:
    """Tests for unknown tool names."""

    @pytest.mark.unit
    def test_unknown_tool_returns_error(self, validator):
        errors = validator.validate("nonexistent_tool", {})
        assert len(errors) == 1
        assert "Unknown tool" in errors[0]


class TestGetCurrentUser:
    """Tests for get_current_user (no parameters)."""

    @pytest.mark.unit
    def test_valid_no_params(self, validator):
        errors = validator.validate("get_current_user", {})
        assert errors == []

    @pytest.mark.unit
    def test_ignores_unrecognized_params(self, validator):
        errors = validator.validate("get_current_user", {"foo": "bar", "baz": 123})
        assert errors == []


class TestRequiredParams:
    """Tests for required parameter validation."""

    @pytest.mark.unit
    def test_missing_required_id(self, validator):
        errors = validator.validate("get_action_item", {})
        assert len(errors) == 1
        assert "Missing required parameter: id" in errors[0]

    @pytest.mark.unit
    def test_missing_multiple_required(self, validator):
        errors = validator.validate("complete_action_item", {})
        assert len(errors) == 2
        assert any("id" in e for e in errors)
        assert any("completed" in e for e in errors)

    @pytest.mark.unit
    def test_missing_required_for_create_webhook(self, validator):
        errors = validator.validate("create_webhook", {})
        assert len(errors) == 2
        assert any("url" in e for e in errors)
        assert any("enabled_events" in e for e in errors)


class TestIdValidation:
    """Tests for ID parameter validation (1-255 chars)."""

    @pytest.mark.unit
    def test_valid_id(self, validator):
        errors = validator.validate("get_action_item", {"id": "abc123"})
        assert errors == []

    @pytest.mark.unit
    def test_empty_id(self, validator):
        errors = validator.validate("get_action_item", {"id": ""})
        assert len(errors) == 1
        assert "non-empty" in errors[0]

    @pytest.mark.unit
    def test_id_too_long(self, validator):
        errors = validator.validate("get_action_item", {"id": "x" * 256})
        assert len(errors) == 1
        assert "255 characters" in errors[0]

    @pytest.mark.unit
    def test_id_max_length_valid(self, validator):
        errors = validator.validate("get_action_item", {"id": "x" * 255})
        assert errors == []

    @pytest.mark.unit
    def test_id_non_string(self, validator):
        errors = validator.validate("get_action_item", {"id": 123})
        assert len(errors) == 1
        assert "must be a string" in errors[0]


class TestBoolValidation:
    """Tests for boolean parameter validation."""

    @pytest.mark.unit
    def test_valid_bool_true(self, validator):
        errors = validator.validate("list_action_items", {"completed": True})
        assert errors == []

    @pytest.mark.unit
    def test_valid_bool_false(self, validator):
        errors = validator.validate("list_action_items", {"archived": False})
        assert errors == []

    @pytest.mark.unit
    def test_invalid_bool_string(self, validator):
        errors = validator.validate("list_action_items", {"completed": "true"})
        assert len(errors) == 1
        assert "must be a boolean" in errors[0]

    @pytest.mark.unit
    def test_invalid_bool_int(self, validator):
        errors = validator.validate("list_action_items", {"completed": 1})
        assert len(errors) == 1
        assert "must be a boolean" in errors[0]


class TestIntValidation:
    """Tests for integer parameter validation (limit: 1-50)."""

    @pytest.mark.unit
    def test_valid_limit(self, validator):
        errors = validator.validate("list_webhooks", {"limit": 25})
        assert errors == []

    @pytest.mark.unit
    def test_limit_min(self, validator):
        errors = validator.validate("list_webhooks", {"limit": 1})
        assert errors == []

    @pytest.mark.unit
    def test_limit_max(self, validator):
        errors = validator.validate("list_webhooks", {"limit": 50})
        assert errors == []

    @pytest.mark.unit
    def test_limit_below_min(self, validator):
        errors = validator.validate("list_webhooks", {"limit": 0})
        assert len(errors) == 1
        assert "between 1 and 50" in errors[0]

    @pytest.mark.unit
    def test_limit_above_max(self, validator):
        errors = validator.validate("list_webhooks", {"limit": 51})
        assert len(errors) == 1
        assert "between 1 and 50" in errors[0]

    @pytest.mark.unit
    def test_limit_non_int(self, validator):
        errors = validator.validate("list_webhooks", {"limit": "10"})
        assert len(errors) == 1
        assert "must be an integer" in errors[0]

    @pytest.mark.unit
    def test_limit_bool_not_int(self, validator):
        """Booleans should not be accepted as integers."""
        errors = validator.validate("list_webhooks", {"limit": True})
        assert len(errors) == 1
        assert "must be an integer" in errors[0]


class TestDateValidation:
    """Tests for date parameter validation (YYYY-MM-DD)."""

    @pytest.mark.unit
    def test_valid_date(self, validator):
        errors = validator.validate("list_notes", {"created_at_start": "2024-01-15"})
        assert errors == []

    @pytest.mark.unit
    def test_invalid_date_format(self, validator):
        errors = validator.validate("list_notes", {"created_at_start": "01-15-2024"})
        assert len(errors) == 1
        assert "YYYY-MM-DD" in errors[0]

    @pytest.mark.unit
    def test_invalid_date_month(self, validator):
        errors = validator.validate("list_notes", {"created_at_start": "2024-13-01"})
        assert len(errors) == 1
        assert "YYYY-MM-DD" in errors[0]

    @pytest.mark.unit
    def test_invalid_date_day(self, validator):
        errors = validator.validate("list_notes", {"created_at_start": "2024-02-30"})
        assert len(errors) == 1
        assert "YYYY-MM-DD" in errors[0]

    @pytest.mark.unit
    def test_leap_year_valid(self, validator):
        errors = validator.validate("list_notes", {"created_at_start": "2024-02-29"})
        assert errors == []

    @pytest.mark.unit
    def test_non_leap_year_feb29(self, validator):
        errors = validator.validate("list_notes", {"created_at_start": "2023-02-29"})
        assert len(errors) == 1
        assert "YYYY-MM-DD" in errors[0]

    @pytest.mark.unit
    def test_date_non_string(self, validator):
        errors = validator.validate("list_notes", {"created_at_start": 20240115})
        assert len(errors) == 1
        assert "YYYY-MM-DD" in errors[0]


class TestEnumValidation:
    """Tests for enum parameter validation."""

    @pytest.mark.unit
    def test_valid_scope(self, validator):
        errors = validator.validate("list_action_items", {"scope": "assigned_to_me"})
        assert errors == []

    @pytest.mark.unit
    def test_invalid_scope(self, validator):
        errors = validator.validate("list_action_items", {"scope": "invalid"})
        assert len(errors) == 1
        assert "invalid value 'invalid'" in errors[0]
        assert "assigned_to_me" in errors[0]
        assert "assigned_to_others" in errors[0]
        assert "all" in errors[0]

    @pytest.mark.unit
    def test_valid_ordering(self, validator):
        errors = validator.validate(
            "list_action_items", {"ordering": "created_at_desc"}
        )
        assert errors == []

    @pytest.mark.unit
    def test_invalid_ordering(self, validator):
        errors = validator.validate("list_action_items", {"ordering": "alphabetical"})
        assert len(errors) == 1
        assert "allowed values" in errors[0]

    @pytest.mark.unit
    def test_valid_webhook_status(self, validator):
        errors = validator.validate(
            "create_webhook",
            {
                "url": "https://example.com",
                "enabled_events": ["ai_note.generated"],
                "status": "active",
            },
        )
        assert errors == []

    @pytest.mark.unit
    def test_invalid_webhook_status(self, validator):
        errors = validator.validate(
            "create_webhook",
            {
                "url": "https://example.com",
                "enabled_events": ["ai_note.generated"],
                "status": "paused",
            },
        )
        assert len(errors) == 1
        assert "allowed values" in errors[0]
        assert "active" in errors[0]
        assert "inactive" in errors[0]

    @pytest.mark.unit
    def test_enum_non_string(self, validator):
        errors = validator.validate("list_action_items", {"scope": 123})
        assert len(errors) == 1
        assert "must be a string" in errors[0]
        assert "allowed values" in errors[0]


class TestEnumListValidation:
    """Tests for enum list parameter validation."""

    @pytest.mark.unit
    def test_valid_note_includes(self, validator):
        errors = validator.validate(
            "list_notes", {"include": ["event_attendees", "content_markdown"]}
        )
        assert errors == []

    @pytest.mark.unit
    def test_invalid_note_include(self, validator):
        errors = validator.validate("list_notes", {"include": ["invalid_include"]})
        assert len(errors) == 1
        assert "invalid value 'invalid_include'" in errors[0]
        assert "event_attendees" in errors[0]
        assert "content_markdown" in errors[0]

    @pytest.mark.unit
    def test_valid_recording_includes(self, validator):
        errors = validator.validate(
            "list_recordings", {"include": ["transcript", "ai_notes"]}
        )
        assert errors == []

    @pytest.mark.unit
    def test_valid_enabled_events(self, validator):
        errors = validator.validate(
            "create_webhook",
            {
                "url": "https://example.com",
                "enabled_events": [
                    "ai_note.shared_to_channel",
                    "action_item.completed",
                ],
            },
        )
        assert errors == []

    @pytest.mark.unit
    def test_invalid_enabled_event(self, validator):
        errors = validator.validate(
            "create_webhook",
            {
                "url": "https://example.com",
                "enabled_events": ["ai_note.generated", "invalid.event"],
            },
        )
        assert len(errors) == 1
        assert "invalid value 'invalid.event'" in errors[0]

    @pytest.mark.unit
    def test_enum_list_not_a_list(self, validator):
        errors = validator.validate(
            "list_notes", {"include": "event_attendees"}
        )
        assert len(errors) == 1
        assert "must be a list" in errors[0]

    @pytest.mark.unit
    def test_enum_list_non_string_item(self, validator):
        errors = validator.validate("list_notes", {"include": [123]})
        assert len(errors) == 1
        assert "non-string value" in errors[0]


class TestUrlValidation:
    """Tests for URL parameter validation (1-2048 chars)."""

    @pytest.mark.unit
    def test_valid_url(self, validator):
        errors = validator.validate(
            "create_webhook",
            {
                "url": "https://example.com/webhook",
                "enabled_events": ["ai_note.generated"],
            },
        )
        assert errors == []

    @pytest.mark.unit
    def test_empty_url(self, validator):
        errors = validator.validate(
            "create_webhook",
            {"url": "", "enabled_events": ["ai_note.generated"]},
        )
        assert len(errors) == 1
        assert "non-empty" in errors[0]

    @pytest.mark.unit
    def test_url_too_long(self, validator):
        errors = validator.validate(
            "create_webhook",
            {"url": "x" * 2049, "enabled_events": ["ai_note.generated"]},
        )
        assert len(errors) == 1
        assert "2048 characters" in errors[0]

    @pytest.mark.unit
    def test_url_max_length_valid(self, validator):
        errors = validator.validate(
            "create_webhook",
            {"url": "x" * 2048, "enabled_events": ["ai_note.generated"]},
        )
        assert errors == []

    @pytest.mark.unit
    def test_url_non_string(self, validator):
        errors = validator.validate(
            "create_webhook",
            {"url": 123, "enabled_events": ["ai_note.generated"]},
        )
        assert len(errors) == 1
        assert "must be a string" in errors[0]


class TestMultipleErrors:
    """Tests for collecting ALL errors rather than failing on first."""

    @pytest.mark.unit
    def test_multiple_invalid_params(self, validator):
        """Multiple validation errors collected in one call."""
        errors = validator.validate(
            "list_action_items",
            {"completed": "not_bool", "scope": "invalid", "ordering": "wrong"},
        )
        assert len(errors) == 3

    @pytest.mark.unit
    def test_missing_and_invalid_combined(self, validator):
        """Missing required + invalid type reported together."""
        errors = validator.validate(
            "complete_action_item", {"id": "", "completed": "yes"}
        )
        # id is empty (1 error) + completed is not bool (1 error)
        assert len(errors) == 2

    @pytest.mark.unit
    def test_create_webhook_all_invalid(self, validator):
        """All parameters invalid for create_webhook."""
        errors = validator.validate(
            "create_webhook",
            {
                "url": "",
                "enabled_events": ["invalid.event"],
                "status": "unknown",
            },
        )
        # url empty (1) + invalid event (1) + invalid status (1) = 3
        assert len(errors) == 3


class TestIgnoreUnrecognized:
    """Tests for silently ignoring unrecognized parameters."""

    @pytest.mark.unit
    def test_unrecognized_params_ignored(self, validator):
        errors = validator.validate(
            "get_action_item", {"id": "valid-id", "unknown_param": "value"}
        )
        assert errors == []

    @pytest.mark.unit
    def test_only_unrecognized_no_errors(self, validator):
        errors = validator.validate(
            "list_action_items", {"foo": "bar", "baz": 42, "qux": [1, 2, 3]}
        )
        assert errors == []


class TestUpdateWebhook:
    """Tests for update_webhook tool validation."""

    @pytest.mark.unit
    def test_valid_update(self, validator):
        errors = validator.validate(
            "update_webhook",
            {"id": "webhook-123", "url": "https://new-url.com"},
        )
        assert errors == []

    @pytest.mark.unit
    def test_update_missing_id(self, validator):
        errors = validator.validate(
            "update_webhook", {"url": "https://example.com"}
        )
        assert len(errors) == 1
        assert "Missing required parameter: id" in errors[0]

    @pytest.mark.unit
    def test_update_all_optional_fields(self, validator):
        errors = validator.validate(
            "update_webhook",
            {
                "id": "wh-1",
                "url": "https://example.com",
                "enabled_events": ["ai_note.generated"],
                "description": "A webhook",
                "status": "inactive",
            },
        )
        assert errors == []


class TestGetRecording:
    """Tests for get_recording tool validation."""

    @pytest.mark.unit
    def test_valid_with_includes(self, validator):
        errors = validator.validate(
            "get_recording", {"id": "rec-123", "include": ["transcript", "media_url"]}
        )
        assert errors == []

    @pytest.mark.unit
    def test_invalid_include(self, validator):
        errors = validator.validate(
            "get_recording", {"id": "rec-123", "include": ["invalid"]}
        )
        assert len(errors) == 1
        assert "invalid value 'invalid'" in errors[0]


class TestListRecordings:
    """Tests for list_recordings tool validation."""

    @pytest.mark.unit
    def test_valid_filters(self, validator):
        errors = validator.validate(
            "list_recordings",
            {
                "event_guid": "ev-123",
                "created_at_start": "2024-01-01",
                "media_url": True,
                "include": ["ai_notes"],
            },
        )
        assert errors == []

    @pytest.mark.unit
    def test_invalid_date_and_include(self, validator):
        errors = validator.validate(
            "list_recordings",
            {"created_at_start": "not-a-date", "include": ["bad_value"]},
        )
        assert len(errors) == 2
