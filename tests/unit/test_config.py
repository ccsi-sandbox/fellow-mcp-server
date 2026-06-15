"""Unit tests for the configuration module (app/config.py).

Tests environment variable loading, validation, and error reporting
for AppConfig.from_env().

Validates: Requirements 2.4, 2.5, 2.6, 3.7, 3.8, 10.5, 10.6
"""

import pytest

from app.config import AppConfig


@pytest.mark.unit
class TestConfigValidLoading:
    """Tests for valid configuration loading."""

    def test_all_vars_set_loads_correctly(self, monkeypatch):
        """Valid config with all env vars set loads correctly."""
        monkeypatch.setenv("FELLOW_API_KEY", "my-api-key-12345")
        monkeypatch.setenv("FELLOW_SUBDOMAIN", "mycompany")
        monkeypatch.setenv("MCP_AUTH_ENABLED", "true")
        monkeypatch.setenv("MCP_AUTH_TOKEN", "a-secure-token-1234567")
        monkeypatch.setenv("GUNICORN_WORKERS", "4")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("MCP_ENDPOINT_PATH", "/custom-mcp")

        config = AppConfig.from_env()

        assert config.fellow_api_key == "my-api-key-12345"
        assert config.fellow_subdomain == "mycompany"
        assert config.mcp_auth_enabled is True
        assert config.mcp_auth_token == "a-secure-token-1234567"
        assert config.gunicorn_workers == 4
        assert config.log_level == "DEBUG"
        assert config.mcp_endpoint_path == "/custom-mcp"
        assert config.fellow_base_url == "https://mycompany.fellow.app"

    def test_minimal_vars_loads_with_defaults(self, monkeypatch):
        """Valid config with only required vars loads with sensible defaults."""
        monkeypatch.setenv("FELLOW_API_KEY", "key123")
        monkeypatch.setenv("FELLOW_SUBDOMAIN", "acme")
        # Ensure optional vars are unset
        monkeypatch.delenv("MCP_AUTH_ENABLED", raising=False)
        monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
        monkeypatch.delenv("GUNICORN_WORKERS", raising=False)
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        monkeypatch.delenv("MCP_ENDPOINT_PATH", raising=False)

        config = AppConfig.from_env()

        assert config.fellow_api_key == "key123"
        assert config.fellow_subdomain == "acme"
        assert config.mcp_auth_enabled is False
        assert config.mcp_auth_token is None
        assert config.gunicorn_workers == 2
        assert config.log_level == "INFO"
        assert config.mcp_endpoint_path == "/mcp"


@pytest.mark.unit
class TestConfigRequiredVars:
    """Tests for missing required environment variables."""

    def test_missing_fellow_api_key_raises_system_exit(self, monkeypatch):
        """Missing FELLOW_API_KEY raises SystemExit with descriptive message."""
        monkeypatch.delenv("FELLOW_API_KEY", raising=False)
        monkeypatch.setenv("FELLOW_SUBDOMAIN", "acme")
        monkeypatch.delenv("MCP_AUTH_ENABLED", raising=False)
        monkeypatch.delenv("GUNICORN_WORKERS", raising=False)
        monkeypatch.delenv("LOG_LEVEL", raising=False)

        with pytest.raises(SystemExit) as exc_info:
            AppConfig.from_env()

        assert "FELLOW_API_KEY" in str(exc_info.value)

    def test_missing_fellow_subdomain_raises_system_exit(self, monkeypatch):
        """Missing FELLOW_SUBDOMAIN raises SystemExit with descriptive message."""
        monkeypatch.setenv("FELLOW_API_KEY", "key123")
        monkeypatch.delenv("FELLOW_SUBDOMAIN", raising=False)
        monkeypatch.delenv("MCP_AUTH_ENABLED", raising=False)
        monkeypatch.delenv("GUNICORN_WORKERS", raising=False)
        monkeypatch.delenv("LOG_LEVEL", raising=False)

        with pytest.raises(SystemExit) as exc_info:
            AppConfig.from_env()

        assert "FELLOW_SUBDOMAIN" in str(exc_info.value)

    def test_empty_fellow_api_key_raises_system_exit(self, monkeypatch):
        """Empty FELLOW_API_KEY raises SystemExit."""
        monkeypatch.setenv("FELLOW_API_KEY", "")
        monkeypatch.setenv("FELLOW_SUBDOMAIN", "acme")
        monkeypatch.delenv("MCP_AUTH_ENABLED", raising=False)
        monkeypatch.delenv("GUNICORN_WORKERS", raising=False)
        monkeypatch.delenv("LOG_LEVEL", raising=False)

        with pytest.raises(SystemExit) as exc_info:
            AppConfig.from_env()

        assert "FELLOW_API_KEY" in str(exc_info.value)


