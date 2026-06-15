"""Fellow.ai HTTP client with retry logic and rate limiting."""

import time
from typing import Any, Optional

import requests
import structlog
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.client.rate_limiter import TokenBucketRateLimiter
from app.config import AppConfig

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
    """Custom before_sleep callback that logs retry attempts at WARNING level."""
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

    def get(self, path: str, params: Optional[dict] = None) -> dict[str, Any]:
        """Send GET request to Fellow API.

        Args:
            path: API path (e.g., '/api/v1/me').
            params: Optional query parameters.

        Returns:
            Parsed JSON response body.

        Raises:
            FellowApiError: On non-transient failure after retries.
        """
        return self._request("GET", path, params=params)

    def post(self, path: str, body: Optional[dict] = None) -> dict[str, Any]:
        """Send POST request to Fellow API.

        Args:
            path: API path.
            body: Optional JSON request body.

        Returns:
            Parsed JSON response body.

        Raises:
            FellowApiError: On non-transient failure after retries.
        """
        return self._request("POST", path, json_body=body)

    def put(self, path: str, body: dict) -> dict[str, Any]:
        """Send PUT request to Fellow API.

        Args:
            path: API path.
            body: JSON request body.

        Returns:
            Parsed JSON response body.

        Raises:
            FellowApiError: On non-transient failure after retries.
        """
        return self._request("PUT", path, json_body=body)

    def delete(self, path: str) -> dict[str, Any]:
        """Send DELETE request to Fellow API.

        Args:
            path: API path.

        Returns:
            Parsed JSON response body.

        Raises:
            FellowApiError: On non-transient failure after retries.
        """
        return self._request("DELETE", path)

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
    ) -> dict[str, Any]:
        """Execute an HTTP request with rate limiting and retry logic.

        This method acquires a rate limiter token before each attempt,
        then delegates to the retry-decorated _do_request method.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            path: API path relative to base URL.
            params: Optional query parameters.
            json_body: Optional JSON body for POST/PUT.

        Returns:
            Parsed JSON response body.

        Raises:
            FellowApiError: On non-transient failure after retries exhausted.
        """
        try:
            return self._do_request_with_retry(method, path, params, json_body)
        except TransientApiError as e:
            raise FellowApiError(e.status_code, e.message) from e
        except requests.Timeout as e:
            raise FellowApiError(408, "Request timed out after retries") from e

    @retry(
        stop=stop_after_attempt(4),  # 1 initial + 3 retries
        wait=_wait_with_retry_after,
        retry=retry_if_exception_type((TransientApiError, requests.Timeout)),
        before_sleep=_before_sleep_log,
        reraise=True,
    )
    def _do_request_with_retry(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
    ) -> dict[str, Any]:
        """Execute a single HTTP request attempt with retry decorator.

        Called by _request(). The tenacity decorator handles retries
        on transient errors and timeouts.

        Raises:
            TransientApiError: On transient HTTP errors (429, 5xx).
            requests.Timeout: On request timeout.
            FellowApiError: On non-transient HTTP errors (non-retryable 4xx).
        """
        self._rate_limiter.acquire()

        url = f"{self._base_url}{path}"
        response = self._session.request(
            method=method,
            url=url,
            params=params,
            json=json_body,
            timeout=self._timeout,
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
