"""Request metrics collection for structured timing and size logging.

Provides dataclasses that accumulate timing, size, and status data
as a request flows through the handler pipeline.
"""

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class UpstreamCallRecord:
    """Record of a single upstream API call."""

    page: int
    duration_ms: float
    status_code: int
    request_bytes: int
    response_bytes: int


@dataclass
class RequestMetrics:
    """Accumulates timing and size metrics throughout a request lifecycle.

    Created at the start of request handling and threaded through the
    call chain to collect per-step timing, byte sizes, and status codes.
    """

    # Wall-clock start
    start_time: float

    # Step durations (milliseconds, rounded to 2dp)
    validation_ms: float = 0.0
    rate_limiter_wait_ms: float = 0.0
    upstream_api_ms: float = 0.0
    retry_wait_ms: float = 0.0
    serialization_ms: float = 0.0
    overhead_ms: float = 0.0

    # Size metrics (bytes)
    mcp_request_bytes: int = 0
    mcp_response_bytes: int = 0
    upstream_request_bytes: int = 0
    upstream_response_bytes: int = 0

    # Status tracking
    upstream_status_code: Optional[int] = None

    # Per-call detail
    upstream_api_calls: list[UpstreamCallRecord] = field(default_factory=list)

    def compute_total_ms(self) -> float:
        """Compute total elapsed time from start to now.

        Returns:
            Wall-clock elapsed milliseconds rounded to 2 decimal places.
        """
        return round((time.time() - self.start_time) * 1000, 2)

    def compute_overhead_ms(self) -> float:
        """Compute overhead as total minus sum of known steps.

        Overhead absorbs any unaccounted framework time (context switching,
        Python interpreter overhead, etc.) to maintain the sum invariant.

        Returns:
            Non-negative overhead in milliseconds, rounded to 2 decimal places.
        """
        total = self.compute_total_ms()
        known = (
            self.validation_ms
            + self.rate_limiter_wait_ms
            + self.upstream_api_ms
            + self.retry_wait_ms
            + self.serialization_ms
        )
        return round(max(0.0, total - known), 2)

    def build_timings_dict(self) -> dict:
        """Build the timings object for log emission.

        Computes overhead and total, then returns the nested structure
        expected by the Tool_Call_Event log format.

        Returns:
            Dict with ``total_ms`` and ``steps`` sub-dict containing
            all step duration fields.
        """
        self.overhead_ms = self.compute_overhead_ms()
        total_ms = self.compute_total_ms()
        return {
            "total_ms": total_ms,
            "steps": {
                "validation_ms": self.validation_ms,
                "rate_limiter_wait_ms": self.rate_limiter_wait_ms,
                "upstream_api_ms": self.upstream_api_ms,
                "retry_wait_ms": self.retry_wait_ms,
                "serialization_ms": self.serialization_ms,
                "overhead_ms": self.overhead_ms,
            },
        }

    def build_retry_timings_dict(self) -> dict:
        """Build timings object for retry events (total_elapsed_ms only).

        Returns:
            Dict with ``total_elapsed_ms`` representing cumulative
            wall-clock time from request start.
        """
        return {"total_elapsed_ms": self.compute_total_ms()}
