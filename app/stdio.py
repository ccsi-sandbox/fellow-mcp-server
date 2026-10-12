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
    negotiate_protocol_version,
    parse_jsonrpc_request,
)
from app.mcp.definitions import TOOL_HANDLERS, create_registry
from app.mcp.registry import ToolNotFoundError, ToolRegistry
from app.validation.schemas import InputValidator

logger = structlog.get_logger(__name__)


# Tool descriptions, annotations, handlers and the registry factory live in
# app.mcp.definitions so that this stdio transport and the HTTP transport in
# app.main advertise byte-identical tool metadata. Do not re-declare them.


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
        # The negotiated version must be >= 2025-03-26 for a client to honour
        # the tool annotations that distinguish reads from writes.
        client_params = parsed.get("params") or {}
        protocol_version = negotiate_protocol_version(
            client_params.get("protocolVersion")
            if isinstance(client_params, dict)
            else None
        )
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": protocol_version,
                "capabilities": {
                    "tools": {
                        "listChanged": False,
                    },
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
    registry = create_registry()

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
