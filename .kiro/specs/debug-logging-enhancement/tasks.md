# Implementation Plan

## Overview

This plan implements the debug-logging-enhancement bugfix using the exploratory bugfix workflow: write tests to confirm bugs exist, write preservation tests to capture baseline behavior, implement fixes, and validate.

**Bug 1 (DEBUG Logging Gap):** Add `logger.debug()` calls at request/response boundaries in `app/client/rate_limiter.py`, `app/client/fellow_api.py`, and `app/main.py`.

**Bug 2 (Timezone Configuration):** Install `tzdata` in Docker image, set default `TZ=America/Los_Angeles`, pass TZ through docker-compose, and document in `.env.example`.

## Tasks

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - DEBUG Logging Gap at Request Boundaries
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate no DEBUG log entries are emitted despite LOG_LEVEL=DEBUG
  - **Scoped PBT Approach**: Use Hypothesis to generate random JSON-RPC method/params combinations at DEBUG level and assert DEBUG entries appear
  - Test that when LOG_LEVEL=DEBUG and a JSON-RPC request is processed through `mcp_endpoint`, a DEBUG log with event `mcp_request_received` containing method and params is emitted (from Bug Condition in design: `debugLogEmitted("mcp_request_received")` returns False)
  - Test that when LOG_LEVEL=DEBUG and `_do_request_with_retry` executes an HTTP request, DEBUG logs with events `fellow_api_request` (with http_method, url, redacted headers) and `fellow_api_response` (with status_code, truncated body, elapsed_ms) are emitted
  - Test that when LOG_LEVEL=DEBUG and `TokenBucketRateLimiter.acquire()` waits (tokens < 1.0), a DEBUG log with event `rate_limiter_wait` containing tokens_available, wait_seconds, max_tokens is emitted
  - Run tests on UNFIXED code - expect FAILURE (no DEBUG entries exist in current code)
  - Document counterexamples: e.g., "tools/call request at DEBUG level produces zero DEBUG log entries"
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - No DEBUG Output at INFO Level and Existing Log Format Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Observe: At LOG_LEVEL=INFO, a tools/call request emits only INFO-level `tool_call` entry with fields (tool, duration_ms, outcome) and zero DEBUG entries
  - Observe: At LOG_LEVEL=WARNING, retry scenarios emit WARNING-level `fellow_api_retry` and no INFO/DEBUG entries appear
  - Observe: request_id correlation field is present in all log entries regardless of level
  - Observe: `/health` endpoint returns 200 with `{"status": "healthy", "fellow_api": "..."}` regardless of LOG_LEVEL
  - Write property-based test (Hypothesis): for all LOG_LEVEL in {INFO, WARNING, ERROR, CRITICAL} and for all valid JSON-RPC requests, zero DEBUG-level entries appear in captured logs
  - Write property-based test: for all valid tools/call requests at INFO level, the `tool_call` INFO entry contains exactly the fields (tool, duration_ms, outcome) with request_id bound
  - Write property-based test: for random Fellow API response bodies of varying lengths, verify current behavior produces no DEBUG output (baseline for truncation preservation)
  - Verify all preservation tests PASS on UNFIXED code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

