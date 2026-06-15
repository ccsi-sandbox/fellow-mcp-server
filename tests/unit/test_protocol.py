"""Unit tests for MCP JSON-RPC protocol parsing and message building."""

import json

import pytest

from app.mcp.errors import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    JsonRpcInvalidRequest,
    JsonRpcParseError,
)
from app.mcp.protocol import (
    build_jsonrpc_error,
    build_tool_result,
    build_tools_list_response,
    parse_jsonrpc_request,
)


class TestParseJsonrpcRequest:
    """Tests for parse_jsonrpc_request()."""

    def test_valid_tools_list_request(self):
        """A valid tools/list request parses successfully."""
        data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).encode()
        result = parse_jsonrpc_request(data)
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 1
        assert result["method"] == "tools/list"

    def test_valid_tools_call_request(self):
        """A valid tools/call request with params parses successfully."""
        data = json.dumps({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "get_current_user", "arguments": {}},
        }).encode()
        result = parse_jsonrpc_request(data)
        assert result["method"] == "tools/call"
        assert result["params"]["name"] == "get_current_user"
        assert result["params"]["arguments"] == {}

    def test_valid_tools_call_with_arguments(self):
        """A tools/call request with non-empty arguments parses successfully."""
        data = json.dumps({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "get_action_item", "arguments": {"id": "abc123"}},
        }).encode()
        result = parse_jsonrpc_request(data)
        assert result["params"]["arguments"] == {"id": "abc123"}

    def test_invalid_json_raises_parse_error(self):
        """Malformed JSON raises JsonRpcParseError."""
        with pytest.raises(JsonRpcParseError) as exc_info:
            parse_jsonrpc_request(b"not valid json {{{")
        assert exc_info.value.code == PARSE_ERROR

    def test_non_object_json_raises_parse_error(self):
        """A JSON array (not object) raises JsonRpcParseError."""
        data = json.dumps([1, 2, 3]).encode()
        with pytest.raises(JsonRpcParseError) as exc_info:
            parse_jsonrpc_request(data)
        assert exc_info.value.code == PARSE_ERROR

    def test_missing_jsonrpc_field_raises_invalid_request(self):
        """Missing 'jsonrpc' field raises JsonRpcInvalidRequest."""
        data = json.dumps({"id": 1, "method": "tools/list"}).encode()
        with pytest.raises(JsonRpcInvalidRequest) as exc_info:
            parse_jsonrpc_request(data)
        assert exc_info.value.code == INVALID_REQUEST
        assert "jsonrpc" in exc_info.value.message

    def test_wrong_jsonrpc_version_raises_invalid_request(self):
        """jsonrpc field != '2.0' raises JsonRpcInvalidRequest."""
        data = json.dumps({"jsonrpc": "1.0", "id": 1, "method": "tools/list"}).encode()
        with pytest.raises(JsonRpcInvalidRequest) as exc_info:
            parse_jsonrpc_request(data)
        assert exc_info.value.code == INVALID_REQUEST
        assert "2.0" in exc_info.value.message

    def test_missing_method_field_raises_invalid_request(self):
        """Missing 'method' field raises JsonRpcInvalidRequest."""
        data = json.dumps({"jsonrpc": "2.0", "id": 1}).encode()
        with pytest.raises(JsonRpcInvalidRequest) as exc_info:
            parse_jsonrpc_request(data)
        assert exc_info.value.code == INVALID_REQUEST
        assert "method" in exc_info.value.message

    def test_empty_method_raises_invalid_request(self):
        """Empty string method raises JsonRpcInvalidRequest."""
        data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": ""}).encode()
        with pytest.raises(JsonRpcInvalidRequest) as exc_info:
            parse_jsonrpc_request(data)
        assert exc_info.value.code == INVALID_REQUEST

    def test_non_string_method_raises_invalid_request(self):
        """Non-string method raises JsonRpcInvalidRequest."""
        data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": 123}).encode()
        with pytest.raises(JsonRpcInvalidRequest) as exc_info:
            parse_jsonrpc_request(data)
        assert exc_info.value.code == INVALID_REQUEST

    def test_tools_call_missing_params_raises_invalid_request(self):
        """tools/call without params raises JsonRpcInvalidRequest."""
        data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call"}).encode()
        with pytest.raises(JsonRpcInvalidRequest) as exc_info:
            parse_jsonrpc_request(data)
        assert "params" in exc_info.value.message

    def test_tools_call_params_not_dict_raises_invalid_request(self):
        """tools/call with non-dict params raises JsonRpcInvalidRequest."""
        data = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": "not_a_dict",
        }).encode()
        with pytest.raises(JsonRpcInvalidRequest) as exc_info:
            parse_jsonrpc_request(data)
        assert "params" in exc_info.value.message

    def test_tools_call_missing_params_name_raises_invalid_request(self):
        """tools/call with missing params.name raises JsonRpcInvalidRequest."""
        data = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"arguments": {}},
        }).encode()
        with pytest.raises(JsonRpcInvalidRequest) as exc_info:
            parse_jsonrpc_request(data)
        assert "params.name" in exc_info.value.message

    def test_tools_call_empty_params_name_raises_invalid_request(self):
        """tools/call with empty params.name raises JsonRpcInvalidRequest."""
        data = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "", "arguments": {}},
        }).encode()
        with pytest.raises(JsonRpcInvalidRequest) as exc_info:
            parse_jsonrpc_request(data)
        assert "params.name" in exc_info.value.message

    def test_tools_call_missing_params_arguments_raises_invalid_request(self):
        """tools/call with missing params.arguments raises JsonRpcInvalidRequest."""
        data = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "some_tool"},
        }).encode()
        with pytest.raises(JsonRpcInvalidRequest) as exc_info:
            parse_jsonrpc_request(data)
        assert "params.arguments" in exc_info.value.message

    def test_tools_call_arguments_not_dict_raises_invalid_request(self):
        """tools/call with non-dict params.arguments raises JsonRpcInvalidRequest."""
        data = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "some_tool", "arguments": "not_a_dict"},
        }).encode()
        with pytest.raises(JsonRpcInvalidRequest) as exc_info:
            parse_jsonrpc_request(data)
        assert "params.arguments" in exc_info.value.message

    def test_non_tools_call_method_does_not_validate_params(self):
        """Non tools/call methods don't require params validation."""
        data = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
        }).encode()
        result = parse_jsonrpc_request(data)
        assert result["method"] == "tools/list"

    def test_request_without_id_field_parses(self):
        """A request without 'id' (notification) still parses."""
        data = json.dumps({"jsonrpc": "2.0", "method": "tools/list"}).encode()
        result = parse_jsonrpc_request(data)
        assert "id" not in result

    def test_invalid_utf8_raises_parse_error(self):
        """Invalid UTF-8 bytes raise JsonRpcParseError."""
        with pytest.raises(JsonRpcParseError):
            parse_jsonrpc_request(b"\xff\xfe invalid bytes")


