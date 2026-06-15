"""Property-based tests for configuration validation.

# Feature: fellow-mcp-server, Property 3: Configuration validation rejects invalid startup state

Tests that for any set of environment variable values, the server refuses to start
if and only if required variables are missing/empty, MCP_AUTH_TOKEN is invalid while
auth is enabled, or GUNICORN_WORKERS is not an integer in [1, 8].
"""

import os
from unittest.mock import patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.config import AppConfig


# --- Strategies ---

# Non-empty strings for valid required fields
valid_api_keys = st.text(min_size=1, max_size=50, alphabet=st.characters(
    whitelist_categories=("L", "N", "P", "S"),
    blacklist_characters=("\x00",)
)).filter(lambda s: s.strip() != "")

valid_subdomains = st.text(min_size=1, max_size=30, alphabet=st.characters(
    whitelist_categories=("L", "N"),
)).filter(lambda s: s.strip() != "")

# Valid auth tokens (>= 16 chars)
valid_auth_tokens = st.text(min_size=16, max_size=64, alphabet=st.characters(
    whitelist_categories=("L", "N", "P"),
    blacklist_characters=("\x00",)
))

# Valid worker counts as strings
valid_worker_strings = st.integers(min_value=1, max_value=8).map(str)

# Invalid worker counts: out of range integers or non-integer strings
invalid_worker_integers = (
    st.integers(min_value=-100, max_value=0) | st.integers(min_value=9, max_value=100)
).map(str)

invalid_worker_non_integers = st.text(min_size=1, max_size=10, alphabet=st.characters(
    whitelist_categories=("L", "P"),
)).filter(lambda s: s.strip() != "" and not s.strip().lstrip("-").isdigit())

# Short auth tokens (< 16 chars, non-empty)
short_auth_tokens = st.text(min_size=1, max_size=15, alphabet=st.characters(
    whitelist_categories=("L", "N"),
))

# Empty or whitespace-only strings (for missing required vars)
empty_strings = st.just("") | st.text(
    min_size=1, max_size=5, alphabet=st.just(" ")
)


def build_env(
    api_key=None,
    subdomain=None,
    auth_enabled=None,
    auth_token=None,
    workers=None,
    log_level=None,
    endpoint_path=None,
):
    """Build an environment dict, omitting keys with None values."""
    env = {}
    if api_key is not None:
        env["FELLOW_API_KEY"] = api_key
    if subdomain is not None:
        env["FELLOW_SUBDOMAIN"] = subdomain
    if auth_enabled is not None:
        env["MCP_AUTH_ENABLED"] = auth_enabled
    if auth_token is not None:
        env["MCP_AUTH_TOKEN"] = auth_token
    if workers is not None:
        env["GUNICORN_WORKERS"] = workers
    if log_level is not None:
        env["LOG_LEVEL"] = log_level
    if endpoint_path is not None:
        env["MCP_ENDPOINT_PATH"] = endpoint_path
    return env


# --- Property Tests ---


