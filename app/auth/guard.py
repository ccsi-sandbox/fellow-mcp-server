"""Authentication guard middleware for the Fellow MCP Server.

Validates the X-MCP-AUTH-TOKEN header on incoming requests using
constant-time comparison to prevent timing attacks.
"""

import hmac
import json
from typing import Optional

import structlog
from flask import Request, Response

from app.config import AppConfig

_AUTH_HEADER = "X-MCP-AUTH-TOKEN"

logger = structlog.get_logger(__name__)


class AuthGuard:
    """Middleware that validates the X-MCP-AUTH-TOKEN header.

    When authentication is enabled, rejects requests missing the header
    or presenting an invalid token with HTTP 401. When disabled, all
    requests pass through without validation.
    """

    def __init__(self, config: AppConfig) -> None:
        """Initialize the auth guard with application configuration.

        Args:
            config: Application configuration containing auth settings.
        """
        self._enabled = config.mcp_auth_enabled
        self._token = config.mcp_auth_token

    def check_request(self, request: Request) -> Optional[Response]:
        """Validate the authentication header on an incoming request.

        Returns None if the request is authorized, or an HTTP 401 Response
        with a JSON error body if the request should be rejected.

        Uses hmac.compare_digest for constant-time token comparison to
        prevent timing-based attacks.

        Args:
            request: The incoming Flask request object.

        Returns:
            None if authorized, or a 401 Response if rejected.
        """
        if not self._enabled:
            return None

        token_value = request.headers.get(_AUTH_HEADER)

        if token_value is None:
            logger.warning(
                "auth_rejected",
                reason="missing_header",
                client_ip=request.remote_addr,
            )
            return self._reject_response(
                f"Missing {_AUTH_HEADER} header"
            )

        if not hmac.compare_digest(token_value, self._token):
            logger.warning(
                "auth_rejected",
                reason="invalid_token",
                client_ip=request.remote_addr,
            )
            return self._reject_response("Invalid authentication token")

        return None

    @staticmethod
    def _reject_response(message: str) -> Response:
        """Build an HTTP 401 JSON error response.

        Args:
            message: The error message to include in the response body.

        Returns:
            A Flask Response with status 401 and JSON content type.
        """
        return Response(
            json.dumps({"error": message}),
            status=401,
            content_type="application/json",
        )
