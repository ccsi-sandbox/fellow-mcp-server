"""Property-based tests for auth guard correctness.

# Feature: fellow-mcp-server, Property 2: Auth guard correctness

For any request and any authentication configuration, the Auth Guard SHALL allow
the request if and only if: authentication is disabled (MCP_AUTH_ENABLED is not
case-sensitively "true") OR the X-MCP-AUTH-TOKEN header value exactly equals the
configured MCP_AUTH_TOKEN. All other cases SHALL result in HTTP 401.
"""

from dataclasses import dataclass
from typing import Optional
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.auth.guard import AuthGuard
from app.config import AppConfig


# --- Helpers ---


def make_config(auth_enabled: bool, auth_token: Optional[str]) -> AppConfig:
    """Build an AppConfig with the specified auth settings."""
    return AppConfig(
        fellow_api_key="test-api-key-value",
        fellow_subdomain="test",
        mcp_auth_enabled=auth_enabled,
        mcp_auth_token=auth_token,
        gunicorn_workers=2,
        log_level="INFO",
        mcp_endpoint_path="/mcp",
        fellow_base_url="https://test.fellow.app",
    )


def make_request(headers: Optional[dict] = None) -> MagicMock:
    """Create a mock Flask Request with the given headers."""
    request = MagicMock()
    request.remote_addr = "127.0.0.1"
    if headers is None:
        headers = {}
    request.headers = headers
    return request


# --- Strategies ---

# Random tokens of various lengths including empty
random_tokens = st.text(
    min_size=0,
    max_size=100,
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S", "Z"),
        blacklist_characters=("\x00",),
        max_codepoint=127,
    ),
)

# Non-empty tokens suitable for use as configured MCP_AUTH_TOKEN
configured_tokens = st.text(
    min_size=16,
    max_size=64,
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P"),
        blacklist_characters=("\x00",),
        max_codepoint=127,
    ),
)

# Auth enabled state values - only case-sensitive "true" enables auth
# Any other string value (including "True", "TRUE", "false", "", etc.) disables auth
auth_enabled_values = st.text(
    min_size=0,
    max_size=10,
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S"),
        blacklist_characters=("\x00",),
        max_codepoint=127,
    ),
)

# Header values: either present (some string) or absent (None)
header_values = st.one_of(st.none(), random_tokens)


# --- Property Tests ---


@pytest.mark.property
class TestAuthGuardCorrectnessProperty:
    """Property 2: Auth guard correctness.

    **Validates: Requirements 2.1, 2.3, 2.4**
    """

    @given(header_value=header_values)
    @settings(max_examples=200)
    def test_auth_disabled_allows_all_requests(self, header_value):
        """When auth is disabled, any or no header passes through.

        The Auth Guard SHALL allow the request when authentication is disabled
        regardless of whether the X-MCP-AUTH-TOKEN header is present or absent,
        and regardless of its value.

        **Validates: Requirements 2.3**
        """
        config = make_config(auth_enabled=False, auth_token=None)
        guard = AuthGuard(config)

        headers = {}
        if header_value is not None:
            headers["X-MCP-AUTH-TOKEN"] = header_value

        request = make_request(headers)
        result = guard.check_request(request)

        # Auth disabled → always passes (returns None)
        assert result is None

    @given(configured_token=configured_tokens)
    @settings(max_examples=200)
    def test_auth_enabled_exact_token_match_passes(self, configured_token):
        """When auth is enabled and header exactly matches configured token, request passes.

        The Auth Guard SHALL allow the request when the X-MCP-AUTH-TOKEN header
        value exactly equals the configured MCP_AUTH_TOKEN.

        **Validates: Requirements 2.1, 2.4**
        """
        config = make_config(auth_enabled=True, auth_token=configured_token)
        guard = AuthGuard(config)

        headers = {"X-MCP-AUTH-TOKEN": configured_token}
        request = make_request(headers)
        result = guard.check_request(request)

        # Exact match → passes (returns None)
        assert result is None

    @given(
        configured_token=configured_tokens,
        provided_token=random_tokens,
    )
    @settings(max_examples=200)
    def test_auth_enabled_wrong_token_returns_401(
        self, configured_token, provided_token
    ):
        """When auth is enabled and header does not match, request is rejected with 401.

        All cases where the token does not exactly equal the configured
        MCP_AUTH_TOKEN SHALL result in HTTP 401.

        **Validates: Requirements 2.1, 2.4**
        """
        # Ensure the provided token is different from the configured token
        assume(provided_token != configured_token)

        config = make_config(auth_enabled=True, auth_token=configured_token)
        guard = AuthGuard(config)

        headers = {"X-MCP-AUTH-TOKEN": provided_token}
        request = make_request(headers)
        result = guard.check_request(request)

        # Wrong token → rejected with 401
        assert result is not None
        assert result.status_code == 401

    @given(configured_token=configured_tokens)
    @settings(max_examples=200)
    def test_auth_enabled_missing_header_returns_401(self, configured_token):
        """When auth is enabled and header is absent, request is rejected with 401.

        The Auth Guard SHALL reject any request that does not include the
        X-MCP-AUTH-TOKEN header with HTTP 401.

        **Validates: Requirements 2.1**
        """
        config = make_config(auth_enabled=True, auth_token=configured_token)
        guard = AuthGuard(config)

        # No auth header present
        request = make_request({})
        result = guard.check_request(request)

        # Missing header → rejected with 401
        assert result is not None
        assert result.status_code == 401

    @given(
        auth_enabled_value=auth_enabled_values,
        configured_token=configured_tokens,
        header_value=header_values,
    )
    @settings(max_examples=200)
    def test_biconditional_allowed_iff_disabled_or_token_matches(
        self, auth_enabled_value, configured_token, header_value
    ):
        """The bi-conditional: request allowed ↔ (auth disabled OR token matches).

        For any request and authentication configuration, the Auth Guard SHALL
        allow the request if and only if: authentication is disabled
        (MCP_AUTH_ENABLED is not case-sensitively "true") OR the X-MCP-AUTH-TOKEN
        header value exactly equals the configured MCP_AUTH_TOKEN.

        **Validates: Requirements 2.1, 2.3, 2.4**
        """
        # Determine if auth is enabled (only case-sensitive "true")
        is_auth_enabled = auth_enabled_value == "true"

        config = make_config(
            auth_enabled=is_auth_enabled,
            auth_token=configured_token if is_auth_enabled else None,
        )
        guard = AuthGuard(config)

        headers = {}
        if header_value is not None:
            headers["X-MCP-AUTH-TOKEN"] = header_value

        request = make_request(headers)
        result = guard.check_request(request)

        # Compute expected outcome
        auth_disabled = not is_auth_enabled
        token_matches = (header_value is not None and header_value == configured_token)
        should_allow = auth_disabled or token_matches

        if should_allow:
            assert result is None, (
                f"Expected request to pass but got rejection. "
                f"auth_enabled={is_auth_enabled}, "
                f"header_value={header_value!r}, "
                f"configured_token={configured_token!r}"
            )
        else:
            assert result is not None, (
                f"Expected request to be rejected but it passed. "
                f"auth_enabled={is_auth_enabled}, "
                f"header_value={header_value!r}, "
                f"configured_token={configured_token!r}"
            )
            assert result.status_code == 401
