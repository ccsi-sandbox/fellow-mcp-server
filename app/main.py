"""Flask application factory and entry point for the Fellow MCP Server."""

import json
import time
from typing import Any

import requests as requests_lib
import structlog
from flask import Flask, Response, request

from app.auth.guard import AuthGuard
from app.client.fellow_api import FellowApiClient, FellowApiError
from app.client.paginator import CursorPaginator, PaginationError
from app.config import AppConfig
from app.logging.setup import bind_request_id, configure_logging
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


# Tool descriptions for MCP tools/list response
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

    Converts the internal param spec format into a standard JSON Schema
    object suitable for MCP tools/list responses.

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
    """Create and populate the tool registry with all 16 tools.

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


def create_app(config: dict | None = None) -> Flask:
    """Create and configure the Flask application.

    Uses the app factory pattern for testability and flexible configuration.
    Initializes all components: config, logging, auth, API client, validator,
    paginator, and tool registry. Wires /mcp and /health endpoints.

    Args:
        config: Optional dictionary of configuration overrides.
                Used primarily in testing to inject test-specific settings.

    Returns:
        Configured Flask application instance.
    """
    app = Flask(__name__)

    if config:
        app.config.update(config)

    # Load application config
    if config and config.get("APP_CONFIG"):
        app_config: AppConfig = config["APP_CONFIG"]
    else:
        app_config = AppConfig.from_env()

    # Configure structured logging
    configure_logging(app_config.log_level)

    # Initialize components
    auth_guard = AuthGuard(app_config)
    api_client = FellowApiClient(app_config)
    paginator = CursorPaginator()
    validator = InputValidator()
    registry = _create_registry()

    # Store on app for access in tests
    app.config["_auth_guard"] = auth_guard
    app.config["_api_client"] = api_client
    app.config["_paginator"] = paginator
    app.config["_validator"] = validator
    app.config["_registry"] = registry

    # Bind request ID for log correlation
    bind_request_id(app)

    # Register routes
    _register_routes(app, app_config, auth_guard, api_client, paginator, validator, registry)

    return app


def _register_routes(
    app: Flask,
    app_config: AppConfig,
    auth_guard: AuthGuard,
    api_client: FellowApiClient,
    paginator: CursorPaginator,
    validator: InputValidator,
    registry: ToolRegistry,
) -> None:
    """Register all route handlers on the Flask app.

    Args:
        app: The Flask application instance.
        app_config: Application configuration.
        auth_guard: Authentication guard instance.
        api_client: Fellow API client instance.
        paginator: Cursor paginator instance.
        validator: Input validator instance.
        registry: Tool registry instance.
    """
    mcp_path = app_config.mcp_endpoint_path

    @app.route(mcp_path, methods=["POST"])
    def mcp_endpoint() -> tuple[Response, int]:
        """Handle MCP protocol messages (JSON-RPC 2.0).

        Accepts tools/list and tools/call methods.
        Returns JSON-RPC 2.0 responses.
        """
        # Auth check
        auth_response = auth_guard.check_request(request)
        if auth_response is not None:
            return auth_response, 401

        # Parse JSON-RPC request
        request_id = None
        try:
            parsed = parse_jsonrpc_request(request.get_data())
            request_id = parsed.get("id")
            method = parsed["method"]

            logger.debug(
                "mcp_request_received",
                method=method,
                params=parsed.get("params"),
                jsonrpc_id=request_id,
            )
        except JsonRpcParseError as e:
            response_body = build_jsonrpc_error(None, e.code, e.message)
            return Response(
                json.dumps(response_body),
                status=200,
                content_type="application/json",
            ), 200
        except JsonRpcInvalidRequest as e:
            response_body = build_jsonrpc_error(None, e.code, e.message)
            return Response(
                json.dumps(response_body),
                status=200,
                content_type="application/json",
            ), 200

        # Dispatch method
        if method == "tools/list":
            tools = registry.list_tools()
            response_body = build_tools_list_response(request_id, tools)
            return Response(
                json.dumps(response_body),
                status=200,
                content_type="application/json",
            ), 200

        elif method == "initialize":
            # MCP protocol handshake — return server capabilities
            response_body = {
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
            return Response(
                json.dumps(response_body),
                status=200,
                content_type="application/json",
            ), 200

        elif method == "notifications/initialized":
            # Client acknowledgment — no response needed for notifications
            # but we return an empty success since this is HTTP (not streaming)
            return Response(
                json.dumps({"jsonrpc": "2.0", "id": request_id, "result": {}}),
                status=200,
                content_type="application/json",
            ), 200

        elif method == "tools/call":
            return _handle_tools_call(
                parsed, request_id, registry, validator, api_client, paginator
            )

        else:
            # Unknown method
            response_body = build_jsonrpc_error(
                request_id, METHOD_NOT_FOUND, f"Method not found: {method}"
            )
            return Response(
                json.dumps(response_body),
                status=200,
                content_type="application/json",
            ), 200

    @app.route("/health", methods=["GET"])
    def health() -> tuple[Response, int]:
        """Health check endpoint.

        Returns server status and Fellow API connectivity.
        """
        fellow_status = "unreachable"
        try:
            if api_client.health_check():
                fellow_status = "reachable"
        except Exception:
            fellow_status = "unreachable"

        health_response = {
            "status": "healthy",
            "fellow_api": fellow_status,
        }
        return Response(
            json.dumps(health_response),
            status=200,
            content_type="application/json",
        ), 200


def _handle_tools_call(
    parsed: dict[str, Any],
    request_id: Any,
    registry: ToolRegistry,
    validator: InputValidator,
    api_client: FellowApiClient,
    paginator: CursorPaginator,
) -> tuple[Response, int]:
    """Handle a tools/call JSON-RPC method.

    Dispatches to the appropriate tool handler after validation.
    Logs tool name, execution duration, and outcome at INFO level.

    Args:
        parsed: The parsed JSON-RPC request.
        request_id: The JSON-RPC request ID.
        registry: The tool registry.
        validator: The input validator.
        api_client: The Fellow API client.
        paginator: The cursor paginator.

    Returns:
        Tuple of (Response, status_code).
    """
    params = parsed["params"]
    tool_name = params["name"]
    arguments = params["arguments"]

    start_time = time.time()
    outcome = "success"

    try:
        # Get handler (raises ToolNotFoundError if unknown)
        try:
            handler = registry.get_handler(tool_name)
        except ToolNotFoundError:
            outcome = "error_tool_not_found"
            response_body = build_jsonrpc_error(
                request_id, INVALID_PARAMS, f"Unknown tool: {tool_name}"
            )
            return Response(
                json.dumps(response_body),
                status=200,
                content_type="application/json",
            ), 200

        # Validate input
        errors = validator.validate(tool_name, arguments)
        if errors:
            outcome = "error_validation"
            error_text = "Validation errors:\n" + "\n".join(f"- {e}" for e in errors)
            response_body = build_tool_result(
                request_id,
                [{"type": "text", "text": error_text}],
                is_error=True,
            )
            return Response(
                json.dumps(response_body),
                status=200,
                content_type="application/json",
            ), 200

        # Execute handler
        try:
            result = handler(arguments=arguments, client=api_client, paginator=paginator)
        except FellowApiError as e:
            outcome = "error_fellow_api"
            error_text = f"Fellow API error (HTTP {e.status_code}): {e.message}"
            response_body = build_tool_result(
                request_id,
                [{"type": "text", "text": error_text}],
                is_error=True,
            )
            return Response(
                json.dumps(response_body),
                status=200,
                content_type="application/json",
            ), 200
        except PaginationError as e:
            outcome = "error_pagination"
            error_text = f"Pagination failed on page {e.page_number}: {e.cause}"
            response_body = build_tool_result(
                request_id,
                [{"type": "text", "text": error_text}],
                is_error=True,
            )
            return Response(
                json.dumps(response_body),
                status=200,
                content_type="application/json",
            ), 200
        except requests_lib.RequestException as e:
            outcome = "error_network"
            error_text = f"Network error communicating with Fellow API: {str(e)}"
            logger.warning("network_error", tool=tool_name, error=str(e))
            response_body = build_tool_result(
                request_id,
                [{"type": "text", "text": error_text}],
                is_error=True,
            )
            return Response(
                json.dumps(response_body),
                status=200,
                content_type="application/json",
            ), 200

        # Build success response
        result_text = json.dumps(result)
        response_body = build_tool_result(
            request_id,
            [{"type": "text", "text": result_text}],
            is_error=False,
        )
        return Response(
            json.dumps(response_body),
            status=200,
            content_type="application/json",
        ), 200

    except Exception as e:
        outcome = "error_internal"
        response_body = build_jsonrpc_error(
            request_id, INTERNAL_ERROR, f"Internal error: {str(e)}"
        )
        return Response(
            json.dumps(response_body),
            status=200,
            content_type="application/json",
        ), 200

    finally:
        duration_ms = round((time.time() - start_time) * 1000, 2)
        logger.info(
            "tool_call",
            tool=tool_name,
            duration_ms=duration_ms,
            outcome=outcome,
        )


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=8000)
