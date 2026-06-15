"""Structlog configuration and request correlation for the Fellow MCP Server.

Provides JSON-formatted structured logging with per-request correlation IDs.
"""

import logging
import uuid

import structlog
from flask import Flask, g


def configure_logging(log_level: str) -> None:
    """Configure structlog with JSON output and the specified log level.

    Sets up a processor chain that produces JSON-formatted log entries
    with timestamps, log level, and any bound context variables (e.g. request_id).

    Args:
        log_level: One of DEBUG, INFO, WARNING, ERROR, CRITICAL.
                   Case-insensitive. Defaults to INFO if invalid.
    """
    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    level_upper = log_level.upper().strip() if log_level else "INFO"

    if level_upper not in valid_levels:
        # Default to INFO for invalid values; a warning is logged after config
        level_upper = "INFO"

    numeric_level = getattr(logging, level_upper)

    # Configure the standard library root logger to match
    logging.basicConfig(
        format="%(message)s",
        level=numeric_level,
        force=True,
    )

    structlog.configure(
        processors=[
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
        cache_logger_on_first_use=True,
    )


def bind_request_id(app: Flask) -> None:
    """Register a Flask before_request hook that generates and binds a unique request_id.

    Each incoming request gets a UUID4 request_id stored in Flask's `g` object
    and bound to structlog's context variables. All log entries emitted during
    that request will automatically include the request_id field.

    Args:
        app: The Flask application to register the hook on.
    """

    @app.before_request
    def _set_request_id() -> None:
        """Generate a unique request_id and bind it to the structlog context."""
        request_id = str(uuid.uuid4())
        g.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
