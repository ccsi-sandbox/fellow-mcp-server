"""Integration tests for the MCP endpoint full request flow.

Tests the complete request lifecycle through the Flask test client,
mocking only the Fellow API at the HTTP level using the `responses` library.

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 3.4, 3.5
"""

import json
from unittest.mock import patch

import pytest
import responses

from app.config import AppConfig
from app.main import create_app


# --- Fixtures ---


@pytest.fixture
def base_config():
    """AppConfig with auth disabled for general endpoint tests."""
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


@pytest.fixture
def auth_config():
    """AppConfig with auth enabled."""
    return AppConfig(
        fellow_api_key="test-api-key-12345",
        fellow_subdomain="testworkspace",
        mcp_auth_enabled=True,
        mcp_auth_token="test-secure-token-1234567890",
        gunicorn_workers=2,
        log_level="DEBUG",
        mcp_endpoint_path="/mcp",
        fellow_base_url="https://testworkspace.fellow.app",
    )


@pytest.fixture
def app_no_auth(base_config):
    """Flask app with auth disabled."""
    return create_app(config={"TESTING": True, "APP_CONFIG": base_config})


@pytest.fixture
def app_with_auth(auth_config):
    """Flask app with auth enabled."""
    return create_app(config={"TESTING": True, "APP_CONFIG": auth_config})


@pytest.fixture
def client_no_auth(app_no_auth):
    """Test client with auth disabled."""
    return app_no_auth.test_client()


@pytest.fixture
def client_with_auth(app_with_auth):
    """Test client with auth enabled."""
    return app_with_auth.test_client()


def _jsonrpc_request(method, params=None, request_id=1):
    """Build a JSON-RPC 2.0 request payload."""
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
    }
    if params is not None:
        payload["params"] = params
    return payload


def _tools_call_request(tool_name, arguments=None, request_id=1):
    """Build a tools/call JSON-RPC request."""
    return _jsonrpc_request(
        "tools/call",
        params={"name": tool_name, "arguments": arguments or {}},
        request_id=request_id,
    )


# --- Test 1: Full lifecycle - tools/call with valid request ---


