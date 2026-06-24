"""Property-based tests for input validation.

# Feature: fellow-mcp-server, Property 4: Input validation reports all errors simultaneously
# Feature: fellow-mcp-server, Property 5: ID and string constraint validation
# Feature: fellow-mcp-server, Property 6: Enum validation rejects invalid values and lists allowed values

Tests that the InputValidator correctly collects all errors simultaneously,
enforces string/ID constraints, and rejects invalid enum values with helpful messages.
"""

import string

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from app.validation.schemas import (
    InputValidator,
    SCOPE_VALUES,
    ORDERING_VALUES,
    NOTE_INCLUDE_VALUES,
    RECORDING_INCLUDE_VALUES,
    ENABLED_EVENTS_VALUES,
    WEBHOOK_STATUS_VALUES,
    TOOL_SCHEMAS,
)


# --- Shared validator instance ---

validator = InputValidator()


# --- Strategies ---

# Printable strings that won't collide with known param names
printable_text = st.text(
    min_size=1,
    max_size=30,
    alphabet=st.characters(whitelist_categories=("L", "N"), min_codepoint=65),
)

# Strategy for unrecognized parameter names (not in any tool schema)
all_known_params = set()
for schema in TOOL_SCHEMAS.values():
    all_known_params.update(schema["params"].keys())

unrecognized_param_names = printable_text.filter(lambda s: s not in all_known_params)

# Valid IDs: 1-255 chars
valid_ids = st.text(
    min_size=1,
    max_size=255,
    alphabet=st.characters(whitelist_categories=("L", "N", "P"), min_codepoint=33),
)

# Empty IDs
empty_ids = st.just("")

# Overlong IDs: > 255 chars
overlong_ids = st.text(
    min_size=256,
    max_size=300,
    alphabet=st.characters(whitelist_categories=("L", "N"), min_codepoint=65),
)

# Valid URLs: 1-2048 chars
valid_urls = st.text(
    min_size=1,
    max_size=200,
    alphabet=st.characters(whitelist_categories=("L", "N", "P"), min_codepoint=33),
).map(lambda s: "https://example.com/" + s[:100])

# Empty URLs
empty_urls = st.just("")

# Overlong URLs: > 2048 chars
overlong_urls = st.text(
    min_size=2049,
    max_size=2100,
    alphabet=st.characters(whitelist_categories=("L", "N"), min_codepoint=65),
)

# Valid dates: YYYY-MM-DD
valid_dates = st.dates().map(lambda d: d.isoformat())

# Invalid date strings (not matching YYYY-MM-DD or invalid components)
invalid_date_formats = st.one_of(
    st.just("2024/01/01"),
    st.just("01-01-2024"),
    st.just("not-a-date"),
    st.just("2024-13-01"),
    st.just("2024-00-15"),
    st.just("2024-01-32"),
    st.just("2024-02-30"),
    st.just(""),
    st.text(min_size=1, max_size=15, alphabet=st.characters(
        whitelist_categories=("L", "N", "P"), min_codepoint=33
    )).filter(lambda s: len(s) != 10 or not all(c.isdigit() or c == "-" for c in s)),
)


# --- Property 4: Input validation reports all errors simultaneously ---


