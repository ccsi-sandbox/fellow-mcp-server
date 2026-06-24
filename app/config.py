"""Configuration module with environment variable loading and validation.

Provides an immutable AppConfig dataclass loaded from environment variables
with comprehensive validation and descriptive error messages on failure.
"""

import logging
import os
from dataclasses import dataclass
from typing import Optional

_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def _strip_inline_comment(value: str) -> str:
    """Strip inline comments from environment variable values.

    Docker Compose env_file does not strip inline comments, so a value like
    'INFO  # some comment' is passed verbatim. This helper strips the comment.

    Args:
        value: Raw environment variable value.

    Returns:
        Value with inline comment removed and whitespace stripped.
    """
    # Only strip if there's a space before the # (to avoid stripping # in values)
    if " #" in value:
        value = value[: value.index(" #")]
    return value.strip()


@dataclass(frozen=True)
class AppConfig:
    """Immutable application configuration loaded from environment variables."""

    fellow_api_key: str
    fellow_subdomain: str
    mcp_auth_enabled: bool
    mcp_auth_token: Optional[str]
    gunicorn_workers: int
    log_level: str
    mcp_endpoint_path: str
    fellow_base_url: str

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Load and validate configuration from environment variables.

        Validates:
        - FELLOW_API_KEY: required, non-empty
        - FELLOW_SUBDOMAIN: required, non-empty
        - MCP_AUTH_ENABLED: case-sensitive "true" enables auth
        - MCP_AUTH_TOKEN: required ≥16 chars when auth enabled
        - GUNICORN_WORKERS: integer in [1, 8], default 2
        - LOG_LEVEL: must be in accepted set, default INFO with warning
        - MCP_ENDPOINT_PATH: default "/mcp"

        Raises:
            SystemExit: If required variables are missing or invalid.
        """
        errors: list[str] = []

        # Required variables
        fellow_api_key = os.environ.get("FELLOW_API_KEY", "").strip()
        if not fellow_api_key:
            errors.append(
                "FELLOW_API_KEY is required and must be non-empty"
            )

        fellow_subdomain = os.environ.get("FELLOW_SUBDOMAIN", "").strip()
        if not fellow_subdomain:
            errors.append(
                "FELLOW_SUBDOMAIN is required and must be non-empty"
            )

        # Auth configuration
        mcp_auth_enabled = os.environ.get("MCP_AUTH_ENABLED", "") == "true"
        mcp_auth_token = os.environ.get("MCP_AUTH_TOKEN")

        if mcp_auth_enabled:
            if not mcp_auth_token:
                errors.append(
                    "MCP_AUTH_TOKEN is required when MCP_AUTH_ENABLED is 'true'"
                )
            elif len(mcp_auth_token) < 16:
                errors.append(
                    "MCP_AUTH_TOKEN must be at least 16 characters when "
                    "authentication is enabled "
                    f"(got {len(mcp_auth_token)} characters)"
                )

        # Gunicorn workers
        workers_raw = _strip_inline_comment(
            os.environ.get("GUNICORN_WORKERS", "2")
        )
        gunicorn_workers = 2
        try:
            gunicorn_workers = int(workers_raw)
            if gunicorn_workers < 1 or gunicorn_workers > 8:
                errors.append(
                    "GUNICORN_WORKERS must be an integer between 1 and 8 "
                    f"(got {gunicorn_workers})"
                )
        except ValueError:
            errors.append(
                "GUNICORN_WORKERS must be a valid integer between 1 and 8 "
                f"(got '{workers_raw}')"
            )

        # Log level
        log_level_raw = _strip_inline_comment(
            os.environ.get("LOG_LEVEL", "INFO")
        ).upper()
        log_level = "INFO"
        if log_level_raw in _VALID_LOG_LEVELS:
            log_level = log_level_raw
        else:
            logging.warning(
                "Invalid LOG_LEVEL '%s' - defaulting to INFO. "
                "Accepted values: %s",
                log_level_raw,
                ", ".join(sorted(_VALID_LOG_LEVELS)),
            )

        # MCP endpoint path
        mcp_endpoint_path = _strip_inline_comment(
            os.environ.get("MCP_ENDPOINT_PATH", "/mcp")
        )

        # Fail fast on validation errors
        if errors:
            error_msg = "Configuration validation failed:\n" + "\n".join(
                f"  - {e}" for e in errors
            )
            raise SystemExit(error_msg)

        # Derive fellow_base_url
        fellow_base_url = f"https://{fellow_subdomain}.fellow.app"

        return cls(
            fellow_api_key=fellow_api_key,
            fellow_subdomain=fellow_subdomain,
            mcp_auth_enabled=mcp_auth_enabled,
            mcp_auth_token=mcp_auth_token,
            gunicorn_workers=gunicorn_workers,
            log_level=log_level,
            mcp_endpoint_path=mcp_endpoint_path,
            fellow_base_url=fellow_base_url,
        )
