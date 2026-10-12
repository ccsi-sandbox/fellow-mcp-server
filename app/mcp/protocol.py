"""JSON-RPC 2.0 parsing and MCP message building utilities."""

import json
from typing import Any

from app.mcp.errors import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    PARSE_ERROR,
    JsonRpcInvalidRequest,
    JsonRpcParseError,
)


# MCP protocol revisions this server implements, newest first.
#
# Tool annotations (readOnlyHint / destructiveHint / idempotentHint /
# openWorldHint) were introduced in revision 2025-03-26. A client that
# negotiates the older 2024-11-05 revision is entitled to ignore them, which
# means it has no way to tell this server's reads from its writes -- so the
# default advertised version must stay at or above 2025-03-26 for tool
# allow-listing to work.
LATEST_PROTOCOL_VERSION = "2025-06-18"
ANNOTATIONS_MIN_PROTOCOL_VERSION = "2025-03-26"
SUPPORTED_PROTOCOL_VERSIONS: tuple[str, ...] = (
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
)


def negotiate_protocol_version(requested: Any) -> str:
    """Pick the protocol version to report from an ``initialize`` request.

    Per the MCP specification the server echoes the client's requested version
    when it supports it, and otherwise answers with a version it does support.

    Args:
        requested: The ``params.protocolVersion`` value sent by the client.
            May be missing or of the wrong type.

    Returns:
        A supported protocol version string.
    """
    if isinstance(requested, str) and requested in SUPPORTED_PROTOCOL_VERSIONS:
        return requested
    return LATEST_PROTOCOL_VERSION


def parse_jsonrpc_request(data: bytes) -> dict[str, Any]:
    """Parse raw bytes into a validated JSON-RPC 2.0 request.

    Validates:
    - Data is valid JSON
    - Top-level value is a JSON object
    - ``jsonrpc`` field is present and equals "2.0"
    - ``method`` field is present and is a non-empty string

    For ``tools/call`` method, additionally validates:
    - ``params`` object is present
    - ``params.name`` is present and is a non-empty string
    - ``params.arguments`` is present and is a dict

    Args:
        data: Raw bytes from the HTTP request body.

    Returns:
        Parsed and validated JSON-RPC request as a dict.

    Raises:
        JsonRpcParseError: If JSON is malformed or not a JSON object.
        JsonRpcInvalidRequest: If required JSON-RPC fields are missing or invalid.
    """
    # Parse JSON
    try:
        parsed = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise JsonRpcParseError("Parse error: invalid JSON")

    # Must be a JSON object
    if not isinstance(parsed, dict):
        raise JsonRpcParseError("Parse error: request must be a JSON object")

    # Validate jsonrpc field
    if "jsonrpc" not in parsed:
        raise JsonRpcInvalidRequest("Invalid request: missing 'jsonrpc' field")

    if parsed["jsonrpc"] != "2.0":
        raise JsonRpcInvalidRequest(
            "Invalid request: 'jsonrpc' field must be \"2.0\""
        )

    # Validate method field
    if "method" not in parsed:
        raise JsonRpcInvalidRequest("Invalid request: missing 'method' field")

    if not isinstance(parsed["method"], str) or not parsed["method"]:
        raise JsonRpcInvalidRequest(
            "Invalid request: 'method' must be a non-empty string"
        )

    # For tools/call, validate params.name and params.arguments
    if parsed["method"] == "tools/call":
        params = parsed.get("params")
        if not isinstance(params, dict):
            raise JsonRpcInvalidRequest(
                "Invalid request: 'params' object is required for tools/call"
            )

        if "name" not in params or not isinstance(params["name"], str) or not params["name"]:
            raise JsonRpcInvalidRequest(
                "Invalid request: 'params.name' must be a non-empty string for tools/call"
            )

        if "arguments" not in params or not isinstance(params["arguments"], dict):
            raise JsonRpcInvalidRequest(
                "Invalid request: 'params.arguments' must be an object for tools/call"
            )

    return parsed


def build_tool_result(
    request_id: Any, content: list[dict], is_error: bool = False
) -> dict:
    """Build a tools/call success or error result in MCP format.

    Args:
        request_id: The JSON-RPC request ID to echo back.
        content: List of content blocks (e.g. [{"type": "text", "text": "..."}]).
        is_error: Whether this result represents a tool execution error.

    Returns:
        A well-formed JSON-RPC 2.0 response with MCP tool result structure.
    """
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "content": content,
            "isError": is_error,
        },
    }


def build_tools_list_response(request_id: Any, tools: list[dict]) -> dict:
    """Build a tools/list response with all tool definitions.

    Args:
        request_id: The JSON-RPC request ID to echo back.
        tools: List of tool definition dicts (name, description, inputSchema).

    Returns:
        A well-formed JSON-RPC 2.0 response with MCP tools list structure.
    """
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "tools": tools,
        },
    }


def build_jsonrpc_error(request_id: Any, code: int, message: str) -> dict:
    """Build a JSON-RPC 2.0 error response.

    Args:
        request_id: The JSON-RPC request ID to echo back (may be None for parse errors).
        code: JSON-RPC error code (e.g. -32700, -32600, -32601, -32602, -32603).
        message: Human-readable error message.

    Returns:
        A well-formed JSON-RPC 2.0 error response.
    """
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": code,
            "message": message,
        },
    }
