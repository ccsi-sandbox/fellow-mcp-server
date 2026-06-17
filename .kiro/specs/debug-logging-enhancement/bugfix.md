# Bugfix Requirements Document

## Introduction

This document captures two operational deficiencies in the Fellow MCP server:

1. **DEBUG Logging Gap**: The server supports a `LOG_LEVEL` environment variable that accepts DEBUG, INFO, WARNING, ERROR, and CRITICAL. However, setting `LOG_LEVEL=DEBUG` produces no additional output compared to `LOG_LEVEL=INFO` because there are zero `logger.debug()` calls anywhere in the codebase. This makes it impossible for administrators to diagnose request/response flow issues without modifying code.

2. **Timezone Configuration Deficiency**: Neither `docker-compose.yml`, `.env.example`, the `Dockerfile`, nor `app/config.py` support setting a timezone. The container runs with UTC by default, providing no mechanism for administrators to configure the timezone for log timestamps or application behavior. The default should be `America/Los_Angeles` (Pacific time), configurable via a `TZ` environment variable.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN LOG_LEVEL is set to DEBUG and an MCP client sends a JSON-RPC request to the /mcp endpoint THEN the system logs only the INFO-level `tool_call` summary (tool name, duration_ms, outcome) with no additional detail about the incoming request

1.2 WHEN LOG_LEVEL is set to DEBUG and the MCP server makes an outgoing HTTP request to the Fellow API THEN the system logs nothing about the outgoing request URL, method, headers, or body

1.3 WHEN LOG_LEVEL is set to DEBUG and the Fellow API returns a response THEN the system logs nothing about the response status code, body, or response time

1.4 WHEN LOG_LEVEL is set to DEBUG and the token bucket rate limiter makes a wait decision THEN the system logs nothing about the rate limiter state or wait duration

### Expected Behavior (Correct)

2.1 WHEN LOG_LEVEL is set to DEBUG and an MCP client sends a JSON-RPC request to the /mcp endpoint THEN the system SHALL emit a DEBUG-level log entry containing the JSON-RPC method, parameters/arguments, and request metadata (request_id is already bound via structlog contextvars)

2.2 WHEN LOG_LEVEL is set to DEBUG and the MCP server makes an outgoing HTTP request to the Fellow API THEN the system SHALL emit a DEBUG-level log entry containing the HTTP method, full URL, request headers (with sensitive headers like X-API-KEY redacted), and request body/params

2.3 WHEN LOG_LEVEL is set to DEBUG and the Fellow API returns a response THEN the system SHALL emit a DEBUG-level log entry containing the HTTP status code, response body (truncated if excessively large), and elapsed time in milliseconds

2.4 WHEN LOG_LEVEL is set to DEBUG and the token bucket rate limiter blocks or waits before issuing a token THEN the system SHALL emit a DEBUG-level log entry containing the current token count, wait duration, and max tokens

### Unchanged Behavior (Regression Prevention)

3.1 WHEN LOG_LEVEL is set to INFO THEN the system SHALL CONTINUE TO emit only the existing `tool_call` INFO-level log with tool name, duration_ms, and outcome — no DEBUG entries shall appear

3.2 WHEN LOG_LEVEL is set to WARNING or higher THEN the system SHALL CONTINUE TO emit only WARNING-level and above log entries (e.g., `fellow_api_retry`, `auth_rejected`, `network_error`)

3.3 WHEN LOG_LEVEL is set to DEBUG and a tool call completes THEN the system SHALL CONTINUE TO emit the existing INFO-level `tool_call` log entry unchanged in format and fields

3.4 WHEN LOG_LEVEL is set to any level THEN the system SHALL CONTINUE TO include the request_id correlation field in all log entries via the existing structlog contextvars binding

---

## Timezone Configuration Deficiency

### Current Behavior (Defect)

1.5 WHEN an administrator deploys the container without setting a TZ environment variable THEN the system defaults to UTC with no documented mechanism to override the timezone

1.6 WHEN an administrator sets a TZ environment variable in .env or docker-compose.yml THEN the system ignores it because docker-compose.yml does not pass TZ to the container environment, the Dockerfile does not install the tzdata package, and app/config.py does not load or validate a TZ setting

1.7 WHEN an administrator reviews .env.example for available configuration options THEN the system provides no documentation or placeholder for a timezone variable

1.8 WHEN the structlog TimeStamper emits ISO timestamps THEN the system always uses UTC regardless of any TZ value because tzdata is not installed in the container image

### Expected Behavior (Correct)

2.5 WHEN an administrator deploys the container without setting a TZ environment variable THEN the system SHALL default to `America/Los_Angeles` (Pacific time) for log timestamps and all time-related output

2.6 WHEN an administrator sets the TZ environment variable (e.g., `TZ=America/New_York`) in .env THEN the system SHALL apply that timezone to the container's system clock, log timestamps, and any time-related application behavior

2.7 WHEN an administrator reviews .env.example for available configuration options THEN the system SHALL document the TZ variable with a default value of `America/Los_Angeles` and a comment explaining its purpose

2.8 WHEN the TZ environment variable is set and tzdata is installed THEN the system SHALL produce log timestamps reflecting the configured timezone rather than UTC

### Unchanged Behavior (Regression Prevention)

3.5 WHEN LOG_LEVEL, FELLOW_API_KEY, FELLOW_SUBDOMAIN, or any other existing environment variable is set THEN the system SHALL CONTINUE TO load and validate those variables exactly as before with no change in behavior

3.6 WHEN the container starts with a valid TZ value THEN the system SHALL CONTINUE TO pass all existing health checks and respond on port 8000 without degradation

3.7 WHEN the TZ variable is not set and the default is applied THEN the system SHALL CONTINUE TO start successfully without configuration validation errors

3.8 WHEN structured log entries are emitted THEN the system SHALL CONTINUE TO include all existing fields (request_id, event name, level) unchanged — only the timezone of the timestamp shall reflect the TZ configuration
