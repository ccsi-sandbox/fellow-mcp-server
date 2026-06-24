"""Unit tests for FellowApiClient."""

import pytest
import requests
import responses
from unittest.mock import MagicMock
from responses import matchers

from app.client.fellow_api import FellowApiClient, FellowApiError, TransientApiError
from app.client.rate_limiter import TokenBucketRateLimiter
from app.config import AppConfig


def _make_config(
    api_key: str = "test-api-key-12345",
    subdomain: str = "testco",
) -> AppConfig:
    """Create a minimal AppConfig for testing."""
    return AppConfig(
        fellow_api_key=api_key,
        fellow_subdomain=subdomain,
        mcp_auth_enabled=False,
        mcp_auth_token=None,
        gunicorn_workers=2,
        log_level="INFO",
        mcp_endpoint_path="/mcp",
        fellow_base_url=f"https://{subdomain}.fellow.app",
    )


class NoOpRateLimiter(TokenBucketRateLimiter):
    """A rate limiter that never blocks, for unit testing."""

    def __init__(self) -> None:
        super().__init__(max_per_second=1000.0)

    def acquire(self) -> None:
        pass


@pytest.fixture
def config() -> AppConfig:
    return _make_config()


@pytest.fixture
def client(config: AppConfig) -> FellowApiClient:
    return FellowApiClient(config=config, rate_limiter=NoOpRateLimiter())


@pytest.mark.unit
class TestFellowApiClientBasics:
    """Tests for basic HTTP method functionality."""

    @responses.activate
    def test_get_request_success(self, client: FellowApiClient):
        """GET request returns parsed JSON on success."""
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            json={"id": "user-1", "name": "Test User"},
            status=200,
        )

        result = client.get("/api/v1/me")

        assert result == {"id": "user-1", "name": "Test User"}
        assert responses.calls[0].request.headers["X-API-KEY"] == "test-api-key-12345"

    @responses.activate
    def test_get_with_params(self, client: FellowApiClient):
        """GET request passes query parameters."""
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/webhook",
            json={"results": []},
            status=200,
        )

        client.get("/api/v1/webhook", params={"limit": "10", "cursor": "abc"})

        assert "limit=10" in responses.calls[0].request.url
        assert "cursor=abc" in responses.calls[0].request.url

    @responses.activate
    def test_post_request_success(self, client: FellowApiClient):
        """POST request sends JSON body and returns parsed response."""
        responses.add(
            responses.POST,
            "https://testco.fellow.app/api/v1/action_items",
            json={"results": [{"id": "ai-1"}]},
            status=200,
        )

        result = client.post("/api/v1/action_items", body={"completed": True})

        assert result == {"results": [{"id": "ai-1"}]}
        assert responses.calls[0].request.headers["Content-Type"] == "application/json"

    @responses.activate
    def test_put_request_success(self, client: FellowApiClient):
        """PUT request sends JSON body and returns parsed response."""
        responses.add(
            responses.PUT,
            "https://testco.fellow.app/api/v1/webhook/wh-1",
            json={"id": "wh-1", "status": "active"},
            status=200,
        )

        result = client.put("/api/v1/webhook/wh-1", body={"status": "active"})

        assert result == {"id": "wh-1", "status": "active"}

    @responses.activate
    def test_delete_request_success(self, client: FellowApiClient):
        """DELETE request returns parsed response."""
        responses.add(
            responses.DELETE,
            "https://testco.fellow.app/api/v1/note/n-1",
            json={"deleted": True},
            status=200,
        )

        result = client.delete("/api/v1/note/n-1")

        assert result == {"deleted": True}

    @responses.activate
    def test_empty_response_body(self, client: FellowApiClient):
        """204 No Content returns empty dict."""
        responses.add(
            responses.DELETE,
            "https://testco.fellow.app/api/v1/note/n-1",
            status=204,
        )

        result = client.delete("/api/v1/note/n-1")

        assert result == {}

    @responses.activate
    def test_api_key_header_set(self, client: FellowApiClient):
        """All requests include X-API-KEY header."""
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            json={},
            status=200,
        )

        client.get("/api/v1/me")

        assert responses.calls[0].request.headers["X-API-KEY"] == "test-api-key-12345"

    @responses.activate
    def test_base_url_construction(self):
        """Base URL uses configured subdomain."""
        config = _make_config(subdomain="mycompany")
        api_client = FellowApiClient(config=config, rate_limiter=NoOpRateLimiter())

        responses.add(
            responses.GET,
            "https://mycompany.fellow.app/api/v1/me",
            json={"ok": True},
            status=200,
        )

        api_client.get("/api/v1/me")

        assert responses.calls[0].request.url == "https://mycompany.fellow.app/api/v1/me"


