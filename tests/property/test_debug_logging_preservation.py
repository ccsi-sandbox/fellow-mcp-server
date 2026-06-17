"""Property-based tests for preservation of existing logging behavior.

# Feature: debug-logging-enhancement, Property 2: Preservation
# No DEBUG Output at INFO Level and Existing Log Format Unchanged

These tests capture existing behavior BEFORE implementing the DEBUG logging fix.
They must PASS on the unfixed code, confirming that:
- At LOG_LEVEL=INFO or higher, zero DEBUG entries appear
- Existing tool_call INFO entry contains expected fields
- request_id correlation is present in all log entries
- /health endpoint returns correct JSON regardless of LOG_LEVEL

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8**
"""

import json
import logging
from unittest.mock import patch

import pytest
import responses
import structlog
from flask import Flask
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.config import AppConfig
from app.logging.setup import bind_request_id, configure_logging
from app.main import create_app


# --- Helpers ---


def _make_config(log_level: str) -> AppConfig:
    """Create a test AppConfig with the specified log_level."""
    return AppConfig(
        fellow_api_key="test-api-key-12345",
        fellow_subdomain="testworkspace",
        mcp_auth_enabled=False,
        mcp_auth_token=None,
        gunicorn_workers=2,
        log_level=log_level,
        mcp_endpoint_path="/mcp",
        fellow_base_url="https://testworkspace.fellow.app",
    )


def _create_app_with_level(log_level: str) -> Flask:
    """Create a Flask app configured with the given log_level."""
    config = _make_config(log_level)
    app = create_app(config={"TESTING": True, "APP_CONFIG": config})
    return app


def _capture_logs(func):
    """Execute func while capturing structured log records. Returns list of parsed log dicts."""
    captured = []
    handler = logging.Handler()
    handler.emit = lambda record: captured.append(record)
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    try:
        func()
    finally:
        root_logger.removeHandler(handler)

    parsed = []
    for record in captured:
        try:
            msg = record.getMessage()
            entry = json.loads(msg)
            parsed.append(entry)
        except (json.JSONDecodeError, ValueError):
            continue
    return parsed


def _build_tools_call_request(tool_name: str, arguments: dict) -> bytes:
    """Build a JSON-RPC tools/call request body."""
    return json.dumps({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
        "id": 1,
    }).encode()


# --- Strategies ---

# Log levels above DEBUG (where no DEBUG entries should appear)
non_debug_log_levels = st.sampled_from(["INFO", "WARNING", "ERROR", "CRITICAL"])

# Valid JSON-RPC methods the server handles
jsonrpc_methods = st.sampled_from([
    "tools/list",
    "initialize",
    "notifications/initialized",
])

# Tool names that exist in the registry
valid_tool_names = st.sampled_from([
    "list_action_items",
    "get_action_item",
    "list_notes",
    "get_note",
    "list_recordings",
    "get_recording",
    "list_webhooks",
    "get_webhook",
    "get_current_user",
])

# Random Fellow API response bodies of varying lengths
response_body_texts = st.text(
    min_size=0,
    max_size=2000,
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S", "Z"),
        blacklist_characters=("\x00",),
        max_codepoint=127,
    ),
)


# --- Property Tests ---


@pytest.mark.property
class TestNoDebugAtHigherLevels:
    """Property 2: For all LOG_LEVEL in {INFO, WARNING, ERROR, CRITICAL} and
    for all valid JSON-RPC requests, zero DEBUG-level entries appear in captured logs.

    **Validates: Requirements 3.1, 3.2, 3.3, 3.4**
    """

    @given(
        log_level=non_debug_log_levels,
        method=jsonrpc_methods,
    )
    @settings(max_examples=50, deadline=None)
    def test_no_debug_entries_for_non_debug_methods(self, log_level, method):
        """For any LOG_LEVEL above DEBUG and any JSON-RPC method, zero DEBUG
        entries appear in captured logs.

        **Validates: Requirements 3.1, 3.2**
        """
        app = _create_app_with_level(log_level)

        request_body = json.dumps({
            "jsonrpc": "2.0",
            "method": method,
            "params": {},
            "id": 1,
        }).encode()

        def do_request():
            with app.test_client() as client:
                client.post(
                    "/mcp",
                    data=request_body,
                    content_type="application/json",
                )

        entries = _capture_logs(do_request)

        # Assert zero DEBUG-level entries
        debug_entries = [e for e in entries if e.get("level") == "debug"]
        assert len(debug_entries) == 0, (
            f"At LOG_LEVEL={log_level}, found {len(debug_entries)} DEBUG entries: "
            f"{debug_entries}"
        )

    @responses.activate
    @given(
        log_level=non_debug_log_levels,
        tool_name=valid_tool_names,
    )
    @settings(max_examples=50, deadline=None)
    def test_no_debug_entries_for_tools_call(self, log_level, tool_name):
        """For any LOG_LEVEL above DEBUG and any tools/call request, zero DEBUG
        entries appear in captured logs.

        **Validates: Requirements 3.1, 3.2**
        """
        responses.reset()
        app = _create_app_with_level(log_level)

        # Mock Fellow API response for any request the tool handler might make
        responses.add(
            responses.GET,
            "https://testworkspace.fellow.app/api/v1/me",
            json={"id": "user-1", "name": "Test"},
            status=200,
        )

        # Use a simple tool that requires minimal params
        request_body = _build_tools_call_request(tool_name, {})

        def do_request():
            with app.test_client() as client:
                client.post(
                    "/mcp",
                    data=request_body,
                    content_type="application/json",
                )

        entries = _capture_logs(do_request)

        # Assert zero DEBUG-level entries
        debug_entries = [e for e in entries if e.get("level") == "debug"]
        assert len(debug_entries) == 0, (
            f"At LOG_LEVEL={log_level}, tool={tool_name}, found {len(debug_entries)} "
            f"DEBUG entries: {debug_entries}"
        )