@pytest.mark.integration
@responses.activate
def test_full_lifecycle_tools_call_success(client_no_auth):
    """POST to /mcp with valid tools/call → success result.

    Validates: Requirements 1.1, 1.2, 1.5
    """
    # Mock the Fellow API response for get_current_user
    responses.add(
        responses.GET,
        "https://testworkspace.fellow.app/api/v1/me",
        json={
            "id": "user-123",
            "name": "Test User",
            "email": "test@example.com",
            "workspace_id": "ws-456",
            "workspace_name": "Test Workspace",
            "workspace_subdomain": "testworkspace",
        },
        status=200,
    )

    payload = _tools_call_request("get_current_user", {})
    resp = client_no_auth.post(
        "/mcp",
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 1
    assert body["result"]["isError"] is False
    # The tool result content should contain the user data
    content_text = body["result"]["content"][0]["text"]
    result_data = json.loads(content_text)
    assert result_data["id"] == "user-123"
    assert result_data["email"] == "test@example.com"


# --- Test 2: Full lifecycle - tools/list returns all 16 tools ---


@pytest.mark.integration
def test_full_lifecycle_tools_list(client_no_auth):
    """POST to /mcp with tools/list → all 16 tool definitions.

    Validates: Requirements 1.4
    """
    payload = _jsonrpc_request("tools/list")
    resp = client_no_auth.post(
        "/mcp",
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 1
    tools = body["result"]["tools"]
    assert len(tools) == 16

    # Verify all expected tools are present
    tool_names = {t["name"] for t in tools}
    expected_names = {
        "list_action_items", "get_action_item", "complete_action_item",
        "archive_action_item", "list_notes", "get_note", "delete_note",
        "list_recordings", "get_recording", "delete_recording",
        "list_webhooks", "get_webhook", "create_webhook",
        "update_webhook", "delete_webhook", "get_current_user",
    }
    assert tool_names == expected_names

    # Each tool should have name, description, and inputSchema
    for tool in tools:
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool


# --- Test 3: Auth enabled + invalid token → 401 ---


@pytest.mark.integration
def test_auth_invalid_token_returns_401(client_with_auth):
    """Auth enabled + invalid token → 401 before any tool execution.

    Validates: Requirement 2.1
    """
    payload = _jsonrpc_request("tools/list")
    resp = client_with_auth.post(
        "/mcp",
        data=json.dumps(payload),
        content_type="application/json",
        headers={"X-MCP-AUTH-TOKEN": "wrong-token-value"},
    )

    assert resp.status_code == 401
    body = resp.get_json()
    assert "error" in body
    assert "Invalid" in body["error"] or "authentication" in body["error"].lower()


# --- Test 4: Auth enabled + valid token → request proceeds ---


@pytest.mark.integration
def test_auth_valid_token_proceeds(client_with_auth):
    """Auth enabled + valid token → request proceeds normally.

    Validates: Requirement 2.1
    """
    payload = _jsonrpc_request("tools/list")
    resp = client_with_auth.post(
        "/mcp",
        data=json.dumps(payload),
        content_type="application/json",
        headers={"X-MCP-AUTH-TOKEN": "test-secure-token-1234567890"},
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert "result" in body
    assert "tools" in body["result"]


# --- Test 5: Malformed JSON body → JSON-RPC error -32700 ---


@pytest.mark.integration
def test_malformed_json_returns_parse_error(client_no_auth):
    """Malformed JSON body → JSON-RPC error with code -32700.

    Validates: Requirement 1.3
    """
    resp = client_no_auth.post(
        "/mcp",
        data="this is {not valid json",
        content_type="application/json",
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] is None
    assert body["error"]["code"] == -32700
    assert "Parse error" in body["error"]["message"] or "JSON" in body["error"]["message"]


# --- Test 6: Missing JSON-RPC fields → -32600 ---


@pytest.mark.integration
def test_missing_jsonrpc_fields_returns_invalid_request(client_no_auth):
    """Missing JSON-RPC fields → JSON-RPC error with code -32600.

    Validates: Requirement 1.3
    """
    # Missing 'method' field
    payload = {"jsonrpc": "2.0", "id": 1}
    resp = client_no_auth.post(
        "/mcp",
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["jsonrpc"] == "2.0"
    assert body["error"]["code"] == -32600
    assert "method" in body["error"]["message"].lower()


# --- Test 7: Unknown method → -32601 ---


@pytest.mark.integration
def test_unknown_method_returns_method_not_found(client_no_auth):
    """Unknown method → JSON-RPC error with code -32601.

    Validates: Requirement 1.3
    """
    payload = _jsonrpc_request("unknown/method")
    resp = client_no_auth.post(
        "/mcp",
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 1
    assert body["error"]["code"] == -32601
    assert "not found" in body["error"]["message"].lower()


# --- Test 8: Unknown tool name → -32602 ---


@pytest.mark.integration
def test_unknown_tool_returns_invalid_params(client_no_auth):
    """Unknown tool name in tools/call → JSON-RPC error with code -32602.

    Validates: Requirement 1.6
    """
    payload = _tools_call_request("nonexistent_tool", {})
    resp = client_no_auth.post(
        "/mcp",
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 1
    assert body["error"]["code"] == -32602
    assert "nonexistent_tool" in body["error"]["message"]


# --- Test 9: Validation errors → tool result with isError=true ---


@pytest.mark.integration
def test_validation_error_returns_all_errors(client_no_auth):
    """Validation errors → tool result with isError=true, all errors listed.

    Validates: Requirements 1.5, 11.1, 11.8
    """
    # complete_action_item requires 'id' and 'completed'
    payload = _tools_call_request("complete_action_item", {})
    resp = client_no_auth.post(
        "/mcp",
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 1
    assert body["result"]["isError"] is True
    # Error text should mention both missing params
    error_text = body["result"]["content"][0]["text"]
    assert "id" in error_text
    assert "completed" in error_text


# --- Test 10: Fellow API error propagation ---


@pytest.mark.integration
@responses.activate
def test_fellow_api_error_propagation(client_no_auth):
    """Fellow API error propagation → tool result with isError=true containing status code.

    Validates: Requirement 4.8
    """
    # Mock the Fellow API to return a 403 error (non-transient, no retry)
    responses.add(
        responses.GET,
        "https://testworkspace.fellow.app/api/v1/action_item/item-123",
        json={"error": "Forbidden"},
        status=403,
    )

    payload = _tools_call_request("get_action_item", {"id": "item-123"})
    resp = client_no_auth.post(
        "/mcp",
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["jsonrpc"] == "2.0"
    assert body["result"]["isError"] is True
    error_text = body["result"]["content"][0]["text"]
    assert "403" in error_text


# --- Test 11: /health with reachable Fellow API ---


@pytest.mark.integration
@responses.activate
def test_health_endpoint_fellow_reachable(client_no_auth):
    """/health with reachable Fellow API → status healthy, fellow_api reachable.

    Validates: Requirement 3.4
    """
    responses.add(
        responses.GET,
        "https://testworkspace.fellow.app/api/v1/me",
        json={"id": "user-1"},
        status=200,
    )

    resp = client_no_auth.get("/health")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "healthy"
    assert body["fellow_api"] == "reachable"


# --- Test 12: /health with unreachable Fellow API ---


@pytest.mark.integration
@responses.activate
def test_health_endpoint_fellow_unreachable(client_no_auth):
    """/health with unreachable Fellow API → status healthy, fellow_api unreachable.

    Validates: Requirements 3.4, 3.5
    """
    responses.add(
        responses.GET,
        "https://testworkspace.fellow.app/api/v1/me",
        body=ConnectionError("Connection refused"),
    )

    resp = client_no_auth.get("/health")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "healthy"
    assert body["fellow_api"] == "unreachable"


# --- Test: Auth missing header → 401 ---


@pytest.mark.integration
def test_auth_missing_header_returns_401(client_with_auth):
    """Auth enabled + missing header → 401.

    Validates: Requirement 2.1
    """
    payload = _jsonrpc_request("tools/list")
    resp = client_with_auth.post(
        "/mcp",
        data=json.dumps(payload),
        content_type="application/json",
        # No X-MCP-AUTH-TOKEN header
    )

    assert resp.status_code == 401
    body = resp.get_json()
    assert "error" in body
    assert "Missing" in body["error"] or "header" in body["error"].lower()