@pytest.mark.property
class TestConfigValidationProperty:
    """Property 3: Configuration validation rejects invalid startup state.

    **Validates: Requirements 2.5, 2.6, 3.7, 3.8**
    """

    @given(
        api_key=valid_api_keys,
        subdomain=valid_subdomains,
        workers=valid_worker_strings,
    )
    @settings(max_examples=200)
    def test_valid_config_without_auth_loads_successfully(
        self, api_key, subdomain, workers
    ):
        """Valid configs with auth disabled always load successfully.

        **Validates: Requirements 2.5, 2.6**
        """
        env = build_env(
            api_key=api_key,
            subdomain=subdomain,
            auth_enabled="false",
            workers=workers,
        )
        with patch.dict(os.environ, env, clear=True):
            config = AppConfig.from_env()
            assert config.fellow_api_key == api_key.strip()
            assert config.fellow_subdomain == subdomain.strip()
            assert config.gunicorn_workers == int(workers)
            assert config.mcp_auth_enabled is False

    @given(
        api_key=valid_api_keys,
        subdomain=valid_subdomains,
        token=valid_auth_tokens,
        workers=valid_worker_strings,
    )
    @settings(max_examples=200)
    def test_valid_config_with_auth_loads_successfully(
        self, api_key, subdomain, token, workers
    ):
        """Valid configs with auth enabled and valid token load successfully.

        **Validates: Requirements 2.5, 2.6**
        """
        env = build_env(
            api_key=api_key,
            subdomain=subdomain,
            auth_enabled="true",
            auth_token=token,
            workers=workers,
        )
        with patch.dict(os.environ, env, clear=True):
            config = AppConfig.from_env()
            assert config.fellow_api_key == api_key.strip()
            assert config.fellow_subdomain == subdomain.strip()
            assert config.mcp_auth_enabled is True
            assert config.mcp_auth_token == token
            assert config.gunicorn_workers == int(workers)

    @given(
        api_key=empty_strings,
        subdomain=valid_subdomains,
    )
    @settings(max_examples=200)
    def test_missing_api_key_raises_system_exit(self, api_key, subdomain):
        """Missing/empty FELLOW_API_KEY always causes startup failure.

        **Validates: Requirements 3.7**
        """
        env = build_env(
            api_key=api_key,
            subdomain=subdomain,
            auth_enabled="false",
            workers="2",
        )
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(SystemExit) as exc_info:
                AppConfig.from_env()
            error_msg = str(exc_info.value)
            assert "FELLOW_API_KEY" in error_msg

    @given(
        api_key=valid_api_keys,
        subdomain=empty_strings,
    )
    @settings(max_examples=200)
    def test_missing_subdomain_raises_system_exit(self, api_key, subdomain):
        """Missing/empty FELLOW_SUBDOMAIN always causes startup failure.

        **Validates: Requirements 3.7**
        """
        env = build_env(
            api_key=api_key,
            subdomain=subdomain,
            auth_enabled="false",
            workers="2",
        )
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(SystemExit) as exc_info:
                AppConfig.from_env()
            error_msg = str(exc_info.value)
            assert "FELLOW_SUBDOMAIN" in error_msg

    @given(
        api_key=valid_api_keys,
        subdomain=valid_subdomains,
        token=short_auth_tokens,
    )
    @settings(max_examples=200)
    def test_short_auth_token_raises_system_exit(
        self, api_key, subdomain, token
    ):
        """Auth token < 16 chars with auth enabled causes startup failure.

        **Validates: Requirements 2.6**
        """
        assume(len(token) < 16)
        env = build_env(
            api_key=api_key,
            subdomain=subdomain,
            auth_enabled="true",
            auth_token=token,
            workers="2",
        )
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(SystemExit) as exc_info:
                AppConfig.from_env()
            error_msg = str(exc_info.value)
            assert "MCP_AUTH_TOKEN" in error_msg

    @given(
        api_key=valid_api_keys,
        subdomain=valid_subdomains,
    )
    @settings(max_examples=200)
    def test_missing_auth_token_with_auth_enabled_raises_system_exit(
        self, api_key, subdomain
    ):
        """Empty/missing MCP_AUTH_TOKEN with auth enabled causes startup failure.

        **Validates: Requirements 2.5**
        """
        env = build_env(
            api_key=api_key,
            subdomain=subdomain,
            auth_enabled="true",
            # No auth_token set
            workers="2",
        )
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(SystemExit) as exc_info:
                AppConfig.from_env()
            error_msg = str(exc_info.value)
            assert "MCP_AUTH_TOKEN" in error_msg

    @given(
        api_key=valid_api_keys,
        subdomain=valid_subdomains,
        workers=invalid_worker_integers,
    )
    @settings(max_examples=200)
    def test_out_of_range_workers_raises_system_exit(
        self, api_key, subdomain, workers
    ):
        """GUNICORN_WORKERS outside [1, 8] always causes startup failure.

        **Validates: Requirements 3.8**
        """
        env = build_env(
            api_key=api_key,
            subdomain=subdomain,
            auth_enabled="false",
            workers=workers,
        )
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(SystemExit) as exc_info:
                AppConfig.from_env()
            error_msg = str(exc_info.value)
            assert "GUNICORN_WORKERS" in error_msg

    @given(
        api_key=valid_api_keys,
        subdomain=valid_subdomains,
        workers=invalid_worker_non_integers,
    )
    @settings(max_examples=200)
    def test_non_integer_workers_raises_system_exit(
        self, api_key, subdomain, workers
    ):
        """Non-integer GUNICORN_WORKERS always causes startup failure.

        **Validates: Requirements 3.8**
        """
        env = build_env(
            api_key=api_key,
            subdomain=subdomain,
            auth_enabled="false",
            workers=workers,
        )
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(SystemExit) as exc_info:
                AppConfig.from_env()
            error_msg = str(exc_info.value)
            assert "GUNICORN_WORKERS" in error_msg

    @given(
        api_key=valid_api_keys,
        subdomain=valid_subdomains,
        auth_enabled=st.text(
            min_size=0, max_size=10,
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "S", "Z"),
                blacklist_characters=("\x00",),
                max_codepoint=127,
            ),
        ).filter(lambda s: s != "true"),
        token=st.text(
            min_size=0, max_size=10,
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "S"),
                blacklist_characters=("\x00",),
                max_codepoint=127,
            ),
        ),
        workers=valid_worker_strings,
    )
    @settings(max_examples=200)
    def test_auth_disabled_ignores_token_validation(
        self, api_key, subdomain, auth_enabled, token, workers
    ):
        """When auth is not enabled, any token value (or absence) is accepted.

        **Validates: Requirements 2.5, 2.6**
        """
        env = build_env(
            api_key=api_key,
            subdomain=subdomain,
            auth_enabled=auth_enabled,
            auth_token=token if token else None,
            workers=workers,
        )
        with patch.dict(os.environ, env, clear=True):
            # Should not raise - auth is disabled so token is irrelevant
            config = AppConfig.from_env()
            assert config.mcp_auth_enabled is False
