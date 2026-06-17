"""Token bucket rate limiter for Fellow.ai API requests."""

import threading
import time

import structlog

logger = structlog.get_logger(__name__)


class TokenBucketRateLimiter:
    """Thread-safe token bucket rate limiter.

    Enforces max_requests_per_second by blocking callers until
    a token is available. The bucket starts full and refills at
    the configured rate.
    """

    def __init__(self, max_per_second: float = 3.0) -> None:
        self._max_tokens: float = max_per_second
        self._tokens: float = max_per_second
        self._last_refill: float = time.monotonic()
        self._lock: threading.Lock = threading.Lock()

    def acquire(self) -> None:
        """Block until a token is available, then consume one."""
        while True:
            with self._lock:
                self._refill()

                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return

                # Calculate time needed to get 1 token and reserve it
                # by deducting the token now (going negative)
                deficit = 1.0 - self._tokens
                wait_time = deficit / self._max_tokens
                self._tokens -= 1.0

            # Sleep outside the lock — the token is already reserved
            logger.debug(
                "rate_limiter_wait",
                tokens_available=round(self._tokens + 1.0, 3),
                wait_seconds=round(wait_time, 4),
                max_tokens=self._max_tokens,
            )
            time.sleep(wait_time)
            return

    def _refill(self) -> None:
        """Refill tokens based on elapsed time since last refill."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(
            self._max_tokens,
            self._tokens + elapsed * self._max_tokens,
        )
        self._last_refill = now
