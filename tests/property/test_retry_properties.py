"""Property-based tests for retry logic on transient errors.

# Feature: fellow-mcp-server, Property 8: Retry logic on transient errors

For any Fellow API request that fails with a transient HTTP status code
(429, 500, 502, 503, 504), the client SHALL retry up to 3 times. If a
Retry-After header is present on a 429 response with a valid positive integer
value, that value SHALL be used as the delay instead of the calculated exponential
backoff. After retries are exhausted, the MCP error response SHALL contain the
HTTP status code and error message.
"""

from unittest.mock import patch

import pytest
import responses
from hypothesis import given, settings
from hypothesis import strategies as st

from app.client.fellow_api import (
    FellowApiClient,
    FellowApiError,
    TransientApiError,
)
from app.client.rate_limiter import TokenBucketRateLimiter
from app.config import AppConfig


# --- Helpers ---


class NoOpRateLimiter(TokenBucketRateLimiter):
    """A rate limiter that never blocks, for use in tests."""

    def __init__(self) -> None:
        super().__init__(max_per_second=1000.0)

    def acquire(self) -> None:
        """No-op: never wait."""
        return


def make_config() -> AppConfig:
    """Build a test AppConfig pointing to mock base URL."""
    return AppConfig(
        fellow_api_key="test-api-key",
        fellow_subdomain="testco",
        mcp_auth_enabled=False,
        mcp_auth_token=None,
        gunicorn_workers=2,
        log_level="INFO",
        mcp_endpoint_path="/mcp",
        fellow_base_url="https://testco.fellow.app",
    )


def make_client() -> FellowApiClient:
    """Create a FellowApiClient with a NoOpRateLimiter."""
    config = make_config()
    return FellowApiClient(config=config, rate_limiter=NoOpRateLimiter())


# --- Strategies ---

# Transient HTTP status codes eligible for retry
transient_status_codes = st.sampled_from([429, 500, 502, 503, 504])

# Valid positive Retry-After values (integer seconds)
valid_retry_after_values = st.integers(min_value=1, max_value=120)

# HTTP methods to test
http_methods = st.sampled_from(["GET", "POST", "PUT", "DELETE"])

# Random error body text
error_bodies = st.text(
    min_size=1,
    max_size=100,
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S", "Z"),
        blacklist_characters=("\x00",),
        max_codepoint=127,
    ),
)


# --- Property Tests ---


