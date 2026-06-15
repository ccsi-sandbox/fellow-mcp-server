"""Shared pytest fixtures for the Fellow MCP Server test suite."""

import pytest

from app.config import AppConfig
from app.main import create_app


@pytest.fixture
def test_config():
    """Create a test AppConfig instance."""
    return AppConfig(
        fellow_api_key="test-api-key-12345",
        fellow_subdomain="testworkspace",
        mcp_auth_enabled=False,
        mcp_auth_token=None,
        gunicorn_workers=2,
        log_level="DEBUG",
        mcp_endpoint_path="/mcp",
        fellow_base_url="https://testworkspace.fellow.app",
    )


@pytest.fixture
def auth_test_config():
    """Create a test AppConfig with authentication enabled."""
    return AppConfig(
        fellow_api_key="test-api-key-12345",
        fellow_subdomain="testworkspace",
        mcp_auth_enabled=True,
        mcp_auth_token="test-secure-token-1234567890",
        gunicorn_workers=2,
        log_level="DEBUG",
        mcp_endpoint_path="/mcp",
        fellow_base_url="https://testworkspace.fellow.app",
    )


@pytest.fixture
def app(test_config):
    """Create a Flask application configured for testing."""
    app = create_app(config={"TESTING": True, "APP_CONFIG": test_config})
    return app


@pytest.fixture
def client(app):
    """Create a Flask test client."""
    return app.test_client()
