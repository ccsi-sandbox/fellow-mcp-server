"""Unit tests for TokenBucketRateLimiter."""

import threading
import time

import pytest

from app.client.rate_limiter import TokenBucketRateLimiter


@pytest.mark.unit
class TestTokenBucketRateLimiter:
    """Tests for the token bucket rate limiter."""

    def test_initial_tokens_available_immediately(self):
        """First N requests (up to max_per_second) should not block."""
        limiter = TokenBucketRateLimiter(max_per_second=3.0)

        start = time.monotonic()
        for _ in range(3):
            limiter.acquire()
        elapsed = time.monotonic() - start

        # 3 tokens available immediately, should be near-instant
        assert elapsed < 0.1

    def test_blocks_when_tokens_exhausted(self):
        """After exhausting tokens, acquire should block until refill."""
        limiter = TokenBucketRateLimiter(max_per_second=3.0)

        # Exhaust all 3 tokens
        for _ in range(3):
            limiter.acquire()

        # Next acquire should block ~0.33s (1 token / 3 tokens-per-sec)
        start = time.monotonic()
        limiter.acquire()
        elapsed = time.monotonic() - start

        assert elapsed >= 0.25  # Allow some timing slack
        assert elapsed < 0.6

    def test_refills_over_time(self):
        """Tokens refill based on elapsed time."""
        limiter = TokenBucketRateLimiter(max_per_second=3.0)

        # Exhaust all tokens
        for _ in range(3):
            limiter.acquire()

        # Wait long enough for 2 tokens to refill
        time.sleep(0.7)

        start = time.monotonic()
        limiter.acquire()
        limiter.acquire()
        elapsed = time.monotonic() - start

        # Should be near-instant since tokens refilled
        assert elapsed < 0.1

    def test_tokens_capped_at_max(self):
        """Tokens should not exceed max_per_second even after long waits."""
        limiter = TokenBucketRateLimiter(max_per_second=3.0)

        # Wait a long time (tokens should still cap at 3)
        time.sleep(1.0)

        start = time.monotonic()
        for _ in range(3):
            limiter.acquire()
        elapsed_first_three = time.monotonic() - start

        # First 3 should be instant
        assert elapsed_first_three < 0.1

        # 4th should block
        start = time.monotonic()
        limiter.acquire()
        elapsed_fourth = time.monotonic() - start
        assert elapsed_fourth >= 0.25

    def test_custom_rate(self):
        """Rate limiter respects custom max_per_second."""
        limiter = TokenBucketRateLimiter(max_per_second=5.0)

        # Should have 5 tokens available immediately
        start = time.monotonic()
        for _ in range(5):
            limiter.acquire()
        elapsed = time.monotonic() - start

        assert elapsed < 0.1

    def test_thread_safety(self):
        """Multiple threads can acquire tokens without data corruption."""
        limiter = TokenBucketRateLimiter(max_per_second=3.0)
        results: list[float] = []
        lock = threading.Lock()

        def worker():
            limiter.acquire()
            with lock:
                results.append(time.monotonic())

        # Launch 6 threads simultaneously
        threads = [threading.Thread(target=worker) for _ in range(6)]
        start = time.monotonic()
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        total_elapsed = time.monotonic() - start

        # 6 requests at 3/sec should take at least ~1 second
        # (3 immediate + 3 more needing 1 second total)
        assert total_elapsed >= 0.9
        assert len(results) == 6
