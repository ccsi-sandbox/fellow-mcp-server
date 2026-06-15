"""Unit tests for the AuthGuard middleware."""

import json
from unittest.mock import patch

import pytest
from flask import Flask

from app.auth.guard import AuthGuard
from app.config import AppConfig


def _make_config(
    auth_enabled: bool = True, auth_token: str = "valid-token-16chars!"
) -> AppConfig:
    """Create an AppConfig with customizable auth settings."""
    return AppConfig(
        fellow_api_key="test-key",
        fellow_subdomain="test",
        mcp_auth_enabled=auth_enabled,
        mcp_auth_token=auth_token if auth_enabled else None,
        gunicorn_workers=2,
        log_level="INFO",
        mcp_endpoint_path="/mcp",
        fellow_base_url="https://test.fellow.app",
    )


@pytest.fixture
def app():
    """Create a minimal Flask app for request context."""
    return Flask(__name__)


class TestAuthGuardDisabled:
    """Tests for when authentication is disabled."""

    def test_allows_request_without_header(self, app):
        """When auth is disabled, requests without a token pass through."""
        config = _make_config(auth_enabled=False)
        guard = AuthGuard(config)

        with app.test_request_context("/mcp", method="POST"):
            from flask import request
            result = guard.check_request(request)

        assert result is None

    def test_allows_request_with_any_header(self, app):
        """When auth is disabled, any token value passes through."""
        config = _make_config(auth_enabled=False)
        guard = AuthGuard(config)

        with app.test_request_context(
            "/mcp", method="POST", headers={"X-MCP-AUTH-TOKEN": "garbage"}
        ):
            from flask import request
            result = guard.check_request(request)

        assert result is None


class TestAuthGuardEnabled:
    """Tests for when authentication is enabled."""

    def test_valid_token_returns_none(self, app):
        """A valid token passes authentication."""
        token = "my-secret-token-1234"
        config = _make_config(auth_enabled=True, auth_token=token)
        guard = AuthGuard(config)

        with app.test_request_context(
            "/mcp", method="POST", headers={"X-MCP-AUTH-TOKEN": token}
        ):
            from flask import request
            result = guard.check_request(request)

        assert result is None

    def test_missing_header_returns_401(self, app):
        """Missing X-MCP-AUTH-TOKEN header returns 401 with JSON error."""
        config = _make_config(auth_enabled=True)
        guard = AuthGuard(config)

        with app.test_request_context("/mcp", method="POST"):
            from flask import request
            result = guard.check_request(request)

        assert result is not None
        assert result.status_code == 401
        body = json.loads(result.get_data(as_text=True))
        assert "Missing X-MCP-AUTH-TOKEN header" in body["error"]

    def test_invalid_token_returns_401(self, app):
        """An incorrect token returns 401 with JSON error."""
        config = _make_config(auth_enabled=True, auth_token="correct-token-16ch!")
        guard = AuthGuard(config)

        with app.test_request_context(
            "/mcp", method="POST", headers={"X-MCP-AUTH-TOKEN": "wrong-token"}
        ):
            from flask import request
            result = guard.check_request(request)

        assert result is not None
        assert result.status_code == 401
        body = json.loads(result.get_data(as_text=True))
        assert "Invalid authentication token" in body["error"]

    def test_empty_token_returns_401(self, app):
        """An empty token string returns 401."""
        config = _make_config(auth_enabled=True, auth_token="correct-token-16ch!")
        guard = AuthGuard(config)

        with app.test_request_context(
            "/mcp", method="POST", headers={"X-MCP-AUTH-TOKEN": ""}
        ):
            from flask import request
            result = guard.check_request(request)

        assert result is not None
        assert result.status_code == 401

    def test_response_content_type_is_json(self, app):
        """Rejection responses have application/json content type."""
        config = _make_config(auth_enabled=True)
        guard = AuthGuard(config)

        with app.test_request_context("/mcp", method="POST"):
            from flask import request
            result = guard.check_request(request)

        assert result.content_type == "application/json"

    def test_uses_constant_time_comparison(self, app):
        """Verify that hmac.compare_digest is used for token comparison."""
        token = "my-secret-token-1234"
        config = _make_config(auth_enabled=True, auth_token=token)
        guard = AuthGuard(config)

        with patch("app.auth.guard.hmac.compare_digest", return_value=True) as mock_cmp:
            with app.test_request_context(
                "/mcp", method="POST", headers={"X-MCP-AUTH-TOKEN": token}
            ):
                from flask import request
                result = guard.check_request(request)

            mock_cmp.assert_called_once_with(token, token)
            assert result is None


class TestAuthGuardLogging:
    """Tests for auth guard WARNING-level logging."""

    def test_logs_missing_header_rejection(self, app):
        """Rejected request due to missing header is logged at WARNING."""
        config = _make_config(auth_enabled=True)
        guard = AuthGuard(config)

        with patch("app.auth.guard.logger") as mock_logger:
            with app.test_request_context(
                "/mcp", method="POST", environ_base={"REMOTE_ADDR": "192.168.1.10"}
            ):
                from flask import request
                guard.check_request(request)

            mock_logger.warning.assert_called_once()
            call_kwargs = mock_logger.warning.call_args
            assert call_kwargs[1]["reason"] == "missing_header"
            assert call_kwargs[1]["client_ip"] == "192.168.1.10"

    def test_logs_invalid_token_rejection(self, app):
        """Rejected request due to invalid token is logged at WARNING."""
        config = _make_config(auth_enabled=True, auth_token="correct-token-16ch!")
        guard = AuthGuard(config)

        with patch("app.auth.guard.logger") as mock_logger:
            with app.test_request_context(
                "/mcp",
                method="POST",
                headers={"X-MCP-AUTH-TOKEN": "wrong"},
                environ_base={"REMOTE_ADDR": "10.0.0.5"},
            ):
                from flask import request
                guard.check_request(request)

            mock_logger.warning.assert_called_once()
            call_kwargs = mock_logger.warning.call_args
            assert call_kwargs[1]["reason"] == "invalid_token"
            assert call_kwargs[1]["client_ip"] == "10.0.0.5"

    def test_no_logging_on_success(self, app):
        """Successful auth does not log at WARNING."""
        token = "valid-secret-token-xx"
        config = _make_config(auth_enabled=True, auth_token=token)
        guard = AuthGuard(config)

        with patch("app.auth.guard.logger") as mock_logger:
            with app.test_request_context(
                "/mcp", method="POST", headers={"X-MCP-AUTH-TOKEN": token}
            ):
                from flask import request
                guard.check_request(request)

            mock_logger.warning.assert_not_called()
