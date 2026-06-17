# Debug Logging Enhancement Bugfix Design

## Overview

This bugfix addresses two operational deficiencies in the Fellow MCP server:

1. **DEBUG Logging Gap**: Despite supporting `LOG_LEVEL=DEBUG` via `AppConfig` and structlog configuration, the codebase contains zero `logger.debug()` calls. Setting DEBUG produces no additional output versus INFO. The fix adds targeted `logger.debug()` calls at key request/response boundaries: incoming MCP requests in `app/main.py`, outgoing Fellow API requests and responses in `app/client/fellow_api.py`, and rate limiter wait decisions in `app/client/rate_limiter.py`.

2. **Timezone Configuration Deficiency**: The Docker container defaults to UTC with no mechanism to configure timezone. The fix installs `tzdata` in the container image, sets a default `TZ=America/Los_Angeles` in the Dockerfile, passes `TZ` through docker-compose environment, and documents the variable in `.env.example`.

Both fixes are additive — they introduce new behavior without modifying existing logic paths.

## Glossary

- **Bug_Condition (C)**: Two conditions: (1) `LOG_LEVEL=DEBUG` is set but no DEBUG log entries are emitted at request/response boundaries; (2) `TZ` environment variable has no effect on container timezone
- **Property (P)**: (1) DEBUG-level log entries appear at all instrumented points when LOG_LEVEL=DEBUG; (2) Container timezone matches configured TZ value
- **Preservation**: Existing INFO/WARNING/ERROR log behavior, existing structlog fields, existing health check behavior, existing configuration validation — all unchanged
- **`_do_request_with_retry`**: The method in `app/client/fellow_api.py` that executes HTTP requests with tenacity retry decoration
- **`TokenBucketRateLimiter.acquire`**: The method in `app/client/rate_limiter.py` that blocks until a rate limit token is available
- **`mcp_endpoint`**: The Flask route handler in `app/main.py` that receives JSON-RPC 2.0 requests
- **`configure_logging`**: The function in `app/logging/setup.py` that sets up structlog with level filtering

## Bug Details

### Bug Condition

The bug manifests in two independent conditions:

**Condition 1 (DEBUG Logging):** When `LOG_LEVEL=DEBUG` is configured and requests flow through the system, no DEBUG-level entries are emitted because there are no `logger.debug()` calls anywhere in the codebase. The structlog pipeline and level filtering work correctly — the problem is purely the absence of debug log statements.

**Condition 2 (Timezone):** When a `TZ` environment variable is set in `.env`, it has no effect because: (a) `docker-compose.yml` does not pass `TZ` to the container, (b) the Dockerfile does not install `tzdata`, and (c) `.env.example` does not document `TZ`.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type SystemState
  OUTPUT: boolean
  
  // Condition 1: DEBUG logging gap
  debugLoggingGap :=
    input.logLevel == "DEBUG"
    AND input.eventType IN ["mcp_request_received", "fellow_api_request", 
                            "fellow_api_response", "rate_limiter_wait"]
    AND NOT debugLogEmitted(input.eventType)
  
  // Condition 2: Timezone configuration gap
  timezoneGap :=
    input.deploymentTarget == "docker"
    AND (input.tzVariable IS SET OR input.tzVariable IS NOT SET)
    AND containerTimezone != expectedTimezone(input.tzVariable)
  
  RETURN debugLoggingGap OR timezoneGap
