"""Fellow.ai HTTP client with retry logic and rate limiting."""

import json
import time
from typing import Any, Optional

import requests
import structlog
from tenacity import (
    Retrying,
    RetryCallState,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.client.rate_limiter import TokenBucketRateLimiter
from app.config import AppConfig
from app.logging.metrics import RequestMetrics, UpstreamCallRecord

logger = structlog.get_logger(__name__)

# HTTP status codes that are considered transient and eligible for retry
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


class FellowApiError(Exception):
    """Raised when Fellow API returns a non-transient error after retries."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"Fellow API error {status_code}: {message}")


class TransientApiError(Exception):
    """Internal exception for transient errors that should trigger retry."""

    def __init__(
        self, status_code: int, message: str, retry_after: Optional[float] = None
    ) -> None:
        self.status_code = status_code
        self.message = message
        self.retry_after = retry_after
        super().__init__(f"Transient error {status_code}: {message}")


def _before_sleep_log(retry_state: RetryCallState) -> None:
    """Custom before_sleep callback that logs retry attempts at WARNING level.

    This is the default callback used when no metrics are available.
    """
    exception = retry_state.outcome.exception() if retry_state.outcome else None
    wait_duration = retry_state.next_action.sleep if retry_state.next_action else 0

    reason = "unknown"
    if isinstance(exception, TransientApiError):
        reason = f"HTTP {exception.status_code}: {exception.message}"
    elif isinstance(exception, requests.Timeout):
        reason = "request timeout"

    logger.warning(
        "fellow_api_retry",
        attempt=retry_state.attempt_number,
        wait_seconds=round(wait_duration, 2),
        reason=reason,
    )


def _make_before_sleep_with_metrics(
    metrics: Optional["RequestMetrics"],
) -> callable:
    """Create a before_sleep callback that has access to a RequestMetrics instance.

    When metrics is available, emits an enhanced Retry_Event with timing,
    size, and per-call detail fields. Also accumulates retry sleep time
    into metrics.retry_wait_ms.

    Args:
        metrics: Optional RequestMetrics instance to read/write during retries.

    Returns:
        A before_sleep callback function compatible with tenacity.
    """

    def _before_sleep_with_metrics(retry_state: RetryCallState) -> None:
        exception = retry_state.outcome.exception() if retry_state.outcome else None
        wait_duration = retry_state.next_action.sleep if retry_state.next_action else 0

        reason = "unknown"
        status_code: Optional[int] = None
        if isinstance(exception, TransientApiError):
            reason = f"HTTP {exception.status_code}: {exception.message}"
            status_code = exception.status_code
        elif isinstance(exception, requests.Timeout):
            reason = "request timeout"
            status_code = 408

        # Accumulate retry sleep time into metrics
        if metrics is not None:
            metrics.retry_wait_ms = round(
                metrics.retry_wait_ms + round(wait_duration * 1000, 2), 2
            )

        # Build enhanced log kwargs
        log_kwargs: dict[str, Any] = {
            "attempt": retry_state.attempt_number,
            "wait_seconds": round(wait_duration, 2),
            "reason": reason,
        }

        # Include status_code (omit if None per 6.4)
        if status_code is not None:
            log_kwargs["status_code"] = status_code

        if metrics is not None:
            # Timings: total_elapsed_ms only for retry events
            log_kwargs["timings"] = metrics.build_retry_timings_dict()

            # MCP request bytes
            log_kwargs["mcp_request_bytes"] = metrics.mcp_request_bytes

            # Cumulative upstream bytes
            log_kwargs["upstream_request_bytes"] = metrics.upstream_request_bytes
            log_kwargs["upstream_response_bytes"] = metrics.upstream_response_bytes

            # Per-call detail array - convert UpstreamCallRecord to dicts
            # Omit fields that are None (Requirement 6.4)
            upstream_calls = []
            for call in metrics.upstream_api_calls:
                call_dict: dict[str, Any] = {}
                if call.page is not None:
                    call_dict["page"] = call.page
                if call.duration_ms is not None:
                    call_dict["duration_ms"] = call.duration_ms
                if call.status_code is not None:
                    call_dict["status_code"] = call.status_code
                if call.request_bytes is not None:
                    call_dict["request_bytes"] = call.request_bytes
                if call.response_bytes is not None:
                    call_dict["response_bytes"] = call.response_bytes
                upstream_calls.append(call_dict)
            log_kwargs["upstream_api_calls"] = upstream_calls

        # Do NOT include mcp_response_bytes (not yet available per Req 6.2)

        logger.warning("fellow_api_retry", **log_kwargs)

    return _before_sleep_with_metrics


def _wait_with_retry_after(retry_state: RetryCallState) -> float:
    """Custom wait function that honors Retry-After header on 429 responses.

    Falls back to exponential backoff (initial=1s, multiplier=2) when
    Retry-After is not available.
    """
    exception = retry_state.outcome.exception() if retry_state.outcome else None

    # If we have a Retry-After value from a 429 response, use it
    if isinstance(exception, TransientApiError) and exception.retry_after is not None:
        return exception.retry_after

    # Fall back to exponential backoff: 1s, 2s, 4s
    exp_wait = wait_exponential(multiplier=1, min=1, max=8)
    return exp_wait(retry_state)


class FellowApiClient:
    """HTTP client for Fellow.ai API with retry and rate limiting.

    Handles:
    - Rate limiting via token bucket (3 req/s)
    - Exponential backoff retry on transient errors (429, 5xx, timeouts)
    - Retry-After header support for 429 responses
    - 30-second request timeout
    - X-API-KEY authentication header
    """

    def __init__(
        self,
        config: AppConfig,
        rate_limiter: Optional[TokenBucketRateLimiter] = None,
    ) -> None:
        self._base_url = config.fellow_base_url
        self._api_key = config.fellow_api_key
        self._timeout = 30.0
        self._rate_limiter = rate_limiter or TokenBucketRateLimiter(3.0)
        self._session = requests.Session()
        self._session.headers.update(
            {
                "X-API-KEY": self._api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    def get(
        self,
        path: str,
        params: Optional[dict] = None,
        metrics: Optional[RequestMetrics] = None,
    ) -> dict[str, Any]:
        """Send GET request to Fellow API.

        Args:
            path: API path (e.g., '/api/v1/me').
            params: Optional query parameters.
            metrics: Optional RequestMetrics to accumulate timing/size data.

        Returns:
            Parsed JSON response body.

        Raises:
            FellowApiError: On non-transient failure after retries.
        """
        return self._request("GET", path, params=params, metrics=metrics)

    def post(
        self,
        path: str,
        body: Optional[dict] = None,
        metrics: Optional[RequestMetrics] = None,
    ) -> dict[str, Any]:
        """Send POST request to Fellow API.

        Args:
            path: API path.
            body: Optional JSON request body.
            metrics: Optional RequestMetrics to accumulate timing/size data.

        Returns:
            Parsed JSON response body.

        Raises:
            FellowApiError: On non-transient failure after retries.
        """
        return self._request("POST", path, json_body=body, metrics=metrics)

    def put(
        self,
        path: str,
        body: dict,
        metrics: Optional[RequestMetrics] = None,
    ) -> dict[str, Any]:
        """Send PUT request to Fellow API.

        Args:
            path: API path.
            body: JSON request body.
            metrics: Optional RequestMetrics to accumulate timing/size data.

        Returns:
            Parsed JSON response body.

        Raises:
            FellowApiError: On non-transient failure after retries.
        """
        return self._request("PUT", path, json_body=body, metrics=metrics)

    def delete(
        self,
        path: str,
        metrics: Optional[RequestMetrics] = None,
    ) -> dict[str, Any]:
        """Send DELETE request to Fellow API.

        Args:
            path: API path.
            metrics: Optional RequestMetrics to accumulate timing/size data.

        Returns:
            Parsed JSON response body.

        Raises:
            FellowApiError: On non-transient failure after retries.
        """
        return self._request("DELETE", path, metrics=metrics)

    def health_check(self) -> bool:
        """Check if Fellow API is reachable.

        Makes a GET request to /api/v1/me to verify connectivity.

        Returns:
            True if the API responds successfully, False otherwise.
        """
        try:
            self._rate_limiter.acquire()
            response = self._session.get(
                f"{self._base_url}/api/v1/me",
                timeout=self._timeout,
            )
            return response.status_code < 500
        except (requests.RequestException, Exception):
            return False

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
        metrics: Optional[RequestMetrics] = None,
    ) -> dict[str, Any]:
        """Execute an HTTP request with rate limiting and retry logic.

        This method acquires a rate limiter token before each attempt,
        then delegates to the retry-decorated _do_request method.
        Uses a metrics-aware before_sleep callback when metrics are provided.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            path: API path relative to base URL.
            params: Optional query parameters.
            json_body: Optional JSON body for POST/PUT.
            metrics: Optional RequestMetrics to accumulate timing/size data.

        Returns:
            Parsed JSON response body.

        Raises:
            FellowApiError: On non-transient failure after retries exhausted.
        """
        # Create a metrics-aware before_sleep callback
        before_sleep_cb = _make_before_sleep_with_metrics(metrics)

        retryer = Retrying(
            stop=stop_after_attempt(4),  # 1 initial + 3 retries
            wait=_wait_with_retry_after,
            retry=retry_if_exception_type((TransientApiError, requests.Timeout)),
            before_sleep=before_sleep_cb,
            reraise=True,
        )

        try:
            return retryer(
                self._do_request_with_retry,
                method, path, params, json_body, metrics,
            )
        except TransientApiError as e:
            if metrics is not None:
                metrics.upstream_status_code = e.status_code
            raise FellowApiError(e.status_code, e.message) from e
        except requests.Timeout as e:
            if metrics is not None:
                metrics.upstream_status_code = 408
            raise FellowApiError(408, "Request timed out after retries") from e

    def _do_request_with_retry(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
        metrics: Optional[RequestMetrics] = None,
    ) -> dict[str, Any]:
        """Execute a single HTTP request attempt with retry decorator.

        Called by _request(). The tenacity decorator handles retries
        on transient errors and timeouts.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            path: API path relative to base URL.
            params: Optional query parameters.
            json_body: Optional JSON body for POST/PUT.
            metrics: Optional RequestMetrics to accumulate timing/size data.

        Raises:
            TransientApiError: On transient HTTP errors (429, 5xx).
            requests.Timeout: On request timeout.
            FellowApiError: On non-transient HTTP errors (non-retryable 4xx).
        """
        # Measure rate limiter wait time
        rate_limiter_start = time.time()
        self._rate_limiter.acquire()
        if metrics is not None:
            rate_limiter_elapsed = round(
                (time.time() - rate_limiter_start) * 1000, 2
            )
            metrics.rate_limiter_wait_ms = round(
                metrics.rate_limiter_wait_ms + rate_limiter_elapsed, 2
            )

        # Compute request bytes
        request_bytes = 0
        if json_body is not None:
            request_bytes = len(json.dumps(json_body).encode("utf-8"))
        if metrics is not None:
            metrics.upstream_request_bytes += request_bytes

        url = f"{self._base_url}{path}"
        logger.debug(
            "fellow_api_request",
            http_method=method,
            url=url,
            params=params,
            body_keys=list(json_body.keys()) if json_body else None,
        )

        # Measure HTTP round-trip time
        http_start = time.time()
        try:
            response = self._session.request(
                method=method,
                url=url,
                params=params,
                json=json_body,
                timeout=self._timeout,
            )
        except requests.Timeout:
            # Record call even on timeout
            http_elapsed = round((time.time() - http_start) * 1000, 2)
            if metrics is not None:
                metrics.upstream_api_ms = round(
                    metrics.upstream_api_ms + http_elapsed, 2
                )
                metrics.upstream_api_calls.append(
                    UpstreamCallRecord(
                        page=len(metrics.upstream_api_calls) + 1,
                        duration_ms=http_elapsed,
                        status_code=0,
                        request_bytes=request_bytes,
                        response_bytes=0,
                    )
                )
            logger.debug(
                "fellow_api_call",
                http_method=method,
                url=url,
                duration_ms=http_elapsed,
                status_code=0,
                request_bytes=request_bytes,
                response_bytes=0,
            )
            raise

        http_elapsed = round((time.time() - http_start) * 1000, 2)

        # Compute response bytes
        response_bytes = len(response.content)

        if metrics is not None:
            metrics.upstream_api_ms = round(
                metrics.upstream_api_ms + http_elapsed, 2
            )
            metrics.upstream_response_bytes += response_bytes
            metrics.upstream_api_calls.append(
                UpstreamCallRecord(
                    page=len(metrics.upstream_api_calls) + 1,
                    duration_ms=http_elapsed,
                    status_code=response.status_code,
                    request_bytes=request_bytes,
                    response_bytes=response_bytes,
                )
            )
            metrics.upstream_status_code = response.status_code

        logger.debug(
            "fellow_api_call",
            http_method=method,
            url=url,
            duration_ms=http_elapsed,
            status_code=response.status_code,
            request_bytes=request_bytes,
            response_bytes=response_bytes,
        )

        if response.status_code in TRANSIENT_STATUS_CODES:
            retry_after = None
            if response.status_code == 429:
                retry_after_header = response.headers.get("Retry-After")
                if retry_after_header:
                    try:
                        retry_after = float(retry_after_header)
                        if retry_after <= 0:
                            retry_after = None
                    except (ValueError, TypeError):
                        retry_after = None

            error_message = response.text or f"HTTP {response.status_code}"
            raise TransientApiError(
                status_code=response.status_code,
                message=error_message,
                retry_after=retry_after,
            )

        if response.status_code >= 400:
            error_message = response.text or f"HTTP {response.status_code}"
            raise FellowApiError(
                status_code=response.status_code,
                message=error_message,
            )

        # Handle empty responses (e.g., 204 No Content)
        if response.status_code == 204 or not response.content:
            return {}

        return response.json()
