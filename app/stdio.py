"""MCP stdio transport for the Fellow MCP Server.

Implements the MCP stdio specification: reads newline-delimited JSON-RPC
messages from stdin, writes newline-delimited JSON-RPC responses to stdout.
All logging is directed to stderr to keep stdout clean for protocol messages.

Usage:
    python3 -m app.stdio

Environment variables:
    FELLOW_API_KEY      - Required. Your Fellow.ai API key.
    FELLOW_SUBDOMAIN    - Required. Your Fellow workspace subdomain.
    LOG_LEVEL           - Optional. Default: INFO.
    TZ                  - Optional. Timezone. Default: America/Los_Angeles.
"""

import json
import logging
import sys
import time
from typing import Any, TextIO

import structlog

from app.client.fellow_api import FellowApiClient, FellowApiError
from app.client.paginator import CursorPaginator, PaginationError
from app.config import AppConfig
from app.logging.metrics import RequestMetrics
from app.mcp.errors import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    JsonRpcInvalidRequest,
    JsonRpcParseError,
)
from app.mcp.protocol import (
    build_jsonrpc_error,
    build_tool_result,
    build_tools_list_response,
    parse_jsonrpc_request,
)
from app.mcp.registry import ToolNotFoundError, ToolRegistry
from app.tools.action_items import (
    archive_action_item,
    complete_action_item,
    get_action_item,
    list_action_items,
)
from app.tools.notes import delete_note, get_note, list_notes
from app.tools.recordings import delete_recording, get_recording, list_recordings
from app.tools.user import get_current_user
from app.tools.webhooks import (
    create_webhook,
    delete_webhook,
    get_webhook,
    list_webhooks,
    update_webhook,
)
from app.validation.schemas import InputValidator, TOOL_SCHEMAS

logger = structlog.get_logger(__name__)


# Tool descriptions (same as main.py)
TOOL_DESCRIPTIONS: dict[str, str] = {
    "list_action_items": (
        "List action items with optional filters for completed status, "
        "archived status, AI detection, scope, and ordering."
    ),
    "get_action_item": "Retrieve a single action item by its ID.",
    "complete_action_item": (
        "Mark an action item as complete or incomplete."
    ),
    "archive_action_item": "Archive an action item by its ID.",
    "list_notes": (
        "List meeting notes with optional filters for event, dates, "
        "channel, title, and attendees."
    ),
    "get_note": "Retrieve a single note by its ID.",
    "delete_note": "Delete a note by its ID.",
    "list_recordings": (
        "List recordings with optional filters for event, dates, "
        "channel, and title. Supports include options for transcript and AI notes."
    ),
    "get_recording": (
        "Retrieve a single recording by its ID with optional includes "
        "for transcript, AI notes, and media URL."
    ),
    "delete_recording": "Delete a recording by its ID.",
    "list_webhooks": (
        "List webhooks with optional limit and cursor for pagination."
    ),
    "get_webhook": "Retrieve a single webhook by its ID.",
    "create_webhook": (
        "Create a new webhook with a URL, enabled events, "
        "and optional description and status."
    ),
    "update_webhook": (
        "Update an existing webhook's URL, enabled events, "
        "description, or status."
    ),
    "delete_webhook": "Delete a webhook by its ID.",
    "get_current_user": (
        "Get the authenticated user's information including "
        "user ID, name, email, and workspace details."
    ),
}

# Tool handlers mapped by name
TOOL_HANDLERS: dict[str, Any] = {
    "list_action_items": list_action_items,
    "get_action_item": get_action_item,
    "complete_action_item": complete_action_item,
    "archive_action_item": archive_action_item,
    "list_notes": list_notes,
    "get_note": get_note,
    "delete_note": delete_note,
    "list_recordings": list_recordings,
    "get_recording": get_recording,
    "delete_recording": delete_recording,
    "list_webhooks": list_webhooks,
    "get_webhook": get_webhook,
    "create_webhook": create_webhook,
    "update_webhook": update_webhook,
    "delete_webhook": delete_webhook,
    "get_current_user": get_current_user,
}


