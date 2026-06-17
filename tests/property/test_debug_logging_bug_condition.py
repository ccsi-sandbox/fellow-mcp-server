"""Property-based tests for DEBUG logging gap bug condition.

# Feature: debug-logging-enhancement, Property 1: Bug Condition - DEBUG Logging Gap

GOAL: Surface counterexamples that demonstrate no DEBUG log entries are emitted
despite LOG_LEVEL=DEBUG being configured.

These tests encode the EXPECTED behavior after the fix. They are expected to FAIL
on unfixed code because logger.debug() calls do not exist yet.

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4**
"""

import json
import time
from unittest.mock import patch, MagicMock

import pytest
import structlog
import structlog.testing
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from app.client.rate_limiter import TokenBucketRateLimiter
from app.client.fellow_api import FellowApiClient
from app.config import AppConfig


# --- Strategies ---

# JSON-RPC methods that the MCP server handles
jsonrpc_methods = st.sampled_from([
    "tools/call",
    "tools/list",
    "initialize",
    "notifications/initialized",
])

# Tool names from the registry
tool_names = st.sampled_from([
    "list_action_items",
    "get_action_item",
    "complete_action_item",
    "archive_action_item",
    "list_notes",
    "get_note",
    "delete_note",
    "list_recordings",
    "get_recording",
    "delete_recording",
    "list_webhooks",
    "get_webhook",
    "create_webhook",
    "update_webhook",
    "delete_webhook",
    "get_current_user",
])

# Random params for JSON-RPC requests
jsonrpc_params = st.one_of(
    st.just({}),
    st.fixed_dictionaries({
        "name": tool_names,
        "arguments": st.just({}),
    }),
    st.dictionaries(
        st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("L", "N"))),
        st.text(min_size=0, max_size=20),
        max_size=3,
    ),
)

# HTTP methods for Fellow API requests
http_methods = st.sampled_from(["GET", "POST", "PUT", "DELETE"])

# API paths
api_paths = st.sampled_from([
    "/api/v1/notes",
    "/api/v1/action-items",
    "/api/v1/recordings",
    "/api/v1/me",
    "/api/v1/webhooks",
])

# Random query params
query_params = st.one_of(
    st.none(),
    st.fixed_dictionaries({
        "limit": st.integers(min_value=1, max_value=100).map(str),
    }),
)

# Random JSON body keys
json_body = st.one_of(
    st.none(),
    st.dictionaries(
        st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("L",))),
        st.text(min_size=0, max_size=50),
        max_size=5,
    ),
)

# Token counts that force a wait (less than 1.0)
low_token_counts = st.floats(min_value=0.0, max_value=0.99, allow_nan=False, allow_infinity=False)


# --- Helpers ---

def make_test_config() -> AppConfig:
    """Create a test AppConfig with DEBUG log level."""
    return AppConfig(
        fellow_api_key="test-api-key-12345",
        fellow_subdomain="testworkspace",
        mcp_auth_enabled=False,
        mcp_auth_token=None,
        gunicorn_workers=2,
        log_level="DEBUG",
        mcp_endpoint_path="/mcp",
        fellow_base_url="https://testworkspace.fellow.app",
    )


# --- Property Tests ---


