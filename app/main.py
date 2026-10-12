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
from app.logging.metrics import RequestMetrics
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
    negotiate_protocol_version,
    parse_jsonrpc_request,
)
from app.mcp.definitions import create_registry
from app.mcp.registry import ToolNotFoundError, ToolRegistry
from app.validation.schemas import InputValidator

logger = structlog.get_logger(__name__)


# Tool descriptions, annotations, handlers and the registry factory live in
# app.mcp.definitions so that the HTTP transport here and the stdio transport
# in app.stdio advertise byte-identical tool metadata. Do not re-declare them.


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
    registry = create_registry()

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
            # MCP protocol handshake — return server capabilities.
            # The negotiated version must be >= 2025-03-26 for a client to
            # honour the tool annotations that distinguish reads from writes.
            client_params = parsed.get("params") or {}
            protocol_version = negotiate_protocol_version(
                client_params.get("protocolVersion")
                if isinstance(client_params, dict)
                else None
            )
            response_body = {
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
    Collects RequestMetrics for structured timing and size logging.

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

    # Create metrics collector at handler entry
    metrics = RequestMetrics(start_time=time.time())
    outcome = "success"

    # Record incoming MCP request size
    metrics.mcp_request_bytes = len(request.get_data())

    try:
        # Get handler (raises ToolNotFoundError if unknown)
        try:
            handler = registry.get_handler(tool_name)
        except ToolNotFoundError:
            outcome = "error_tool_not_found"
            # No upstream call made — zero out upstream-related steps
            metrics.upstream_api_ms = 0.0
            metrics.retry_wait_ms = 0.0
            metrics.serialization_ms = 0.0
            response_body = build_jsonrpc_error(
                request_id, INVALID_PARAMS, f"Unknown tool: {tool_name}"
            )
            response_json = json.dumps(response_body)
            metrics.mcp_response_bytes = len(response_json.encode("utf-8"))
            metrics.overhead_ms = metrics.compute_overhead_ms()
            return Response(
                response_json,
                status=200,
                content_type="application/json",
            ), 200

        # Validate input — time the validation step
        val_start = time.time()
        errors = validator.validate(tool_name, arguments)
        metrics.validation_ms = round((time.time() - val_start) * 1000, 2)

        if errors:
            outcome = "error_validation"
            # No upstream call made — zero out upstream-related steps
            metrics.upstream_api_ms = 0.0
            metrics.retry_wait_ms = 0.0
            metrics.serialization_ms = 0.0
            error_text = "Validation errors:\n" + "\n".join(f"- {e}" for e in errors)
            response_body = build_tool_result(
                request_id,
                [{"type": "text", "text": error_text}],
                is_error=True,
            )
            response_json = json.dumps(response_body)
            metrics.mcp_response_bytes = len(response_json.encode("utf-8"))
            metrics.overhead_ms = metrics.compute_overhead_ms()
            return Response(
                response_json,
                status=200,
                content_type="application/json",
            ), 200

        # Execute handler
        try:
            result = handler(arguments=arguments, client=api_client, paginator=paginator, metrics=metrics)
        except FellowApiError as e:
            outcome = "error_fellow_api"
            error_text = f"Fellow API error (HTTP {e.status_code}): {e.message}"
            response_body = build_tool_result(
                request_id,
                [{"type": "text", "text": error_text}],
                is_error=True,
            )
            response_json = json.dumps(response_body)
            metrics.mcp_response_bytes = len(response_json.encode("utf-8"))
            metrics.overhead_ms = metrics.compute_overhead_ms()
            return Response(
                response_json,
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
            response_json = json.dumps(response_body)
            metrics.mcp_response_bytes = len(response_json.encode("utf-8"))
            metrics.overhead_ms = metrics.compute_overhead_ms()
            return Response(
                response_json,
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
            response_json = json.dumps(response_body)
            metrics.mcp_response_bytes = len(response_json.encode("utf-8"))
            metrics.overhead_ms = metrics.compute_overhead_ms()
            return Response(
                response_json,
                status=200,
                content_type="application/json",
            ), 200

        # Serialize success response — time the serialization step
        ser_start = time.time()
        result_text = json.dumps(result)
        metrics.serialization_ms = round((time.time() - ser_start) * 1000, 2)

        response_body = build_tool_result(
            request_id,
            [{"type": "text", "text": result_text}],
            is_error=False,
        )
        response_json = json.dumps(response_body)
        metrics.mcp_response_bytes = len(response_json.encode("utf-8"))
        metrics.overhead_ms = metrics.compute_overhead_ms()
        return Response(
            response_json,
            status=200,
            content_type="application/json",
        ), 200

    except Exception as e:
        outcome = "error_internal"
        response_body = build_jsonrpc_error(
            request_id, INTERNAL_ERROR, f"Internal error: {str(e)}"
        )
        response_json = json.dumps(response_body)
        metrics.mcp_response_bytes = len(response_json.encode("utf-8"))
        metrics.overhead_ms = metrics.compute_overhead_ms()
        return Response(
            response_json,
            status=200,
            content_type="application/json",
        ), 200

    finally:
        try:
            timings = metrics.build_timings_dict()

            log_kwargs: dict[str, Any] = {
                "tool": tool_name,
                "outcome": outcome,
                "timings": timings,
                "mcp_request_bytes": metrics.mcp_request_bytes,
                "mcp_response_bytes": metrics.mcp_response_bytes,
                "upstream_request_bytes": metrics.upstream_request_bytes,
                "upstream_response_bytes": metrics.upstream_response_bytes,
                "upstream_api_calls": [
                    {
                        "page": call.page,
                        "duration_ms": call.duration_ms,
                        "status_code": call.status_code,
                        "request_bytes": call.request_bytes,
                        "response_bytes": call.response_bytes,
                    }
                    for call in metrics.upstream_api_calls
                ],
            }

            # Omit upstream_status_code when no upstream call was made (Req 3.6)
            if metrics.upstream_status_code is not None:
                log_kwargs["upstream_status_code"] = metrics.upstream_status_code

            logger.info("tool_call", **log_kwargs)
        except Exception as metrics_error:
            # Metrics computation failed — emit degraded log without timings
            logger.warning(
                "tool_call_metrics_error",
                tool=tool_name,
                outcome=outcome,
                error=str(metrics_error),
            )
            logger.info(
                "tool_call",
                tool=tool_name,
                outcome=outcome,
            )


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=8000)