@pytest.mark.property
class TestToolCallInfoEntryFormat:
    """Property 2: For all valid tools/call requests at INFO level, the tool_call
    INFO entry contains exactly the fields (tool, duration_ms, outcome) with
    request_id bound.

    **Validates: Requirements 3.1, 3.3, 3.4**
    """

    @responses.activate
    @given(tool_name=valid_tool_names)
    @settings(max_examples=50, deadline=None)
    def test_tool_call_info_entry_has_required_fields(self, tool_name):
        """For any valid tools/call request at INFO level, the tool_call INFO entry
        contains exactly fields: tool, duration_ms, outcome, and request_id is bound.

        **Validates: Requirements 3.1, 3.3, 3.4**
        """
        responses.reset()
        app = _create_app_with_level("INFO")

        # Mock Fellow API for tools that call it
        responses.add(
            responses.GET,
            "https://testworkspace.fellow.app/api/v1/me",
            json={"id": "user-1", "name": "Test"},
            status=200,
        )
        # Mock various endpoints tools might call
        responses.add(
            responses.GET,
            "https://testworkspace.fellow.app/api/v1/action-items",
            json={"results": [], "next": None},
            status=200,
        )
        responses.add(
            responses.GET,
            "https://testworkspace.fellow.app/api/v1/notes",
            json={"results": [], "next": None},
            status=200,
        )
        responses.add(
            responses.GET,
            "https://testworkspace.fellow.app/api/v1/recordings",
            json={"results": [], "next": None},
            status=200,
        )
        responses.add(
            responses.GET,
            "https://testworkspace.fellow.app/api/v1/webhooks",
            json={"results": [], "next": None},
            status=200,
        )
        # Catch-all for any other path
        responses.add(
            responses.GET,
            url="https://testworkspace.fellow.app/api/v1/action-items/1",
            json={"id": 1, "title": "Test"},
            status=200,
        )
        responses.add(
            responses.GET,
            url="https://testworkspace.fellow.app/api/v1/notes/1",
            json={"id": 1, "title": "Test"},
            status=200,
        )
        responses.add(
            responses.GET,
            url="https://testworkspace.fellow.app/api/v1/recordings/1",
            json={"id": 1, "title": "Test"},
            status=200,
        )
        responses.add(
            responses.GET,
            url="https://testworkspace.fellow.app/api/v1/webhooks/1",
            json={"id": 1, "url": "https://example.com"},
            status=200,
        )

        request_body = _build_tools_call_request(tool_name, {})

        def do_request():
            with app.test_client() as client:
                client.post(
                    "/mcp",
                    data=request_body,
                    content_type="application/json",
                )

        entries = _capture_logs(do_request)

        # Find the tool_call INFO entry
        tool_call_entries = [
            e for e in entries
            if e.get("event") == "tool_call" and e.get("level") == "info"
        ]

        assert len(tool_call_entries) >= 1, (
            f"Expected at least 1 tool_call INFO entry for tool={tool_name}, "
            f"found {len(tool_call_entries)}. All entries: {entries}"
        )

        entry = tool_call_entries[0]

        # Verify required fields are present
        assert "tool" in entry, f"tool_call entry missing 'tool' field: {entry}"
        assert "duration_ms" in entry, f"tool_call entry missing 'duration_ms' field: {entry}"
        assert "outcome" in entry, f"tool_call entry missing 'outcome' field: {entry}"
        assert "request_id" in entry, f"tool_call entry missing 'request_id' field: {entry}"

        # Verify tool field matches the requested tool
        assert entry["tool"] == tool_name, (
            f"Expected tool={tool_name}, got tool={entry['tool']}"
        )

        # Verify duration_ms is a number
        assert isinstance(entry["duration_ms"], (int, float)), (
            f"duration_ms should be numeric, got {type(entry['duration_ms'])}"
        )

        # Verify outcome is a string
        assert isinstance(entry["outcome"], str), (
            f"outcome should be a string, got {type(entry['outcome'])}"
        )


