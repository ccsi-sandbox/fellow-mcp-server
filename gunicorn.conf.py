"""Gunicorn configuration for the Fellow MCP Server.

Worker count is configured via the GUNICORN_WORKERS environment variable,
defaulting to 2 workers when unset.
"""

import os

# Server socket
bind = "0.0.0.0:8000"

# Worker processes
workers = int(os.environ.get("GUNICORN_WORKERS", "2"))

# Worker class (sync - appropriate for rate-limited API calls)
worker_class = "sync"

# Timeout for worker processes (seconds)
# Must be high enough to accommodate paginated requests with retries.
# Worst case: 20 pages × (30s timeout × 4 attempts) / 3 req/s rate limit = ~800s
# Setting to 300s as a practical balance.
timeout = 300

# Graceful restart timeout
graceful_timeout = 30

# Access log - disable since we use structlog
accesslog = None

# Error log - let structlog handle it
errorlog = "-"

# Log level
loglevel = os.environ.get("LOG_LEVEL", "info").lower()