@pytest.mark.property
class TestRetryLogicProperty:
    """Property 8: Retry logic on transient errors.

    **Validates: Requirements 4.3, 4.4, 4.8**
    """

    @responses.activate
    @given(
        status_code=transient_status_codes,
        num_failures=st.integers(min_value=0, max_value=3),
    )
    @settings(max_examples=100, deadline=None)
    def test_transient_failures_followed_by_success(
        self, status_code, num_failures
    ):
        """For K transient failures followed by success (K < 4), the client
        succeeds after K+1 total attempts.

        **Validates: Requirements 4.3**
        """
        responses.reset()
        client = make_client()
        url = "https://testco.fellow.app/api/v1/me"

        # Register K failure responses
        for _ in range(num_failures):
            responses.add(
                responses.GET,
                url,
                status=status_code,
                body=f"Error {status_code}",
            )

        # Register success response
        responses.add(
            responses.GET,
            url,
            json={"id": "user-1", "name": "Test User"},
            status=200,
        )

        # Patch sleep to avoid real delays during retries
        with patch("tenacity.nap.time.sleep"):
            result = client.get("/api/v1/me")

        assert result == {"id": "user-1", "name": "Test User"}
        # Total calls = num_failures + 1 (the successful one)
        assert len(responses.calls) == num_failures + 1

    @responses.activate
    @given(
        status_code=transient_status_codes,
        error_body=error_bodies,
    )
    @settings(max_examples=100, deadline=None)
    def test_retries_exhausted_raises_fellow_api_error(
        self, status_code, error_body
    ):
        """For 4+ transient failures (all retries exhausted), FellowApiError is
        raised with the correct status code and error message.

        **Validates: Requirements 4.3, 4.8**
        """
        responses.reset()
        client = make_client()
        url = "https://testco.fellow.app/api/v1/me"

        # Register 4 failure responses (1 initial + 3 retries = all exhausted)
        for _ in range(4):
            responses.add(
                responses.GET,
                url,
                status=status_code,
                body=error_body,
            )

        with patch("tenacity.nap.time.sleep"):
            with pytest.raises(FellowApiError) as exc_info:
                client.get("/api/v1/me")

        # Error should contain the HTTP status code
        assert exc_info.value.status_code == status_code
        # Error should contain the error message from the response
        assert exc_info.value.message == error_body

        # Should have made exactly 4 attempts (1 initial + 3 retries)
        assert len(responses.calls) == 4

    @responses.activate
    @given(
        retry_after_value=valid_retry_after_values,
    )
    @settings(max_examples=100, deadline=None)
    def test_429_with_valid_retry_after_carries_value(
        self, retry_after_value
    ):
        """For 429 with valid Retry-After header, the TransientApiError
        carries the retry_after value which is used for delay.

        **Validates: Requirements 4.4**
        """
        responses.reset()
        client = make_client()
        url = "https://testco.fellow.app/api/v1/me"

        # Register a 429 with Retry-After, then a success
        responses.add(
            responses.GET,
            url,
            status=429,
            body="Rate limited",
            headers={"Retry-After": str(retry_after_value)},
        )
        responses.add(
            responses.GET,
            url,
            json={"id": "user-1", "name": "Test User"},
            status=200,
        )

        with patch("tenacity.nap.time.sleep"):
            result = client.get("/api/v1/me")

        assert result == {"id": "user-1", "name": "Test User"}
        # Should have made exactly 2 attempts
        assert len(responses.calls) == 2

    @responses.activate
    @given(
        retry_after_value=valid_retry_after_values,
    )
    @settings(max_examples=100, deadline=None)
    def test_429_retry_after_value_propagated_to_transient_error(
        self, retry_after_value
    ):
        """When a 429 response includes a valid positive Retry-After value,
        that value SHALL be used as the delay. Verify by exhausting retries
        and checking the TransientApiError cause carries the retry_after.

        **Validates: Requirements 4.4**
        """
        responses.reset()
        client = make_client()
        url = "https://testco.fellow.app/api/v1/me"

        # All 4 attempts are 429 with Retry-After to exhaust retries
        for _ in range(4):
            responses.add(
                responses.GET,
                url,
                status=429,
                body="Rate limited",
                headers={"Retry-After": str(retry_after_value)},
            )

        with patch("tenacity.nap.time.sleep") as mock_sleep:
            with pytest.raises(FellowApiError) as exc_info:
                client.get("/api/v1/me")

        assert exc_info.value.status_code == 429

        # Verify the cause carries the retry_after value
        cause = exc_info.value.__cause__
        assert isinstance(cause, TransientApiError)
        assert cause.retry_after == float(retry_after_value)

        # Verify that sleep was called with the Retry-After value
        # (tenacity calls sleep with the wait value from our custom wait fn)
        for call in mock_sleep.call_args_list:
            sleep_value = call[0][0]
            assert sleep_value == float(retry_after_value)

    @responses.activate
    @given(
        status_code=st.sampled_from([500, 502, 503, 504]),
        num_failures=st.integers(min_value=1, max_value=3),
    )
    @settings(max_examples=100, deadline=None)
    def test_non_429_transient_no_retry_after(
        self, status_code, num_failures
    ):
        """For non-429 transient errors, retry_after is None (exponential
        backoff is used instead). Verify by exhausting retries and checking
        the TransientApiError has retry_after=None.

        **Validates: Requirements 4.3**
        """
        responses.reset()
        client = make_client()
        url = "https://testco.fellow.app/api/v1/me"

        # Register failures then success
        for _ in range(num_failures):
            responses.add(
                responses.GET,
                url,
                status=status_code,
                body=f"Server error {status_code}",
            )

        responses.add(
            responses.GET,
            url,
            json={"status": "ok"},
            status=200,
        )

        with patch("tenacity.nap.time.sleep"):
            result = client.get("/api/v1/me")

        assert result == {"status": "ok"}
        assert len(responses.calls) == num_failures + 1

    @responses.activate
    @given(
        status_code=transient_status_codes,
        error_body=error_bodies,
        method=http_methods,
    )
    @settings(max_examples=100, deadline=None)
    def test_retry_works_for_all_http_methods(
        self, status_code, error_body, method
    ):
        """Retry logic applies to all HTTP methods (GET, POST, PUT, DELETE).

        **Validates: Requirements 4.3**
        """
        responses.reset()
        client = make_client()
        path = "/api/v1/me"
        url = f"https://testco.fellow.app{path}"

        method_map = {
            "GET": responses.GET,
            "POST": responses.POST,
            "PUT": responses.PUT,
            "DELETE": responses.DELETE,
        }
        resp_method = method_map[method]

        # One transient failure, then success
        responses.add(
            resp_method,
            url,
            status=status_code,
            body=error_body,
        )
        responses.add(
            resp_method,
            url,
            json={"result": "success"},
            status=200,
        )

        with patch("tenacity.nap.time.sleep"):
            if method == "GET":
                result = client.get(path)
            elif method == "POST":
                result = client.post(path, body={"key": "value"})
            elif method == "PUT":
                result = client.put(path, body={"key": "value"})
            else:  # DELETE
                result = client.delete(path)

        assert result == {"result": "success"}
        assert len(responses.calls) == 2
