"""Property-based tests for rate limiter enforcement.

# Feature: fellow-mcp-server, Property 9: Rate limiter enforces 3 requests per second

For any sequence of N requests submitted simultaneously where N > 3,
the total elapsed time to complete all requests SHALL be at least
(N - 3) / 3 seconds, ensuring no more than 3 requests per second reach
the Fellow API.
"""

import time
import threading

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.client.rate_limiter import TokenBucketRateLimiter


# --- Strategies ---

# Number of simultaneous requests (must be > 3 to observe throttling)
num_requests = st.integers(min_value=4, max_value=15)


# --- Property Tests ---


@pytest.mark.property
class TestRateLimiterProperty:
    """Property 9: Rate limiter enforces 3 requests per second.

    **Validates: Requirements 4.5**
    """

    @given(n=num_requests)
    @settings(max_examples=30, deadline=None)
    def test_elapsed_time_enforces_rate_limit(self, n: int):
        """For N > 3 simultaneous requests, total elapsed time SHALL be
        at least (N - 3) / 3 seconds.

        **Validates: Requirements 4.5**
        """
        limiter = TokenBucketRateLimiter(max_per_second=3.0)

        # Use a barrier to ensure all threads start simultaneously
        barrier = threading.Barrier(n)
        completion_times: list[float] = []
        lock = threading.Lock()

        def worker():
            barrier.wait()
            limiter.acquire()
            with lock:
                completion_times.append(time.monotonic())

        start = time.monotonic()
        threads = [threading.Thread(target=worker) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        elapsed = max(completion_times) - start

        # The minimum expected time: first 3 requests go through immediately
        # (bucket starts full), remaining (N-3) requests must wait for tokens
        # at a rate of 3 per second.
        expected_minimum = (n - 3) / 3.0

        # Allow 10% tolerance for timing imprecision
        assert elapsed >= expected_minimum * 0.9, (
            f"N={n}: elapsed {elapsed:.4f}s < expected minimum "
            f"{expected_minimum * 0.9:.4f}s (90% of {expected_minimum:.4f}s)"
        )
