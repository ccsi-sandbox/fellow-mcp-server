"""Shared fixtures for property-based tests.

Ensures structlog context is clean between tests for proper isolation
when using structlog.testing.capture_logs().
"""

import structlog
import pytest


@pytest.fixture(autouse=True)
def reset_structlog_context():
    """Clear structlog context variables between tests for isolation."""
    structlog.contextvars.clear_contextvars()
    yield
    structlog.contextvars.clear_contextvars()
