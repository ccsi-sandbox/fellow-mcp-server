"""Property-based tests for malformed input handling.

# Feature: fellow-mcp-server, Property 1: Malformed input always produces valid JSON-RPC error

For any byte sequence that is not valid JSON, or any JSON object missing required
JSON-RPC 2.0 fields (jsonrpc, method), or any tools/call request referencing a tool
name not in the registered set, the server SHALL return a well-formed JSON-RPC 2.0
error response with an appropriate error code and non-empty message.
"""

import json
from typing import Any

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.mcp.errors import (
    PARSE_ERROR,
    INVALID_REQUEST,
    JsonRpcParseError,
    JsonRpcInvalidRequest,
)
from app.mcp.protocol import build_jsonrpc_error, parse_jsonrpc_request


# --- Helpers ---


def assert_valid_jsonrpc_error(response: dict[str, Any]) -> None:
    """Assert that a response is a well-formed JSON-RPC 2.0 error response."""
    assert response.get("jsonrpc") == "2.0", "Must have jsonrpc='2.0'"
    assert "id" in response, "Must have 'id' field"
    assert "error" in response, "Must have 'error' field"
    error = response["error"]
    assert isinstance(error, dict), "error must be a dict"
    assert "code" in error, "error must have 'code'"
    assert isinstance(error["code"], int), "error.code must be an integer"
    assert "message" in error, "error must have 'message'"
    assert isinstance(error["message"], str), "error.message must be a string"
    assert len(error["message"]) > 0, "error.message must be non-empty"


# --- Strategies ---

# Random byte sequences that are not valid JSON
random_binary = st.binary(min_size=0, max_size=256)

# Valid JSON but not a JSON object (arrays, strings, numbers, booleans, null)
non_object_json_values = st.one_of(
    st.lists(st.integers(), max_size=5),
    st.text(min_size=0, max_size=50),
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.booleans(),
    st.none(),
)

# JSON objects missing the "jsonrpc" field
missing_jsonrpc_objects = st.fixed_dictionaries(
    {"method": st.text(min_size=1, max_size=30)},
    optional={
        "id": st.one_of(st.integers(), st.text(min_size=1, max_size=10)),
        "params": st.dictionaries(
            st.text(min_size=1, max_size=10),
            st.text(min_size=1, max_size=10),
            max_size=3,
        ),
    },
).filter(lambda d: "jsonrpc" not in d)

# JSON objects missing the "method" field
missing_method_objects = st.fixed_dictionaries(
    {"jsonrpc": st.just("2.0")},
    optional={
        "id": st.one_of(st.integers(), st.text(min_size=1, max_size=10)),
        "params": st.dictionaries(
            st.text(min_size=1, max_size=10),
            st.text(min_size=1, max_size=10),
            max_size=3,
        ),
    },
).filter(lambda d: "method" not in d)

# JSON objects with wrong jsonrpc version
wrong_version_objects = st.fixed_dictionaries(
    {
        "jsonrpc": st.text(min_size=0, max_size=10).filter(lambda s: s != "2.0"),
        "method": st.text(min_size=1, max_size=30),
    },
    optional={
        "id": st.one_of(st.integers(), st.text(min_size=1, max_size=10)),
    },
)

# tools/call requests with missing or invalid params
invalid_tools_call_params = st.one_of(
    # params is not a dict
    st.fixed_dictionaries(
        {
            "jsonrpc": st.just("2.0"),
            "method": st.just("tools/call"),
            "id": st.integers(min_value=1, max_value=1000),
            "params": st.one_of(
                st.none(),
                st.text(min_size=0, max_size=20),
                st.integers(),
                st.lists(st.integers(), max_size=3),
            ),
        }
    ),
    # params missing "name"
    st.fixed_dictionaries(
        {
            "jsonrpc": st.just("2.0"),
            "method": st.just("tools/call"),
            "id": st.integers(min_value=1, max_value=1000),
            "params": st.fixed_dictionaries(
                {"arguments": st.just({})},
            ),
        }
    ),
    # params.name is not a string or is empty
    st.fixed_dictionaries(
        {
            "jsonrpc": st.just("2.0"),
            "method": st.just("tools/call"),
            "id": st.integers(min_value=1, max_value=1000),
            "params": st.fixed_dictionaries(
                {
                    "name": st.one_of(
                        st.just(""),
                        st.integers(),
                        st.none(),
                        st.lists(st.integers(), max_size=2),
                    ),
                    "arguments": st.just({}),
                }
            ),
        }
    ),
    # params.arguments is missing or not a dict
    st.fixed_dictionaries(
        {
            "jsonrpc": st.just("2.0"),
            "method": st.just("tools/call"),
            "id": st.integers(min_value=1, max_value=1000),
            "params": st.fixed_dictionaries(
                {
                    "name": st.text(min_size=1, max_size=20),
                }
            ),
        }
    ),
)

# Request IDs for build_jsonrpc_error
request_ids = st.one_of(
    st.none(),
    st.integers(min_value=0, max_value=10000),
    st.text(min_size=1, max_size=20),
)