class TestBuildToolResult:
    """Tests for build_tool_result()."""

    def test_success_result(self):
        """Builds a success tool result response."""
        content = [{"type": "text", "text": "Hello"}]
        result = build_tool_result(request_id=1, content=content)
        assert result == {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": content, "isError": False},
        }

    def test_error_result(self):
        """Builds an error tool result response."""
        content = [{"type": "text", "text": "Error: something failed"}]
        result = build_tool_result(request_id=5, content=content, is_error=True)
        assert result == {
            "jsonrpc": "2.0",
            "id": 5,
            "result": {"content": content, "isError": True},
        }

    def test_null_request_id(self):
        """Handles None request_id."""
        result = build_tool_result(request_id=None, content=[])
        assert result["id"] is None

    def test_string_request_id(self):
        """Handles string request_id per JSON-RPC 2.0 spec."""
        result = build_tool_result(request_id="abc-123", content=[])
        assert result["id"] == "abc-123"


class TestBuildToolsListResponse:
    """Tests for build_tools_list_response()."""

    def test_empty_tools_list(self):
        """Builds response with no tools."""
        result = build_tools_list_response(request_id=1, tools=[])
        assert result == {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"tools": []},
        }

    def test_with_tool_definitions(self):
        """Builds response with tool definitions."""
        tools = [
            {
                "name": "get_current_user",
                "description": "Get current user info",
                "inputSchema": {"type": "object", "properties": {}},
            }
        ]
        result = build_tools_list_response(request_id=2, tools=tools)
        assert result["result"]["tools"] == tools
        assert result["id"] == 2


class TestBuildJsonrpcError:
    """Tests for build_jsonrpc_error()."""

    def test_parse_error(self):
        """Builds a parse error response."""
        result = build_jsonrpc_error(
            request_id=None, code=PARSE_ERROR, message="Parse error: invalid JSON"
        )
        assert result == {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32700, "message": "Parse error: invalid JSON"},
        }

    def test_invalid_request_error(self):
        """Builds an invalid request error response."""
        result = build_jsonrpc_error(
            request_id=1, code=INVALID_REQUEST, message="Missing method field"
        )
        assert result["error"]["code"] == -32600

    def test_method_not_found_error(self):
        """Builds a method not found error response."""
        result = build_jsonrpc_error(
            request_id=3, code=METHOD_NOT_FOUND, message="Unknown method: foo/bar"
        )
        assert result["error"]["code"] == -32601

    def test_invalid_params_error(self):
        """Builds an invalid params error response."""
        result = build_jsonrpc_error(
            request_id=4, code=INVALID_PARAMS, message="Unknown tool: bad_tool"
        )
        assert result["error"]["code"] == -32602

    def test_internal_error(self):
        """Builds an internal error response."""
        result = build_jsonrpc_error(
            request_id=5, code=INTERNAL_ERROR, message="Unexpected failure"
        )
        assert result["error"]["code"] == -32603


class TestErrorConstants:
    """Tests for error code constants."""

    def test_error_codes_values(self):
        """Error codes match JSON-RPC 2.0 spec values."""
        assert PARSE_ERROR == -32700
        assert INVALID_REQUEST == -32600
        assert METHOD_NOT_FOUND == -32601
        assert INVALID_PARAMS == -32602
        assert INTERNAL_ERROR == -32603