@pytest.mark.unit
class TestConfigAuthToken:
    """Tests for MCP_AUTH_TOKEN validation when auth is enabled."""

    def _set_required(self, monkeypatch):
        """Set the minimum required env vars."""
        monkeypatch.setenv("FELLOW_API_KEY", "key123")
        monkeypatch.setenv("FELLOW_SUBDOMAIN", "acme")
        monkeypatch.delenv("GUNICORN_WORKERS", raising=False)
        monkeypatch.delenv("LOG_LEVEL", raising=False)

    def test_auth_enabled_with_valid_token_succeeds(self, monkeypatch):
        """MCP_AUTH_ENABLED=true with token >= 16 chars succeeds."""
        self._set_required(monkeypatch)
        monkeypatch.setenv("MCP_AUTH_ENABLED", "true")
        monkeypatch.setenv("MCP_AUTH_TOKEN", "abcdefghijklmnop")  # exactly 16

        config = AppConfig.from_env()

        assert config.mcp_auth_enabled is True
        assert config.mcp_auth_token == "abcdefghijklmnop"

    def test_auth_enabled_with_missing_token_raises_system_exit(self, monkeypatch):
        """MCP_AUTH_ENABLED=true with missing token raises SystemExit."""
        self._set_required(monkeypatch)
        monkeypatch.setenv("MCP_AUTH_ENABLED", "true")
        monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)

        with pytest.raises(SystemExit) as exc_info:
            AppConfig.from_env()

        assert "MCP_AUTH_TOKEN" in str(exc_info.value)

    def test_auth_enabled_with_short_token_raises_system_exit(self, monkeypatch):
        """MCP_AUTH_ENABLED=true with short token (< 16 chars) raises SystemExit."""
        self._set_required(monkeypatch)
        monkeypatch.setenv("MCP_AUTH_ENABLED", "true")
        monkeypatch.setenv("MCP_AUTH_TOKEN", "short")  # 5 chars

        with pytest.raises(SystemExit) as exc_info:
            AppConfig.from_env()

        assert "MCP_AUTH_TOKEN" in str(exc_info.value)
        assert "16" in str(exc_info.value)

    def test_auth_disabled_does_not_require_token(self, monkeypatch):
        """MCP_AUTH_ENABLED=false doesn't require token."""
        self._set_required(monkeypatch)
        monkeypatch.setenv("MCP_AUTH_ENABLED", "false")
        monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)

        config = AppConfig.from_env()

        assert config.mcp_auth_enabled is False
        assert config.mcp_auth_token is None

    def test_auth_unset_does_not_require_token(self, monkeypatch):
        """MCP_AUTH_ENABLED unset doesn't require token."""
        self._set_required(monkeypatch)
        monkeypatch.delenv("MCP_AUTH_ENABLED", raising=False)
        monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)

        config = AppConfig.from_env()

        assert config.mcp_auth_enabled is False