END FUNCTION
```

### Examples

- **MCP Request (DEBUG gap)**: Client sends `{"jsonrpc":"2.0","method":"tools/call","params":{"name":"list_notes","arguments":{}},"id":1}` → Expected: DEBUG log with method, tool name, arguments. Actual: No DEBUG log emitted.
- **Fellow API Request (DEBUG gap)**: Server calls `GET https://company.fellow.app/api/v1/notes?limit=20` → Expected: DEBUG log with method, URL, redacted headers. Actual: No log emitted.
- **Fellow API Response (DEBUG gap)**: API returns `200 OK` with JSON body → Expected: DEBUG log with status code, truncated body, elapsed_ms. Actual: No log emitted.
- **Rate Limiter Wait (DEBUG gap)**: Token bucket has 0.2 tokens, must wait 0.27s → Expected: DEBUG log with tokens_available, wait_seconds, max_tokens. Actual: No log emitted.
- **Timezone (TZ gap)**: `TZ=America/New_York` in `.env`, container still uses UTC for log timestamps.
- **Timezone Default (TZ gap)**: No `TZ` set anywhere, expected default `America/Los_Angeles`, actual default UTC.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- INFO-level `tool_call` log entries (tool name, duration_ms, outcome) continue to be emitted unchanged in format and fields
- WARNING-level `fellow_api_retry` and `auth_rejected` entries continue to appear at WARNING+ levels
- `request_id` correlation via structlog contextvars continues to be bound on every request
- All existing structlog fields (event, level, logger, timestamp) remain present
- Health check endpoint continues to respond on `/health` with correct status
- All existing environment variable validation (FELLOW_API_KEY, FELLOW_SUBDOMAIN, etc.) remains unchanged
- Container starts successfully with or without TZ variable set
- No DEBUG entries appear when LOG_LEVEL is set to INFO or higher

**Scope:**
All inputs that do NOT involve DEBUG-level log emission or timezone configuration should be completely unaffected by this fix. This includes:
- Normal request/response flow at INFO level
- Authentication guard behavior
- Retry logic and error handling
- Tool handler execution
- Rate limiter functional behavior (token bucket algorithm unchanged)
- Configuration validation logic

## Hypothesized Root Cause

Based on the bug description, the root causes are straightforward:

1. **Missing `logger.debug()` Calls**: The codebase was written with INFO as the practical minimum. No developer added DEBUG instrumentation at request boundaries. The logging infrastructure (structlog, level filtering) works correctly — there are simply no debug statements to emit.

2. **Missing `tzdata` Package in Container**: The `python:3.11-slim` base image does not include timezone data. Without `tzdata`, Python's `datetime` and the OS-level `TZ` variable cannot resolve named timezones.

3. **Missing TZ Passthrough in Docker Compose**: `docker-compose.yml` uses `env_file: .env` which passes variables to the container, but without the `TZ` variable documented in `.env.example`, users don't know to set it. Additionally, no default is set in the Dockerfile.

4. **No Default TZ in Dockerfile**: The Dockerfile sets no `ENV TZ=...` directive, so the container always defaults to UTC.

## Correctness Properties

Property 1: Bug Condition - DEBUG Log Emission at Request Boundaries

_For any_ request processed by the MCP server when `LOG_LEVEL=DEBUG`, the system SHALL emit DEBUG-level structured log entries at each instrumented boundary: incoming MCP request (with JSON-RPC method and arguments), outgoing Fellow API request (with HTTP method, URL, redacted headers), Fellow API response (with status code, truncated body, elapsed_ms), and rate limiter wait decisions (with token count, wait duration, max tokens).

**Validates: Requirements 2.1, 2.2, 2.3, 2.4**

Property 2: Preservation - No DEBUG Output at INFO Level and Above

_For any_ request processed by the MCP server when `LOG_LEVEL` is set to INFO, WARNING, ERROR, or CRITICAL, the system SHALL produce exactly the same log output as the original unfixed code — no DEBUG entries shall appear, and all existing INFO/WARNING/ERROR entries shall remain unchanged in format and content.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

Property 3: Bug Condition - Container Timezone Reflects TZ Variable

_For any_ deployment where `TZ` is set to a valid IANA timezone identifier, the container's system timezone and log timestamps SHALL reflect that timezone. When `TZ` is not set, the container SHALL default to `America/Los_Angeles`.

**Validates: Requirements 2.5, 2.6, 2.7, 2.8**