def _build_input_schema(tool_name: str) -> dict[str, Any]:
    """Build a JSON Schema dict from the internal TOOL_SCHEMAS definition.

    Args:
        tool_name: The tool name to build schema for.

    Returns:
        A JSON Schema dict with type, properties, and required fields.
    """
    schema_def = TOOL_SCHEMAS[tool_name]
    properties: dict[str, Any] = {}

    for param_name, param_spec in schema_def["params"].items():
        param_type = param_spec["type"]

        if param_type == "bool":
            properties[param_name] = {"type": "boolean"}
        elif param_type == "int":
            prop: dict[str, Any] = {"type": "integer"}
            if "min" in param_spec:
                prop["minimum"] = param_spec["min"]
            if "max" in param_spec:
                prop["maximum"] = param_spec["max"]
            properties[param_name] = prop
        elif param_type in ("string", "id", "date", "url"):
            properties[param_name] = {"type": "string"}
        elif param_type == "enum":
            properties[param_name] = {
                "type": "string",
                "enum": param_spec["enum_values"],
            }
        elif param_type == "enum_list":
            properties[param_name] = {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": param_spec["enum_values"],
                },
            }

    return {
        "type": "object",
        "properties": properties,
        "required": schema_def["required"],
    }


def _create_registry() -> ToolRegistry:
    """Create and populate the tool registry with all tools.

    Returns:
        A fully populated ToolRegistry instance.
    """
    registry = ToolRegistry()

    for tool_name, handler in TOOL_HANDLERS.items():
        registry.register(
            name=tool_name,
            description=TOOL_DESCRIPTIONS[tool_name],
            input_schema=_build_input_schema(tool_name),
            handler=handler,
        )

    return registry