@pytest.mark.unit
class TestConfigGunicornWorkers:
    """Tests for GUNICORN_WORKERS validation (range 1-8)."""

    def _set_required(self, monkeypatch):
        """Set the minimum required env vars."""
        monkeypatch.setenv("FELLOW_API_KEY", "key123")
        monkeypatch.setenv("FELLOW_SUBDOMAIN", "acme")
        monkeypatch.delenv("MCP_AUTH_ENABLED", raising=False)
        monkeypatch.delenv("LOG_LEVEL", raising=False)

    def test_workers_1_succeeds(self, monkeypatch):
        """GUNICORN_WORKERS=1 succeeds (lower boundary)."""
        self._set_required(monkeypatch)
        monkeypatch.setenv("GUNICORN_WORKERS", "1")

        config = AppConfig.from_env()

        assert config.gunicorn_workers == 1

    def test_workers_8_succeeds(self, monkeypatch):
        """GUNICORN_WORKERS=8 succeeds (upper boundary)."""
        self._set_required(monkeypatch)
        monkeypatch.setenv("GUNICORN_WORKERS", "8")

        config = AppConfig.from_env()

        assert config.gunicorn_workers == 8

    def test_workers_0_raises_system_exit(self, monkeypatch):
        """GUNICORN_WORKERS=0 raises SystemExit (below range)."""
        self._set_required(monkeypatch)
        monkeypatch.setenv("GUNICORN_WORKERS", "0")

        with pytest.raises(SystemExit) as exc_info:
            AppConfig.from_env()

        assert "GUNICORN_WORKERS" in str(exc_info.value)

    def test_workers_9_raises_system_exit(self, monkeypatch):
        """GUNICORN_WORKERS=9 raises SystemExit (above range)."""
        self._set_required(monkeypatch)
        monkeypatch.setenv("GUNICORN_WORKERS", "9")

        with pytest.raises(SystemExit) as exc_info:
            AppConfig.from_env()

        assert "GUNICORN_WORKERS" in str(exc_info.value)

    def test_workers_non_integer_raises_system_exit(self, monkeypatch):
        """GUNICORN_WORKERS='abc' raises SystemExit."""
        self._set_required(monkeypatch)
        monkeypatch.setenv("GUNICORN_WORKERS", "abc")

        with pytest.raises(SystemExit) as exc_info:
            AppConfig.from_env()

        assert "GUNICORN_WORKERS" in str(exc_info.value)


@pytest.mark.unit
class TestConfigLogLevel:
    """Tests for LOG_LEVEL validation and fallback behavior."""

    def _set_required(self, monkeypatch):
        """Set the minimum required env vars."""
        monkeypatch.setenv("FELLOW_API_KEY", "key123")
        monkeypatch.setenv("FELLOW_SUBDOMAIN", "acme")
        monkeypatch.delenv("MCP_AUTH_ENABLED", raising=False)
        monkeypatch.delenv("GUNICORN_WORKERS", raising=False)

    def test_valid_log_level_debug_accepted(self, monkeypatch):
        """LOG_LEVEL='DEBUG' is accepted."""
        self._set_required(monkeypatch)
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")

        config = AppConfig.from_env()

        assert config.log_level == "DEBUG"

    def test_invalid_log_level_defaults_to_info(self, monkeypatch):
        """LOG_LEVEL='INVALID' defaults to INFO (no SystemExit)."""
        self._set_required(monkeypatch)
        monkeypatch.setenv("LOG_LEVEL", "INVALID")

        config = AppConfig.from_env()

        assert config.log_level == "INFO"


@pytest.mark.unit
class TestConfigDerivedValues:
    """Tests for derived configuration values."""

    def test_fellow_base_url_derived_correctly(self, monkeypatch):
        """fellow_base_url is derived from FELLOW_SUBDOMAIN."""
        monkeypatch.setenv("FELLOW_API_KEY", "key123")
        monkeypatch.setenv("FELLOW_SUBDOMAIN", "myorg")
        monkeypatch.delenv("MCP_AUTH_ENABLED", raising=False)
        monkeypatch.delenv("GUNICORN_WORKERS", raising=False)
        monkeypatch.delenv("LOG_LEVEL", raising=False)

        config = AppConfig.from_env()

        assert config.fellow_base_url == "https://myorg.fellow.app"