Property 4: Preservation - Existing Configuration and Startup Unchanged

_For any_ deployment with or without `TZ` set, the system SHALL continue to start successfully, pass health checks, validate all existing environment variables identically, and include all existing structured log fields (request_id, event, level) unchanged.

**Validates: Requirements 3.5, 3.6, 3.7, 3.8**

## Fix Implementation

### Changes Required

**File**: `app/main.py`

**Function**: `mcp_endpoint` (inside `_register_routes`)

**Specific Changes**:
1. **Add DEBUG log for incoming MCP request**: After successful `parse_jsonrpc_request()`, emit `logger.debug("mcp_request_received", method=method, params=parsed.get("params"), jsonrpc_id=request_id)` before dispatching to handlers.

---

**File**: `app/client/fellow_api.py`

**Function**: `_do_request_with_retry`

**Specific Changes**:
2. **Add DEBUG log before HTTP request**: After `self._rate_limiter.acquire()` and before `self._session.request(...)`, emit `logger.debug("fellow_api_request", http_method=method, url=url, params=params, body_keys=list(json_body.keys()) if json_body else None)`. Redact the X-API-KEY header by not logging raw headers.
3. **Add DEBUG log after HTTP response**: After receiving `response`, emit `logger.debug("fellow_api_response", http_method=method, url=url, status_code=response.status_code, response_body=response.text[:500], elapsed_ms=round(response.elapsed.total_seconds() * 1000, 2))`. Truncate response body to 500 chars to avoid log bloat.

---

**File**: `app/client/rate_limiter.py`

**Function**: `acquire`

**Specific Changes**:
4. **Add DEBUG log for rate limiter wait**: When a wait is required (tokens < 1.0), emit `logger.debug("rate_limiter_wait", tokens_available=round(self._tokens, 3), wait_seconds=round(wait_time, 4), max_tokens=self._max_tokens)`. Import structlog at module level. Only log when a wait actually occurs (not on immediate token grant).

---

**File**: `Dockerfile`

**Specific Changes**:
5. **Install tzdata in production stage**: Add `RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*` before switching to non-root user.
6. **Set default TZ**: Add `ENV TZ=America/Los_Angeles` after tzdata install.

---

**File**: `docker-compose.yml`

**Specific Changes**:
7. **Add environment section with TZ**: Add `environment: - TZ=${TZ:-America/Los_Angeles}` to pass TZ from host `.env` with a default fallback.

---

**File**: `docker-compose.yml.drl`

**Specific Changes**:
8. **Add environment section with TZ**: Same as docker-compose.yml — add `environment: - TZ=${TZ:-America/Los_Angeles}`.

---

**File**: `.env.example`

**Specific Changes**:
9. **Document TZ variable**: Add a `# Timezone Configuration` section with `TZ=America/Los_Angeles` and a comment explaining it controls container and log timezone.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, confirm the bugs exist on unfixed code (no DEBUG output, wrong timezone), then verify the fix produces correct DEBUG output and respects TZ configuration while preserving all existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate both bugs BEFORE implementing the fix. Confirm that the root cause analysis is correct.

**Test Plan**: Write tests that exercise each instrumented code path at DEBUG level and assert DEBUG log entries are emitted. Run on UNFIXED code to confirm failures.

**Test Cases**:
1. **MCP Request DEBUG Test**: Set LOG_LEVEL=DEBUG, send a JSON-RPC tools/call request, assert a DEBUG entry with event "mcp_request_received" appears (will fail on unfixed code)
2. **Fellow API Request DEBUG Test**: Set LOG_LEVEL=DEBUG, trigger an API call, assert a DEBUG entry with event "fellow_api_request" appears (will fail on unfixed code)
3. **Fellow API Response DEBUG Test**: Set LOG_LEVEL=DEBUG, trigger an API call, assert a DEBUG entry with event "fellow_api_response" with status_code appears (will fail on unfixed code)
4. **Rate Limiter Wait DEBUG Test**: Set LOG_LEVEL=DEBUG, exhaust tokens then acquire, assert a DEBUG entry with event "rate_limiter_wait" appears (will fail on unfixed code)
5. **Timezone Default Test**: Build container without TZ set, check system timezone is America/Los_Angeles (will fail on unfixed code — shows UTC)