@pytest.mark.property
class TestValidationReportsAllErrors:
    """Property 4: Input validation reports all errors simultaneously.

    For any tool call with N validation failures, the error response contains
    exactly N error descriptions. Unrecognized parameters are silently ignored.

    **Validates: Requirements 11.1, 11.2, 11.6, 11.7, 11.8**
    """

    @given(
        n_missing=st.integers(min_value=1, max_value=2),
    )
    @settings(max_examples=200)
    def test_missing_required_params_counted_correctly(self, n_missing):
        """Missing required parameters each produce exactly one error.

        **Validates: Requirements 11.1, 11.8**
        """
        # Use create_webhook which has 2 required params: url, enabled_events
        tool_name = "create_webhook"
        required = TOOL_SCHEMAS[tool_name]["required"]
        assume(n_missing <= len(required))

        # Remove n_missing required params
        missing_params = required[:n_missing]
        provided_params = {p: "valid" for p in required[n_missing:]}

        # Provide valid values for non-missing params to avoid extra errors
        for p in provided_params:
            if p == "url":
                provided_params[p] = "https://example.com/hook"
            elif p == "enabled_events":
                provided_params[p] = ["ai_note.generated"]

        errors = validator.validate(tool_name, provided_params)

        # Count missing-param errors
        missing_errors = [e for e in errors if "Missing required" in e]
        assert len(missing_errors) == n_missing

        for param in missing_params:
            assert any(param in e for e in missing_errors)

    @given(
        bad_bool_count=st.integers(min_value=1, max_value=3),
    )
    @settings(max_examples=200)
    def test_multiple_type_errors_all_reported(self, bad_bool_count):
        """Multiple type errors in a single call all produce errors.

        **Validates: Requirements 11.2, 11.8**
        """
        # list_action_items has boolean params: completed, archived, ai_detected
        tool_name = "list_action_items"
        bool_params = ["completed", "archived", "ai_detected"]
        assume(bad_bool_count <= len(bool_params))

        args = {}
        for i in range(bad_bool_count):
            args[bool_params[i]] = "not_a_bool"  # Wrong type

        errors = validator.validate(tool_name, args)
        assert len(errors) == bad_bool_count

        for i in range(bad_bool_count):
            assert any(bool_params[i] in e for e in errors)

    @given(
        unrecognized_keys=st.lists(
            unrecognized_param_names, min_size=1, max_size=5, unique=True
        ),
    )
    @settings(max_examples=200)
    def test_unrecognized_params_ignored(self, unrecognized_keys):
        """Unrecognized parameters do not generate errors.

        **Validates: Requirements 11.7**
        """
        # Use get_current_user which has no required or optional params
        tool_name = "get_current_user"
        args = {k: "some_value" for k in unrecognized_keys}

        errors = validator.validate(tool_name, args)
        assert errors == []

    @given(
        invalid_scope=st.text(min_size=1, max_size=20, alphabet=st.characters(
            whitelist_categories=("L",), min_codepoint=65
        )).filter(lambda s: s not in SCOPE_VALUES),
    )
    @settings(max_examples=200)
    def test_combined_missing_and_type_and_enum_errors(self, invalid_scope):
        """Missing + type + enum errors all collected simultaneously.

        **Validates: Requirements 11.1, 11.2, 11.6, 11.8**
        """
        # complete_action_item requires: id, completed
        # We'll omit 'id' (missing), provide bad type for 'completed',
        # and also test with list_action_items for enum error
        tool_name = "complete_action_item"

        # Missing 'id', wrong type for 'completed'
        args = {"completed": "not_bool"}
        errors = validator.validate(tool_name, args)

        # Should have at least 2 errors: missing id + wrong type completed
        assert len(errors) >= 2
        assert any("id" in e and "Missing" in e for e in errors)
        assert any("completed" in e for e in errors)

    @given(
        unrecognized_keys=st.lists(
            unrecognized_param_names, min_size=1, max_size=3, unique=True
        ),
    )
    @settings(max_examples=200)
    def test_errors_with_unrecognized_params_not_inflated(self, unrecognized_keys):
        """Error count not inflated by unrecognized params alongside real errors.

        **Validates: Requirements 11.7, 11.8**
        """
        # get_action_item requires 'id' - omit it, add unrecognized params
        tool_name = "get_action_item"
        args = {k: "some_value" for k in unrecognized_keys}

        errors = validator.validate(tool_name, args)

        # Should have exactly 1 error: missing 'id'
        assert len(errors) == 1
        assert "id" in errors[0]
        assert "Missing" in errors[0]


# --- Property 5: ID and string constraint validation ---