def _configure_stdio_logging(log_level: str) -> None:
    """Configure logging to write exclusively to stderr.

    In stdio mode, stdout is reserved for MCP protocol messages.
    All logging output must go to stderr.

    Args:
        log_level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    level_upper = log_level.upper().strip() if log_level else "INFO"
    if level_upper not in valid_levels:
        level_upper = "INFO"

    numeric_level = getattr(logging, level_upper)

    # Remove all existing handlers and add one that writes to stderr
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(numeric_level)
    root_logger.addHandler(stderr_handler)
    root_logger.setLevel(numeric_level)

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )


def _write_message(message: dict[str, Any], output: TextIO) -> None:
    """Write a JSON-RPC message to the output stream.

    Serializes to a single line (no embedded newlines) followed by a newline
    delimiter, per the MCP stdio specification.

    Args:
        message: The JSON-RPC response dict to write.
        output: The output stream (stdout).
    """
    line = json.dumps(message, separators=(",", ":"))
    output.write(line + "\n")
    output.flush()


def _handle_tools_call(
    parsed: dict[str, Any],
    request_id: Any,
    registry: ToolRegistry,
    validator: InputValidator,
    api_client: FellowApiClient,
    paginator: CursorPaginator,
) -> dict[str, Any]:
    """Handle a tools/call JSON-RPC method.

    Args:
        parsed: The parsed JSON-RPC request.
        request_id: The JSON-RPC request ID.
        registry: The tool registry.
        validator: The input validator.
        api_client: The Fellow API client.
        paginator: The cursor paginator.

    Returns:
        JSON-RPC response dict.
    """
    params = parsed["params"]
    tool_name = params["name"]
    arguments = params["arguments"]

    metrics = RequestMetrics(start_time=time.time())

    try:
        # Get handler
        try:
            handler = registry.get_handler(tool_name)
        except ToolNotFoundError:
            return build_jsonrpc_error(
                request_id, INVALID_PARAMS, f"Unknown tool: {tool_name}"
            )

        # Validate input
        errors = validator.validate(tool_name, arguments)
        if errors:
            error_text = "Validation errors:\n" + "\n".join(f"- {e}" for e in errors)
            return build_tool_result(
                request_id,
                [{"type": "text", "text": error_text}],
                is_error=True,
            )

        # Execute handler
        try:
            result = handler(
                arguments=arguments,
                client=api_client,
                paginator=paginator,
                metrics=metrics,
            )
        except FellowApiError as e:
            error_text = f"Fellow API error (HTTP {e.status_code}): {e.message}"
            return build_tool_result(
                request_id,
                [{"type": "text", "text": error_text}],
                is_error=True,
            )
        except PaginationError as e:
            error_text = f"Pagination failed on page {e.page_number}: {e.cause}"
            return build_tool_result(
                request_id,
                [{"type": "text", "text": error_text}],
                is_error=True,
            )

        # Success
        result_text = json.dumps(result)
        return build_tool_result(
            request_id,
            [{"type": "text", "text": result_text}],
            is_error=False,
        )

    except Exception as e:
        logger.error("tool_call_error", tool=tool_name, error=str(e))
        return build_jsonrpc_error(
            request_id, INTERNAL_ERROR, f"Internal error: {str(e)}"
        )


def _handle_message(
    line: str,
    registry: ToolRegistry,
    validator: InputValidator,
    api_client: FellowApiClient,
    paginator: CursorPaginator,
    output: TextIO,
) -> None:
    """Parse and dispatch a single JSON-RPC message from stdin.

    Args:
        line: Raw line from stdin (one JSON-RPC message).
        registry: The tool registry.
        validator: The input validator.
        api_client: The Fellow API client.
        paginator: The cursor paginator.
        output: Output stream for responses (stdout).
    """
    request_id = None

    try:
        parsed = parse_jsonrpc_request(line.encode("utf-8"))
        request_id = parsed.get("id")
        method = parsed["method"]

        logger.debug("stdio_request", method=method, jsonrpc_id=request_id)

    except JsonRpcParseError as e:
        response = build_jsonrpc_error(None, e.code, e.message)
        _write_message(response, output)
        return
    except JsonRpcInvalidRequest as e:
        response = build_jsonrpc_error(None, e.code, e.message)
        _write_message(response, output)
        return

    # Dispatch method
    if method == "initialize":
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                },
                "serverInfo": {
                    "name": "fellow-mcp-server",
                    "version": "1.0.0",
                },
            },
        }
        _write_message(response, output)

    elif method == "notifications/initialized":
        # Client acknowledgment notification — no response required
        # Per JSON-RPC 2.0, notifications (no "id") don't get responses.
        # If the client did include an id, respond with empty result.
        if request_id is not None:
            _write_message(
                {"jsonrpc": "2.0", "id": request_id, "result": {}}, output
            )

    elif method == "tools/list":
        tools = registry.list_tools()
        response = build_tools_list_response(request_id, tools)
        _write_message(response, output)

    elif method == "tools/call":
        response = _handle_tools_call(
            parsed, request_id, registry, validator, api_client, paginator
        )
        _write_message(response, output)

    else:
        response = build_jsonrpc_error(
            request_id, METHOD_NOT_FOUND, f"Method not found: {method}"
        )
        _write_message(response, output)


def run_stdio() -> None:
    """Run the MCP server in stdio transport mode.

    Reads newline-delimited JSON-RPC messages from stdin, processes them,
    and writes responses to stdout. Exits when stdin is closed (EOF).
    """
    # Load config — auth is not used in stdio mode
    import os
    os.environ.setdefault("MCP_AUTH_ENABLED", "false")

    app_config = AppConfig.from_env()

    # Configure logging to stderr only
    _configure_stdio_logging(app_config.log_level)

    # Initialize components
    api_client = FellowApiClient(app_config)
    paginator = CursorPaginator()
    validator = InputValidator()
    registry = _create_registry()

    logger.info("stdio_server_started", tools_count=len(TOOL_HANDLERS))

    # Main message loop — read from stdin until EOF
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            _handle_message(
                line, registry, validator, api_client, paginator, sys.stdout
            )
    except KeyboardInterrupt:
        logger.info("stdio_server_shutdown", reason="keyboard_interrupt")
    except Exception as e:
        logger.error("stdio_server_error", error=str(e))
        sys.exit(1)

    logger.info("stdio_server_shutdown", reason="stdin_closed")


if __name__ == "__main__":
    run_stdio()