**Expected Counterexamples**:
- No DEBUG-level log entries captured in any test at DEBUG level
- Container timezone reports UTC instead of America/Los_Angeles

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed functions produce the expected DEBUG output and correct timezone.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  IF input.type == "debug_logging" THEN
    result := processRequest_fixed(input)
    ASSERT debugLogEmitted(result, expectedEvent, expectedFields)
  ELSE IF input.type == "timezone" THEN
    result := containerTimezone_fixed(input.tzVariable)
    ASSERT result == expectedTimezone(input.tzVariable)
  END IF
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed functions produce the same result as the original.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT processRequest_original(input).logs == processRequest_fixed(input).logs
  ASSERT processRequest_original(input).response == processRequest_fixed(input).response
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many combinations of LOG_LEVEL settings and request types automatically
- It catches regressions in log output format that manual tests might miss
- It provides strong guarantees that INFO-level behavior is unchanged across all tool types

**Test Plan**: Observe behavior on UNFIXED code first for INFO-level log output, then write property-based tests capturing that exact behavior continues after fix.

**Test Cases**:
1. **INFO Level Preservation**: Verify that at LOG_LEVEL=INFO, the `tool_call` INFO entry is emitted with identical fields (tool, duration_ms, outcome) and NO DEBUG entries appear
2. **WARNING Level Preservation**: Verify that at LOG_LEVEL=WARNING, retry warnings still emit and no INFO or DEBUG entries appear
3. **Request ID Preservation**: Verify that request_id correlation continues to appear in all log entries at every level
4. **Health Check Preservation**: Verify that `/health` endpoint returns 200 with correct JSON regardless of TZ or LOG_LEVEL setting
5. **Config Validation Preservation**: Verify that existing env var validation (FELLOW_API_KEY required, GUNICORN_WORKERS range) works identically

### Unit Tests

- Test that `logger.debug("mcp_request_received", ...)` is called with correct fields when MCP request is processed at DEBUG level
- Test that `logger.debug("fellow_api_request", ...)` is called with HTTP method, URL, and redacted headers
- Test that `logger.debug("fellow_api_response", ...)` includes status_code, truncated body, and elapsed_ms
- Test that `logger.debug("rate_limiter_wait", ...)` is called only when wait occurs, not on immediate grant
- Test that response body truncation works correctly at 500-char boundary
- Test that no DEBUG calls occur when LOG_LEVEL=INFO (level filtering)
- Test that TZ=America/Los_Angeles is documented in .env.example
- Test that Dockerfile includes tzdata installation

### Property-Based Tests

- Generate random JSON-RPC requests (varying methods, params, tool names) at DEBUG level and verify all expected DEBUG fields are present in log output
- Generate random LOG_LEVEL values from {INFO, WARNING, ERROR, CRITICAL} and verify zero DEBUG entries appear for any request combination
- Generate random Fellow API response bodies of varying lengths and verify truncation at 500 chars works correctly
- Generate random rate limiter states (varying token counts 0.0–3.0) and verify DEBUG log only emits when wait_time > 0

### Integration Tests

- Test full request flow at DEBUG level: send MCP request → verify mcp_request_received log → verify fellow_api_request log → verify fellow_api_response log → verify tool_call INFO log still present
- Test that setting LOG_LEVEL=INFO produces identical output to current unfixed code (no regressions)
- Test container build with TZ=America/New_York and verify log timestamps reflect Eastern time
- Test container build with no TZ and verify default America/Los_Angeles is applied