- [x] 3. Implement DEBUG logging instrumentation

  - [x] 3.1 Add DEBUG log to rate limiter acquire method
    - In `app/client/rate_limiter.py`, add `import structlog` and `logger = structlog.get_logger(__name__)` at module level
    - Inside `acquire()`, after calculating `wait_time` and before `time.sleep(wait_time)`, add `logger.debug("rate_limiter_wait", tokens_available=round(self._tokens + 1.0, 3), wait_seconds=round(wait_time, 4), max_tokens=self._max_tokens)`
    - Only log when wait actually occurs (within the `if self._tokens < 1.0` branch where wait_time > 0)
    - _Bug_Condition: isBugCondition(input) where input.logLevel == "DEBUG" AND input.eventType == "rate_limiter_wait" AND NOT debugLogEmitted("rate_limiter_wait")_
    - _Expected_Behavior: DEBUG entry with tokens_available, wait_seconds, max_tokens fields when wait occurs_
    - _Preservation: Rate limiter functional behavior (token bucket algorithm) unchanged; no DEBUG at INFO+_
    - _Requirements: 1.4, 2.4, 3.1, 3.2_

  - [x] 3.2 Add DEBUG logs to Fellow API client
    - In `app/client/fellow_api.py` `_do_request_with_retry` method:
    - After `self._rate_limiter.acquire()` and before `self._session.request(...)`, add `logger.debug("fellow_api_request", http_method=method, url=url, params=params, body_keys=list(json_body.keys()) if json_body else None)`
    - After receiving `response`, add `logger.debug("fellow_api_response", http_method=method, url=url, status_code=response.status_code, response_body=response.text[:500], elapsed_ms=round(response.elapsed.total_seconds() * 1000, 2))`
    - Do NOT log raw headers (X-API-KEY redaction by omission)
    - Truncate response body to 500 characters to prevent log bloat
    - _Bug_Condition: isBugCondition(input) where input.logLevel == "DEBUG" AND input.eventType IN ["fellow_api_request", "fellow_api_response"]_
    - _Expected_Behavior: DEBUG entries with http_method, url, status_code, truncated body, elapsed_ms_
    - _Preservation: Existing retry logic, error handling, and WARNING-level logs unchanged_
    - _Requirements: 1.2, 1.3, 2.2, 2.3, 3.1, 3.2, 3.3_

  - [x] 3.3 Add DEBUG log to MCP endpoint for incoming requests
    - In `app/main.py` `mcp_endpoint` function inside `_register_routes`:
    - After successful `parse_jsonrpc_request()` and assignment of `method`, add `logger.debug("mcp_request_received", method=method, params=parsed.get("params"), jsonrpc_id=request_id)`
    - This logs the JSON-RPC method, parameters/arguments, and request_id (already bound via structlog contextvars)
    - _Bug_Condition: isBugCondition(input) where input.logLevel == "DEBUG" AND input.eventType == "mcp_request_received"_
    - _Expected_Behavior: DEBUG entry with method, params, jsonrpc_id fields for every parsed MCP request_
    - _Preservation: Existing INFO-level tool_call log, auth behavior, and response format unchanged_
    - _Requirements: 1.1, 2.1, 3.1, 3.3, 3.4_

  - [x] 3.4 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - DEBUG Log Emission at Request Boundaries
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior (DEBUG entries emitted at each boundary)
    - When this test passes, it confirms: mcp_request_received, fellow_api_request, fellow_api_response, and rate_limiter_wait DEBUG entries are emitted correctly
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms DEBUG logging gap is fixed)
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 3.5 Verify preservation tests still pass
    - **Property 2: Preservation** - No DEBUG Output at INFO Level and Existing Log Format Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions — INFO/WARNING/ERROR behavior unchanged)
    - Confirm no DEBUG entries appear at INFO level, existing tool_call format intact, request_id still bound
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 4. Implement timezone configuration

  - [x] 4.1 Install tzdata and set default TZ in Dockerfile
    - In `Dockerfile` production stage, before `USER appuser`, add: `RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*`
    - After tzdata install, add: `ENV TZ=America/Los_Angeles`
    - This ensures named timezones resolve correctly and defaults to Pacific time
    - _Bug_Condition: isBugCondition(input) where input.deploymentTarget == "docker" AND containerTimezone != expectedTimezone(input.tzVariable)_
    - _Expected_Behavior: Container timezone defaults to America/Los_Angeles; TZ variable overrides it_
    - _Preservation: Container starts successfully, health checks pass, no configuration validation changes_
    - _Requirements: 1.5, 1.6, 1.8, 2.5, 2.8, 3.5, 3.6, 3.7_

  - [x] 4.2 Add TZ environment passthrough in docker-compose.yml
    - Add `environment:` section to the `fellow-mcp` service with `- TZ=${TZ:-America/Los_Angeles}`
    - This allows host `.env` TZ value to pass through to the container with a default fallback
    - _Bug_Condition: docker-compose.yml does not pass TZ to container environment_
    - _Expected_Behavior: TZ from .env is applied to container; defaults to America/Los_Angeles if unset_
    - _Preservation: Existing env_file, ports, healthcheck, build config unchanged_
    - _Requirements: 1.6, 2.6, 3.5, 3.6_

  - [x] 4.3 Add TZ environment passthrough in docker-compose.yml.drl
    - Add `environment:` section to the `fellow-mcp` service with `- TZ=${TZ:-America/Los_Angeles}`
    - Same change as docker-compose.yml applied to the DRL variant
    - _Requirements: 1.6, 2.6_

  - [x] 4.4 Document TZ variable in .env.example
    - Add a `# Timezone Configuration` section at the end of `.env.example`
    - Add `TZ=America/Los_Angeles` with comment: `# Container timezone (IANA format). Default: America/Los_Angeles`
    - _Bug_Condition: .env.example provides no documentation for TZ variable_
    - _Expected_Behavior: TZ variable documented with default value and explanatory comment_
    - _Preservation: All existing variable documentation unchanged_
    - _Requirements: 1.7, 2.7, 3.5_

- [x] 5. Checkpoint - Ensure all tests pass
  - Run full test suite: `pytest` (within venv)
  - Verify bug condition exploration test (task 1) passes after fix
  - Verify preservation property tests (task 2) still pass after fix
  - Verify no regressions in existing test suite
  - Optionally build Docker image to confirm tzdata install and TZ default: `docker compose build`
  - Ensure all tests pass, ask the user if questions arise.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1", "2"] },
    { "id": 1, "tasks": ["3.1", "3.2", "3.3"] },
    { "id": 2, "tasks": ["3.4", "3.5"] },
    { "id": 3, "tasks": ["4.1", "4.2", "4.3", "4.4"] },
    { "id": 4, "tasks": ["5"] }
  ]
}
```

## Notes

- Tasks 1 and 2 are independent and can be written in parallel, but both must complete before task 3.
- Task 3 sub-tasks (3.1, 3.2, 3.3) are independent of each other and can be implemented in any order. Sub-tasks 3.4 and 3.5 must run after 3.1–3.3.
- Task 4 is independent of task 3 at the code level but is ordered after for logical grouping. It can be parallelized with task 3 if desired.
- All property-based tests use Hypothesis (already in requirements.txt).
- Response body truncation uses 500 characters as specified in design.