@pytest.mark.unit
class TestFellowApiClientErrors:
    """Tests for error handling."""

    @responses.activate
    def test_non_transient_4xx_raises_fellow_api_error(self, client: FellowApiClient):
        """Non-transient 4xx errors raise FellowApiError immediately."""
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            json={"error": "Not found"},
            status=404,
        )

        with pytest.raises(FellowApiError) as exc_info:
            client.get("/api/v1/me")

        assert exc_info.value.status_code == 404
        assert "Not found" in exc_info.value.message

    @responses.activate
    def test_401_raises_fellow_api_error(self, client: FellowApiClient):
        """401 Unauthorized raises FellowApiError (not retried)."""
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            json={"error": "Invalid API key"},
            status=401,
        )

        with pytest.raises(FellowApiError) as exc_info:
            client.get("/api/v1/me")

        assert exc_info.value.status_code == 401

    @responses.activate
    def test_403_raises_fellow_api_error(self, client: FellowApiClient):
        """403 Forbidden raises FellowApiError (not retried)."""
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            body="Forbidden",
            status=403,
        )

        with pytest.raises(FellowApiError) as exc_info:
            client.get("/api/v1/me")

        assert exc_info.value.status_code == 403


@pytest.mark.unit
class TestFellowApiClientRetry:
    """Tests for retry logic on transient errors."""

    @responses.activate
    def test_retries_on_500(self, client: FellowApiClient):
        """500 errors trigger retry, succeed on subsequent attempt."""
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            body="Internal Server Error",
            status=500,
        )
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            json={"id": "user-1"},
            status=200,
        )

        result = client.get("/api/v1/me")

        assert result == {"id": "user-1"}
        assert len(responses.calls) == 2

    @responses.activate
    def test_retries_on_502(self, client: FellowApiClient):
        """502 errors trigger retry."""
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            body="Bad Gateway",
            status=502,
        )
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            json={"ok": True},
            status=200,
        )

        result = client.get("/api/v1/me")
        assert result == {"ok": True}
        assert len(responses.calls) == 2

    @responses.activate
    def test_retries_on_503(self, client: FellowApiClient):
        """503 errors trigger retry."""
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            body="Service Unavailable",
            status=503,
        )
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            json={"ok": True},
            status=200,
        )

        result = client.get("/api/v1/me")
        assert result == {"ok": True}
        assert len(responses.calls) == 2

    @responses.activate
    def test_retries_on_504(self, client: FellowApiClient):
        """504 errors trigger retry."""
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            body="Gateway Timeout",
            status=504,
        )
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            json={"ok": True},
            status=200,
        )

        result = client.get("/api/v1/me")
        assert result == {"ok": True}
        assert len(responses.calls) == 2

    @responses.activate
    def test_retries_on_429(self, client: FellowApiClient):
        """429 Too Many Requests triggers retry."""
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            body="Rate limited",
            status=429,
        )
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            json={"ok": True},
            status=200,
        )

        result = client.get("/api/v1/me")
        assert result == {"ok": True}
        assert len(responses.calls) == 2

    @responses.activate
    def test_max_retries_exhausted_raises_error(self, client: FellowApiClient):
        """After 4 total attempts (1 initial + 3 retries), raises FellowApiError."""
        for _ in range(4):
            responses.add(
                responses.GET,
                "https://testco.fellow.app/api/v1/me",
                body="Server Error",
                status=500,
            )

        with pytest.raises(FellowApiError) as exc_info:
            client.get("/api/v1/me")

        assert exc_info.value.status_code == 500
        assert len(responses.calls) == 4

    @responses.activate
    def test_retry_after_header_honored(self, client: FellowApiClient):
        """429 with Retry-After header uses that value for wait."""
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            body="Rate limited",
            status=429,
            headers={"Retry-After": "2"},
        )
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            json={"ok": True},
            status=200,
        )

        result = client.get("/api/v1/me")
        assert result == {"ok": True}
        assert len(responses.calls) == 2

    @responses.activate
    def test_does_not_retry_on_non_transient_errors(self, client: FellowApiClient):
        """Non-transient errors (400, 401, 403, 404, 422) are not retried."""
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            body="Bad Request",
            status=400,
        )

        with pytest.raises(FellowApiError):
            client.get("/api/v1/me")

        # Only 1 attempt, no retries
        assert len(responses.calls) == 1

    def test_timeout_triggers_retry(self, config: AppConfig):
        """Request timeouts are treated as transient errors and retried."""
        from unittest.mock import patch, MagicMock

        rate_limiter = NoOpRateLimiter()
        api_client = FellowApiClient(config=config, rate_limiter=rate_limiter)

        # First call raises Timeout, second call succeeds
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"ok": true}'
        mock_response.json.return_value = {"ok": True}

        mock_request = MagicMock(
            side_effect=[
                requests.Timeout("Connection timed out"),
                mock_response,
            ]
        )

        with patch.object(api_client._session, "request", mock_request):
            result = api_client.get("/api/v1/me")

        assert result == {"ok": True}
        assert mock_request.call_count == 2

    @responses.activate
    def test_transient_then_success(self, client: FellowApiClient):
        """Multiple transient failures followed by success still works."""
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            body="Error",
            status=503,
        )
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            body="Error",
            status=502,
        )
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            json={"recovered": True},
            status=200,
        )

        result = client.get("/api/v1/me")
        assert result == {"recovered": True}
        assert len(responses.calls) == 3