# Error codes (valid JSON-RPC error codes)
error_codes = st.sampled_from([-32700, -32600, -32601, -32602, -32603])

# Non-empty error messages
error_messages = st.text(min_size=1, max_size=100)


# --- Property Tests ---


@pytest.mark.property
class TestMalformedInputProperty:
    """Property 1: Malformed input always produces valid JSON-RPC error.

    **Validates: Requirements 1.3, 1.6**
    """

    @given(data=random_binary)
    @settings(max_examples=200)
    def test_random_binary_raises_parse_error(self, data: bytes):
        """Any random binary input that is not valid JSON raises JsonRpcParseError.

        **Validates: Requirements 1.3**
        """
        # Check if this happens to be valid JSON that's also a dict with
        # required fields - if so, skip it (we only test truly malformed input)
        try:
            parsed = json.loads(data)
            if isinstance(parsed, dict) and "jsonrpc" in parsed and "method" in parsed:
                assume(False)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

        # The parser should raise either JsonRpcParseError or JsonRpcInvalidRequest
        with pytest.raises((JsonRpcParseError, JsonRpcInvalidRequest)) as exc_info:
            parse_jsonrpc_request(data)

        exc = exc_info.value
        assert isinstance(exc.code, int), "Exception must have integer code"
        assert isinstance(exc.message, str), "Exception must have string message"
        assert len(exc.message) > 0, "Exception must have non-empty message"
        assert exc.code in (PARSE_ERROR, INVALID_REQUEST)

    @given(value=non_object_json_values)
    @settings(max_examples=200)
    def test_valid_json_non_object_raises_parse_error(self, value: Any):
        """Valid JSON that is not an object raises JsonRpcParseError.

        **Validates: Requirements 1.3**
        """
        data = json.dumps(value).encode("utf-8")

        with pytest.raises(JsonRpcParseError) as exc_info:
            parse_jsonrpc_request(data)

        exc = exc_info.value
        assert exc.code == PARSE_ERROR
        assert isinstance(exc.message, str)
        assert len(exc.message) > 0

    @given(obj=missing_jsonrpc_objects)
    @settings(max_examples=200)
    def test_missing_jsonrpc_field_raises_invalid_request(self, obj: dict):
        """JSON object missing 'jsonrpc' field raises JsonRpcInvalidRequest.

        **Validates: Requirements 1.3**
        """
        data = json.dumps(obj).encode("utf-8")

        with pytest.raises(JsonRpcInvalidRequest) as exc_info:
            parse_jsonrpc_request(data)

        exc = exc_info.value
        assert exc.code == INVALID_REQUEST
        assert isinstance(exc.message, str)
        assert len(exc.message) > 0

    @given(obj=missing_method_objects)
    @settings(max_examples=200)
    def test_missing_method_field_raises_invalid_request(self, obj: dict):
        """JSON object missing 'method' field raises JsonRpcInvalidRequest.

        **Validates: Requirements 1.3**
        """
        data = json.dumps(obj).encode("utf-8")

        with pytest.raises(JsonRpcInvalidRequest) as exc_info:
            parse_jsonrpc_request(data)

        exc = exc_info.value
        assert exc.code == INVALID_REQUEST
        assert isinstance(exc.message, str)
        assert len(exc.message) > 0

    @given(obj=wrong_version_objects)
    @settings(max_examples=200)
    def test_wrong_jsonrpc_version_raises_invalid_request(self, obj: dict):
        """JSON object with wrong jsonrpc version raises JsonRpcInvalidRequest.

        **Validates: Requirements 1.3**
        """
        data = json.dumps(obj).encode("utf-8")

        with pytest.raises(JsonRpcInvalidRequest) as exc_info:
            parse_jsonrpc_request(data)

        exc = exc_info.value
        assert exc.code == INVALID_REQUEST
        assert isinstance(exc.message, str)
        assert len(exc.message) > 0

    @given(obj=invalid_tools_call_params)
    @settings(max_examples=200)
    def test_tools_call_with_invalid_params_raises_invalid_request(
        self, obj: dict
    ):
        """tools/call with missing or invalid params raises JsonRpcInvalidRequest.

        **Validates: Requirements 1.3**
        """
        data = json.dumps(obj).encode("utf-8")

        with pytest.raises(JsonRpcInvalidRequest) as exc_info:
            parse_jsonrpc_request(data)

        exc = exc_info.value
        assert exc.code == INVALID_REQUEST
        assert isinstance(exc.message, str)
        assert len(exc.message) > 0

    @given(request_id=request_ids, code=error_codes, message=error_messages)
    @settings(max_examples=200)
    def test_build_jsonrpc_error_always_well_formed(
        self, request_id: Any, code: int, message: str
    ):
        """build_jsonrpc_error always produces a well-formed JSON-RPC 2.0 error response.

        **Validates: Requirements 1.3, 1.6**
        """
        response = build_jsonrpc_error(request_id, code, message)

        assert_valid_jsonrpc_error(response)

        # Verify the response echoes back what we provided
        assert response["id"] == request_id
        assert response["error"]["code"] == code
        assert response["error"]["message"] == message