@pytest.mark.property
class TestNoDebugForFellowApiResponses:
    """Property 2: For random Fellow API response bodies of varying lengths,
    verify current behavior produces no DEBUG output (baseline for truncation preservation).

    **Validates: Requirements 3.1, 3.2, 3.3**
    """

    @responses.activate
    @given(response_body=response_body_texts)
    @settings(max_examples=50, deadline=None)
    def test_no_debug_output_for_varying_response_bodies(self, response_body):
        """For random Fellow API response bodies of varying lengths, verify
        current behavior produces no DEBUG output.

        **Validates: Requirements 3.1, 3.2, 3.3**
        """
        responses.reset()
        app = _create_app_with_level("INFO")

        # Mock Fellow API with the random response body
        # Use get_current_user tool which calls /api/v1/me
        responses.add(
            responses.GET,
            "https://testworkspace.fellow.app/api/v1/me",
            json={"id": "user-1", "name": "Test", "extra": response_body},
            status=200,
        )

        request_body = _build_tools_call_request("get_current_user", {})

        def do_request():
            with app.test_client() as client:
                client.post(
                    "/mcp",
                    data=request_body,
                    content_type="application/json",
                )

        entries = _capture_logs(do_request)

        # Assert zero DEBUG-level entries regardless of response body length
        debug_entries = [e for e in entries if e.get("level") == "debug"]
        assert len(debug_entries) == 0, (
            f"Found {len(debug_entries)} DEBUG entries for response body "
            f"of length {len(response_body)}: {debug_entries}"
        )


@pytest.mark.property
class TestHealthEndpointPreservation:
    """Preservation: /health endpoint returns 200 with correct JSON regardless of LOG_LEVEL.

    **Validates: Requirements 3.5, 3.6, 3.7, 3.8**
    """

    @responses.activate
    @given(log_level=st.sampled_from(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]))
    @settings(max_examples=20, deadline=None)
    def test_health_endpoint_returns_correct_json(self, log_level):
        """/health endpoint returns 200 with {"status": "healthy", "fellow_api": "..."}
        regardless of LOG_LEVEL setting.

        **Validates: Requirements 3.5, 3.6, 3.7, 3.8**
        """
        responses.reset()
        app = _create_app_with_level(log_level)

        # Mock the health check API call
        responses.add(
            responses.GET,
            "https://testworkspace.fellow.app/api/v1/me",
            json={"id": "user-1"},
            status=200,
        )

        with app.test_client() as client:
            resp = client.get("/health")

        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code} at LOG_LEVEL={log_level}"
        )

        data = json.loads(resp.data)
        assert "status" in data, f"Missing 'status' key in health response: {data}"
        assert data["status"] == "healthy", (
            f"Expected status='healthy', got '{data['status']}'"
        )
        assert "fellow_api" in data, f"Missing 'fellow_api' key in health response: {data}"
        # fellow_api should be either "reachable" or "unreachable"
        assert data["fellow_api"] in ("reachable", "unreachable"), (
            f"Unexpected fellow_api value: {data['fellow_api']}"
        )


@pytest.mark.property
class TestRequestIdPreservation:
    """Preservation: request_id correlation field is present in all log entries
    regardless of level.

    **Validates: Requirements 3.4, 3.8**
    """

    @responses.activate
    @given(
        log_level=st.sampled_from(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    )
    @settings(max_examples=20, deadline=None)
    def test_request_id_present_in_all_entries(self, log_level):
        """request_id correlation field is present in all log entries
        emitted during a request, regardless of LOG_LEVEL.

        **Validates: Requirements 3.4, 3.8**
        """
        responses.reset()
        app = _create_app_with_level(log_level)

        # Mock Fellow API
        responses.add(
            responses.GET,
            "https://testworkspace.fellow.app/api/v1/me",
            json={"id": "user-1", "name": "Test"},
            status=200,
        )

        # Use a tools/call that generates a tool_call log entry at INFO level
        request_body = _build_tools_call_request("get_current_user", {})

        def do_request():
            with app.test_client() as client:
                client.post(
                    "/mcp",
                    data=request_body,
                    content_type="application/json",
                )

        entries = _capture_logs(do_request)

        # Filter entries that have an event field (actual log entries from our app)
        app_entries = [e for e in entries if "event" in e]

        # All app log entries should have request_id
        for entry in app_entries:
            assert "request_id" in entry, (
                f"Log entry missing request_id at LOG_LEVEL={log_level}: {entry}"
            )