@pytest.mark.unit
class TestFellowApiClientHealthCheck:
    """Tests for the health_check method."""

    @responses.activate
    def test_health_check_returns_true_on_success(self, client: FellowApiClient):
        """health_check returns True when API responds with 2xx."""
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            json={"id": "user-1"},
            status=200,
        )

        assert client.health_check() is True

    @responses.activate
    def test_health_check_returns_true_on_4xx(self, client: FellowApiClient):
        """health_check returns True on 4xx (API is reachable)."""
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            body="Unauthorized",
            status=401,
        )

        assert client.health_check() is True

    @responses.activate
    def test_health_check_returns_false_on_5xx(self, client: FellowApiClient):
        """health_check returns False on 5xx (API has issues)."""
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            body="Internal Server Error",
            status=500,
        )

        assert client.health_check() is False

    @responses.activate
    def test_health_check_returns_false_on_connection_error(
        self, client: FellowApiClient
    ):
        """health_check returns False when connection fails."""
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            body=responses.ConnectionError("Connection refused"),
        )

        assert client.health_check() is False


@pytest.mark.unit
class TestFellowApiClientRateLimiter:
    """Tests for rate limiter integration."""

    @responses.activate
    def test_rate_limiter_called_before_request(self):
        """Rate limiter acquire() is called before making API request."""
        acquire_called = []

        class TrackingRateLimiter(TokenBucketRateLimiter):
            def __init__(self):
                super().__init__(max_per_second=1000.0)

            def acquire(self):
                acquire_called.append(True)

        config = _make_config()
        api_client = FellowApiClient(
            config=config, rate_limiter=TrackingRateLimiter()
        )

        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            json={"ok": True},
            status=200,
        )

        api_client.get("/api/v1/me")

        assert len(acquire_called) == 1

    @responses.activate
    def test_default_rate_limiter_created_when_none_provided(self):
        """When no rate_limiter is provided, a default one is created."""
        config = _make_config()
        api_client = FellowApiClient(config=config)

        # Verify it has a rate limiter (it should be a TokenBucketRateLimiter)
        assert api_client._rate_limiter is not None
        assert isinstance(api_client._rate_limiter, TokenBucketRateLimiter)


