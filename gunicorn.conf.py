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
timeout = 120

# Graceful restart timeout
graceful_timeout = 30

# Access log - disable since we use structlog
accesslog = None

# Error log - let structlog handle it
errorlog = "-"

# Log level
loglevel = os.environ.get("LOG_LEVEL", "info").lower()