@pytest.mark.property
class TestDebugLoggingBugCondition:
    """Property 1: Bug Condition - DEBUG Logging Gap at Request Boundaries.

    These tests verify that DEBUG log entries are emitted at request boundaries
    when LOG_LEVEL=DEBUG. On unfixed code, these tests FAIL because no
    logger.debug() calls exist.

    **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4**
    """

    @given(method=jsonrpc_methods, params=jsonrpc_params)
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_mcp_request_received_debug_log_emitted(
        self, method: str, params: dict, app, client
    ):
        """When LOG_LEVEL=DEBUG and a JSON-RPC request is processed through
        mcp_endpoint, a DEBUG log with event 'mcp_request_received' containing
        method and params SHALL be emitted.

        **Validates: Requirements 1.1, 2.1**
        """
        # Build a valid JSON-RPC request
        jsonrpc_request = {
            "jsonrpc": "2.0",
            "method": method,
            "id": 1,
        }
        if method == "tools/call":
            jsonrpc_request["params"] = {
                "name": "get_current_user",
                "arguments": {},
            }
        else:
            jsonrpc_request["params"] = params

        with structlog.testing.capture_logs() as captured:
            client.post(
                "/mcp",
                data=json.dumps(jsonrpc_request),
                content_type="application/json",
            )

        # Assert that a DEBUG-level entry with event "mcp_request_received" was emitted
        debug_entries = [
            entry for entry in captured
            if entry.get("event") == "mcp_request_received"
            and entry.get("log_level") == "debug"
        ]

        assert len(debug_entries) >= 1, (
            f"Expected at least one DEBUG log entry with event 'mcp_request_received' "
            f"for method='{method}', but got zero. "
            f"Captured log events: {[e.get('event') for e in captured]}"
        )

        # Verify required fields
        entry = debug_entries[0]
        assert "method" in entry, (
            f"DEBUG entry 'mcp_request_received' missing 'method' field. Entry: {entry}"
        )

    @given(http_method=http_methods, path=api_paths, params=query_params, body=json_body)
    @settings(max_examples=50, deadline=None)
    def test_fellow_api_request_debug_log_emitted(
        self, http_method: str, path: str, params: dict | None, body: dict | None
    ):
        """When LOG_LEVEL=DEBUG and _do_request_with_retry executes an HTTP request,
        a DEBUG log with event 'fellow_api_request' containing http_method, url,
        params, and body_keys SHALL be emitted.

        **Validates: Requirements 1.2, 2.2**
        """
        config = make_test_config()

        # Mock the rate limiter to not actually wait
        mock_limiter = MagicMock()
        mock_limiter.acquire = MagicMock(return_value=None)

        api_client = FellowApiClient(config, rate_limiter=mock_limiter)

        # Mock the HTTP session to return a successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"result": "ok"}'
        mock_response.text = '{"result": "ok"}'
        mock_response.json.return_value = {"result": "ok"}
        mock_response.elapsed = MagicMock()
        mock_response.elapsed.total_seconds.return_value = 0.05

        with patch.object(api_client._session, "request", return_value=mock_response):
            with structlog.testing.capture_logs() as captured:
                api_client._do_request_with_retry(http_method, path, params=params, json_body=body)

        # Assert a DEBUG entry with event "fellow_api_request" was emitted
        request_entries = [
            entry for entry in captured
            if entry.get("event") == "fellow_api_request"
            and entry.get("log_level") == "debug"
        ]

        assert len(request_entries) >= 1, (
            f"Expected at least one DEBUG log entry with event 'fellow_api_request' "
            f"for {http_method} {path}, but got zero. "
            f"Captured log events: {[e.get('event') for e in captured]}"
        )

        # Verify required fields
        entry = request_entries[0]
        assert "http_method" in entry, f"Missing 'http_method' in fellow_api_request entry: {entry}"
        assert "url" in entry, f"Missing 'url' in fellow_api_request entry: {entry}"

    @given(http_method=http_methods, path=api_paths)
    @settings(max_examples=50, deadline=None)
    def test_fellow_api_response_debug_log_emitted(
        self, http_method: str, path: str
    ):
        """When LOG_LEVEL=DEBUG and the Fellow API returns a response,
        a DEBUG log with event 'fellow_api_response' containing status_code,
        truncated response_body, and elapsed_ms SHALL be emitted.

        **Validates: Requirements 1.3, 2.3**
        """
        config = make_test_config()

        # Mock the rate limiter
        mock_limiter = MagicMock()
        mock_limiter.acquire = MagicMock(return_value=None)

        api_client = FellowApiClient(config, rate_limiter=mock_limiter)

        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"data": "test response body"}'
        mock_response.text = '{"data": "test response body"}'
        mock_response.json.return_value = {"data": "test response body"}
        mock_response.elapsed = MagicMock()
        mock_response.elapsed.total_seconds.return_value = 0.123

        with patch.object(api_client._session, "request", return_value=mock_response):
            with structlog.testing.capture_logs() as captured:
                api_client._do_request_with_retry(http_method, path)

        # Assert a DEBUG entry with event "fellow_api_response" was emitted
        response_entries = [
            entry for entry in captured
            if entry.get("event") == "fellow_api_response"
            and entry.get("log_level") == "debug"
        ]

        assert len(response_entries) >= 1, (
            f"Expected at least one DEBUG log entry with event 'fellow_api_response' "
            f"for {http_method} {path}, but got zero. "
            f"Captured log events: {[e.get('event') for e in captured]}"
        )

        # Verify required fields
        entry = response_entries[0]
        assert "status_code" in entry, f"Missing 'status_code' in fellow_api_response entry: {entry}"
        assert "elapsed_ms" in entry, f"Missing 'elapsed_ms' in fellow_api_response entry: {entry}"
        assert "response_body" in entry, f"Missing 'response_body' in fellow_api_response entry: {entry}"

    @given(initial_tokens=low_token_counts)
    @settings(max_examples=50, deadline=None)
    def test_rate_limiter_wait_debug_log_emitted(self, initial_tokens: float):
        """When LOG_LEVEL=DEBUG and TokenBucketRateLimiter.acquire() must wait
        (tokens < 1.0), a DEBUG log with event 'rate_limiter_wait' containing
        tokens_available, wait_seconds, and max_tokens SHALL be emitted.

        **Validates: Requirements 1.4, 2.4**
        """
        limiter = TokenBucketRateLimiter(max_per_second=3.0)

        # Force the limiter into a low-token state
        with limiter._lock:
            limiter._tokens = initial_tokens
            limiter._last_refill = time.monotonic()

        with structlog.testing.capture_logs() as captured:
            # Patch time.sleep to avoid actual waiting
            with patch("time.sleep", return_value=None):
                limiter.acquire()

        # Assert a DEBUG entry with event "rate_limiter_wait" was emitted
        wait_entries = [
            entry for entry in captured
            if entry.get("event") == "rate_limiter_wait"
            and entry.get("log_level") == "debug"
        ]

        assert len(wait_entries) >= 1, (
            f"Expected at least one DEBUG log entry with event 'rate_limiter_wait' "
            f"when tokens={initial_tokens:.3f} < 1.0, but got zero. "
            f"Captured log events: {[e.get('event') for e in captured]}"
        )

        # Verify required fields
        entry = wait_entries[0]
        assert "tokens_available" in entry, f"Missing 'tokens_available' in rate_limiter_wait entry: {entry}"
        assert "wait_seconds" in entry, f"Missing 'wait_seconds' in rate_limiter_wait entry: {entry}"
        assert "max_tokens" in entry, f"Missing 'max_tokens' in rate_limiter_wait entry: {entry}"