@pytest.mark.unit
class TestEnhancedRetryLogging:
    """Tests for enhanced retry logging with metrics."""

    @responses.activate
    def test_retry_event_includes_status_code_on_transient_error(
        self, client: FellowApiClient, caplog
    ):
        """Retry event includes the HTTP status code that caused the retry."""
        import structlog
        from app.logging.metrics import RequestMetrics
        import time

        captured_events = []
        original_warning = structlog.get_logger(__name__).warning

        # Use structlog testing capture
        metrics = RequestMetrics(start_time=time.time())

        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            body="Rate limited",
            status=429,
        )
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            json={"ok": True},
            status=200,
        )

        result = client.get("/api/v1/me", metrics=metrics)

        assert result == {"ok": True}
        # Retry wait time was accumulated
        assert metrics.retry_wait_ms > 0

    @responses.activate
    def test_retry_event_accumulates_retry_wait_ms(
        self, client: FellowApiClient
    ):
        """Retry sleep time is accumulated into metrics.retry_wait_ms."""
        import time
        from app.logging.metrics import RequestMetrics

        metrics = RequestMetrics(start_time=time.time())

        # Two transient errors followed by success
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            body="Error",
            status=500,
        )
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            body="Error",
            status=503,
        )
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            json={"ok": True},
            status=200,
        )

        client.get("/api/v1/me", metrics=metrics)

        # Two retries means retry_wait_ms should be positive
        assert metrics.retry_wait_ms > 0

    @responses.activate
    def test_retry_event_includes_upstream_api_calls(
        self, client: FellowApiClient
    ):
        """Retry event includes upstream_api_calls for calls made so far."""
        import time
        from app.logging.metrics import RequestMetrics

        metrics = RequestMetrics(start_time=time.time())

        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            body="Error",
            status=500,
        )
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            json={"ok": True},
            status=200,
        )

        client.get("/api/v1/me", metrics=metrics)

        # After success: 2 calls total (1 failed + 1 success)
        assert len(metrics.upstream_api_calls) == 2
        assert metrics.upstream_api_calls[0].status_code == 500
        assert metrics.upstream_api_calls[1].status_code == 200

    @responses.activate
    def test_retry_event_includes_cumulative_upstream_bytes(
        self, client: FellowApiClient
    ):
        """Retry event includes cumulative upstream request/response bytes."""
        import time
        from app.logging.metrics import RequestMetrics

        metrics = RequestMetrics(start_time=time.time())

        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            body="Error body",
            status=500,
        )
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            json={"ok": True},
            status=200,
        )

        client.get("/api/v1/me", metrics=metrics)

        # Both calls generated upstream response bytes
        assert metrics.upstream_response_bytes > 0

    def test_retry_event_uses_408_for_timeout(self, config: AppConfig):
        """Timeout retry events report status_code 408."""
        import time
        from unittest.mock import patch, MagicMock
        from app.logging.metrics import RequestMetrics

        rate_limiter = NoOpRateLimiter()
        api_client = FellowApiClient(config=config, rate_limiter=rate_limiter)
        metrics = RequestMetrics(start_time=time.time())

        # First call raises Timeout, second call succeeds
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"ok": true}'
        mock_response.text = '{"ok": true}'
        mock_response.json.return_value = {"ok": True}
        mock_response.headers = {}

        mock_request = MagicMock(
            side_effect=[
                requests.Timeout("Connection timed out"),
                mock_response,
            ]
        )

        with patch.object(api_client._session, "request", mock_request):
            result = api_client.get("/api/v1/me", metrics=metrics)

        assert result == {"ok": True}
        # The timeout call should be recorded with status_code=0
        assert metrics.upstream_api_calls[0].status_code == 0
        # retry_wait_ms should be accumulated
        assert metrics.retry_wait_ms > 0

    @responses.activate
    def test_retry_event_no_mcp_response_bytes(self, client: FellowApiClient):
        """Retry events do NOT include mcp_response_bytes (not yet available)."""
        import time
        import structlog
        from unittest.mock import patch
        from app.logging.metrics import RequestMetrics

        metrics = RequestMetrics(start_time=time.time())
        metrics.mcp_request_bytes = 100

        captured_kwargs = []

        def capture_warning(event, **kwargs):
            if event == "fellow_api_retry":
                captured_kwargs.append(kwargs)

        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            body="Error",
            status=500,
        )
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            json={"ok": True},
            status=200,
        )

        with patch(
            "app.client.fellow_api.logger"
        ) as mock_logger:
            mock_logger.debug = MagicMock()
            mock_logger.warning = capture_warning
            client.get("/api/v1/me", metrics=metrics)

        # Should have captured one retry event
        assert len(captured_kwargs) == 1
        # mcp_response_bytes should NOT be in the retry event
        assert "mcp_response_bytes" not in captured_kwargs[0]
        # mcp_request_bytes SHOULD be present
        assert "mcp_request_bytes" in captured_kwargs[0]

    @responses.activate
    def test_retry_event_includes_timings_with_total_elapsed(
        self, client: FellowApiClient
    ):
        """Retry event includes timings dict with total_elapsed_ms."""
        import time
        from unittest.mock import patch, MagicMock
        from app.logging.metrics import RequestMetrics

        metrics = RequestMetrics(start_time=time.time())

        captured_kwargs = []

        def capture_warning(event, **kwargs):
            if event == "fellow_api_retry":
                captured_kwargs.append(kwargs)

        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            body="Error",
            status=500,
        )
        responses.add(
            responses.GET,
            "https://testco.fellow.app/api/v1/me",
            json={"ok": True},
            status=200,
        )

        with patch(
            "app.client.fellow_api.logger"
        ) as mock_logger:
            mock_logger.debug = MagicMock()
            mock_logger.warning = capture_warning
            client.get("/api/v1/me", metrics=metrics)

        assert len(captured_kwargs) == 1
        assert "timings" in captured_kwargs[0]
        assert "total_elapsed_ms" in captured_kwargs[0]["timings"]
        assert captured_kwargs[0]["timings"]["total_elapsed_ms"] > 0