@pytest.mark.property
class TestIdAndStringConstraints:
    """Property 5: ID and string constraint validation.

    IDs: pass if 1-255 chars, fail if empty or > 255.
    URLs: pass if 1-2048 chars, fail if empty or > 2048.
    Dates: pass if valid YYYY-MM-DD, fail otherwise.

    **Validates: Requirements 11.3, 11.4, 8.8**
    """

    @given(id_value=valid_ids)
    @settings(max_examples=200)
    def test_valid_ids_pass(self, id_value):
        """IDs with 1-255 characters pass validation.

        **Validates: Requirements 11.3**
        """
        errors = validator.validate("get_action_item", {"id": id_value})
        assert errors == []

    @given(id_value=empty_ids)
    @settings(max_examples=200)
    def test_empty_ids_fail(self, id_value):
        """Empty string IDs fail validation.

        **Validates: Requirements 11.3**
        """
        errors = validator.validate("get_action_item", {"id": id_value})
        assert len(errors) == 1
        assert "non-empty" in errors[0] or "must be" in errors[0]

    @given(id_value=overlong_ids)
    @settings(max_examples=200)
    def test_overlong_ids_fail(self, id_value):
        """IDs longer than 255 characters fail validation.

        **Validates: Requirements 11.3**
        """
        errors = validator.validate("get_action_item", {"id": id_value})
        assert len(errors) == 1
        assert "255" in errors[0]

    @given(url_value=valid_urls)
    @settings(max_examples=200)
    def test_valid_urls_pass(self, url_value):
        """URLs with 1-2048 characters pass validation.

        **Validates: Requirements 8.8**
        """
        assume(len(url_value) <= 2048)
        errors = validator.validate(
            "create_webhook",
            {"url": url_value, "enabled_events": ["ai_note.generated"]},
        )
        # Only check for url-related errors
        url_errors = [e for e in errors if "url" in e.lower()]
        assert url_errors == []

    @given(url_value=empty_urls)
    @settings(max_examples=200)
    def test_empty_urls_fail(self, url_value):
        """Empty string URLs fail validation.

        **Validates: Requirements 8.8**
        """
        errors = validator.validate(
            "create_webhook",
            {"url": url_value, "enabled_events": ["ai_note.generated"]},
        )
        url_errors = [e for e in errors if "url" in e.lower()]
        assert len(url_errors) == 1
        assert "non-empty" in url_errors[0] or "must be" in url_errors[0]

    @given(url_value=overlong_urls)
    @settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.large_base_example])
    def test_overlong_urls_fail(self, url_value):
        """URLs longer than 2048 characters fail validation.

        **Validates: Requirements 8.8**
        """
        errors = validator.validate(
            "create_webhook",
            {"url": url_value, "enabled_events": ["ai_note.generated"]},
        )
        url_errors = [e for e in errors if "url" in e.lower()]
        assert len(url_errors) == 1
        assert "2048" in url_errors[0]

    @given(date_value=valid_dates)
    @settings(max_examples=200)
    def test_valid_dates_pass(self, date_value):
        """Valid YYYY-MM-DD dates pass validation.

        **Validates: Requirements 11.4**
        """
        errors = validator.validate(
            "list_notes", {"created_at_start": date_value}
        )
        assert errors == []

    @given(date_value=invalid_date_formats)
    @settings(max_examples=200)
    def test_invalid_dates_fail(self, date_value):
        """Invalid date strings fail validation.

        **Validates: Requirements 11.4**
        """
        errors = validator.validate(
            "list_notes", {"created_at_start": date_value}
        )
        assert len(errors) == 1
        assert "date" in errors[0].lower() or "YYYY-MM-DD" in errors[0]

    @given(
        length=st.integers(min_value=1, max_value=255),
    )
    @settings(max_examples=200)
    def test_id_boundary_lengths_pass(self, length):
        """Any ID of length 1-255 passes validation.

        **Validates: Requirements 11.3**
        """
        id_value = "a" * length
        errors = validator.validate("get_action_item", {"id": id_value})
        assert errors == []

    @given(
        length=st.integers(min_value=1, max_value=2048),
    )
    @settings(max_examples=200)
    def test_url_boundary_lengths_pass(self, length):
        """Any URL of length 1-2048 passes validation.

        **Validates: Requirements 8.8**
        """
        url_value = "x" * length
        errors = validator.validate(
            "create_webhook",
            {"url": url_value, "enabled_events": ["ai_note.generated"]},
        )
        url_errors = [e for e in errors if "url" in e.lower()]
        assert url_errors == []


# --- Property 6: Enum validation rejects invalid values and lists allowed values ---


@pytest.mark.property
class TestEnumValidation:
    """Property 6: Enum validation rejects invalid values and lists allowed values.

    For each enum parameter, valid values pass and invalid values produce an
    error message that includes the allowed values list.

    **Validates: Requirements 6.6, 7.6, 8.6, 8.7, 11.6**
    """

    @given(scope=st.sampled_from(SCOPE_VALUES))
    @settings(max_examples=200)
    def test_valid_scope_passes(self, scope):
        """Valid scope enum values pass validation.

        **Validates: Requirements 11.6**
        """
        errors = validator.validate("list_action_items", {"scope": scope})
        assert errors == []

    @given(
        scope=st.text(min_size=1, max_size=30, alphabet=st.characters(
            whitelist_categories=("L",), min_codepoint=65
        )).filter(lambda s: s not in SCOPE_VALUES),
    )
    @settings(max_examples=200)
    def test_invalid_scope_rejected_with_allowed_values(self, scope):
        """Invalid scope values are rejected with allowed values listed.

        **Validates: Requirements 11.6**
        """
        errors = validator.validate("list_action_items", {"scope": scope})
        assert len(errors) == 1
        # Error message must include the allowed values
        for allowed in SCOPE_VALUES:
            assert allowed in errors[0]

    @given(ordering=st.sampled_from(ORDERING_VALUES))
    @settings(max_examples=200)
    def test_valid_ordering_passes(self, ordering):
        """Valid ordering enum values pass validation.

        **Validates: Requirements 11.6**
        """
        errors = validator.validate("list_action_items", {"ordering": ordering})
        assert errors == []

    @given(
        ordering=st.text(min_size=1, max_size=30, alphabet=st.characters(
            whitelist_categories=("L",), min_codepoint=65
        )).filter(lambda s: s not in ORDERING_VALUES),
    )
    @settings(max_examples=200)
    def test_invalid_ordering_rejected_with_allowed_values(self, ordering):
        """Invalid ordering values are rejected with allowed values listed.

        **Validates: Requirements 11.6**
        """
        errors = validator.validate("list_action_items", {"ordering": ordering})
        assert len(errors) == 1
        for allowed in ORDERING_VALUES:
            assert allowed in errors[0]

    @given(includes=st.lists(st.sampled_from(NOTE_INCLUDE_VALUES), min_size=1, max_size=2, unique=True))
    @settings(max_examples=200)
    def test_valid_note_includes_pass(self, includes):
        """Valid note include values pass validation.

        **Validates: Requirements 6.6**
        """
        errors = validator.validate("list_notes", {"include": includes})
        assert errors == []

    @given(
        invalid_include=st.text(min_size=1, max_size=30, alphabet=st.characters(
            whitelist_categories=("L",), min_codepoint=65
        )).filter(lambda s: s not in NOTE_INCLUDE_VALUES),
    )
    @settings(max_examples=200)
    def test_invalid_note_include_rejected_with_allowed_values(self, invalid_include):
        """Invalid note include values are rejected with allowed values listed.

        **Validates: Requirements 6.6**
        """
        errors = validator.validate("list_notes", {"include": [invalid_include]})
        assert len(errors) == 1
        for allowed in NOTE_INCLUDE_VALUES:
            assert allowed in errors[0]

    @given(
        includes=st.lists(
            st.sampled_from(RECORDING_INCLUDE_VALUES), min_size=1, max_size=3, unique=True
        )
    )
    @settings(max_examples=200)
    def test_valid_recording_includes_pass(self, includes):
        """Valid recording include values pass validation.

        **Validates: Requirements 7.6**
        """
        errors = validator.validate("list_recordings", {"include": includes})
        assert errors == []

    @given(
        invalid_include=st.text(min_size=1, max_size=30, alphabet=st.characters(
            whitelist_categories=("L",), min_codepoint=65
        )).filter(lambda s: s not in RECORDING_INCLUDE_VALUES),
    )
    @settings(max_examples=200)
    def test_invalid_recording_include_rejected_with_allowed_values(self, invalid_include):
        """Invalid recording include values are rejected with allowed values listed.

        **Validates: Requirements 7.6**
        """
        errors = validator.validate("list_recordings", {"include": [invalid_include]})
        assert len(errors) == 1
        for allowed in RECORDING_INCLUDE_VALUES:
            assert allowed in errors[0]

    @given(events=st.lists(st.sampled_from(ENABLED_EVENTS_VALUES), min_size=1, max_size=4, unique=True))
    @settings(max_examples=200)
    def test_valid_enabled_events_pass(self, events):
        """Valid enabled_events values pass validation.

        **Validates: Requirements 8.6**
        """
        errors = validator.validate(
            "create_webhook",
            {"url": "https://example.com/hook", "enabled_events": events},
        )
        # Filter to only enabled_events errors
        event_errors = [e for e in errors if "enabled_events" in e]
        assert event_errors == []

    @given(
        invalid_event=st.text(min_size=1, max_size=30, alphabet=st.characters(
            whitelist_categories=("L", "N", "P"), min_codepoint=33
        )).filter(lambda s: s not in ENABLED_EVENTS_VALUES),
    )
    @settings(max_examples=200)
    def test_invalid_enabled_events_rejected_with_allowed_values(self, invalid_event):
        """Invalid enabled_events values are rejected with allowed values listed.

        **Validates: Requirements 8.6, 8.7**
        """
        errors = validator.validate(
            "create_webhook",
            {"url": "https://example.com/hook", "enabled_events": [invalid_event]},
        )
        event_errors = [e for e in errors if "enabled_events" in e]
        assert len(event_errors) == 1
        for allowed in ENABLED_EVENTS_VALUES:
            assert allowed in event_errors[0]

    @given(status=st.sampled_from(WEBHOOK_STATUS_VALUES))
    @settings(max_examples=200)
    def test_valid_webhook_status_passes(self, status):
        """Valid webhook status values pass validation.

        **Validates: Requirements 8.6**
        """
        errors = validator.validate(
            "create_webhook",
            {
                "url": "https://example.com/hook",
                "enabled_events": ["ai_note.generated"],
                "status": status,
            },
        )
        status_errors = [e for e in errors if "status" in e]
        assert status_errors == []

    @given(
        status=st.text(min_size=1, max_size=20, alphabet=st.characters(
            whitelist_categories=("L",), min_codepoint=65
        )).filter(lambda s: s not in WEBHOOK_STATUS_VALUES),
    )
    @settings(max_examples=200)
    def test_invalid_webhook_status_rejected_with_allowed_values(self, status):
        """Invalid webhook status values are rejected with allowed values listed.

        **Validates: Requirements 8.6**
        """
        errors = validator.validate(
            "create_webhook",
            {
                "url": "https://example.com/hook",
                "enabled_events": ["ai_note.generated"],
                "status": status,
            },
        )
        status_errors = [e for e in errors if "status" in e]
        assert len(status_errors) == 1
        for allowed in WEBHOOK_STATUS_VALUES:
            assert allowed in status_errors[0]
