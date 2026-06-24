# Implementation Plan: Enhanced Request Logging

## Overview

Implement structured timing breakdowns, request/response size metrics, and upstream API response codes on all request-related log events. This introduces a `RequestMetrics` collector dataclass that accumulates timing, size, and status data as a request flows through the handler pipeline. The existing `_handle_tools_call` function is restructured to instrument each processing phase, and the API client is modified to record per-call details and emit enhanced retry/debug events.

## Tasks

- [x] 1. Create RequestMetrics dataclass and UpstreamCallRecord
  - [x] 1.1 Create `app/logging/metrics.py` with `UpstreamCallRecord` and `RequestMetrics` dataclasses
    - Define `UpstreamCallRecord` with fields: `page`, `duration_ms`, `status_code`, `request_bytes`, `response_bytes`
    - Define `RequestMetrics` with all timing fields (`validation_ms`, `rate_limiter_wait_ms`, `upstream_api_ms`, `retry_wait_ms`, `serialization_ms`, `overhead_ms`), size fields (`mcp_request_bytes`, `mcp_response_bytes`, `upstream_request_bytes`, `upstream_response_bytes`), status tracking (`upstream_status_code`), and per-call list (`upstream_api_calls`)
    - Implement `compute_total_ms()`, `compute_overhead_ms()`, `build_timings_dict()`, and `build_retry_timings_dict()` methods
    - All durations rounded to 2 decimal places; overhead computed as max(0, total - sum_of_steps)
    - _Requirements: 1.1, 1.2, 1.3, 1.10_

  - [x] 1.2 Write property test for timing sum invariant
    - **Property 1: Timing Sum Invariant**
    - **Validates: Requirements 1.3**

  - [x] 1.3 Write property test for step duration validity
    - **Property 2: Step Duration Validity**
    - **Validates: Requirements 1.2, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10**

- [x] 2. Instrument the API client for per-call metrics
  - [x] 2.1 Modify `FellowApiClient._request` and `_do_request_with_retry` in `app/client/fellow_api.py` to accept and populate `RequestMetrics`
    - Add optional `metrics: RequestMetrics | None = None` parameter to `_request` and `_do_request_with_retry`
    - Measure rate limiter wait time around `self._rate_limiter.acquire()` and accumulate into `metrics.rate_limiter_wait_ms`
    - Measure HTTP round-trip time (excluding rate limiter wait) and accumulate into `metrics.upstream_api_ms`
    - Record `request_bytes` (byte length of JSON-serialized body or 0 if none) and `response_bytes` (byte length of raw response body)
    - Capture `status_code` per attempt
    - Append an `UpstreamCallRecord` to `metrics.upstream_api_calls` for each HTTP call
    - Set `metrics.upstream_status_code` to the final response status code
    - _Requirements: 1.6, 1.7, 2.3, 2.4, 2.7, 2.8, 3.1, 3.2, 4.1, 4.4, 4.5_

  - [x] 2.2 Emit `fellow_api_call` DEBUG event for each individual HTTP request
    - Log at DEBUG level with fields: `event="fellow_api_call"`, `http_method`, `url`, `duration_ms`, `status_code`, `request_bytes`, `response_bytes`
    - Only per-call fields, no cumulative metrics (per Requirement 6.3)
    - _Requirements: 4.1, 6.3_

  - [x] 2.3 Enhance retry logging in `_before_sleep_log` to emit enhanced Retry_Event
    - Include `status_code` (HTTP status that caused retry, or 408 for timeout)
    - Include `timings.total_elapsed_ms` from `metrics.build_retry_timings_dict()`
    - Include `upstream_request_bytes`, `upstream_response_bytes` (cumulative)
    - Include `upstream_api_calls` array (calls up to and including the failed attempt)
    - Include `mcp_request_bytes`
    - Do NOT include `mcp_response_bytes` (not yet available)
    - Accumulate retry sleep time into `metrics.retry_wait_ms`
    - _Requirements: 3.4, 3.5, 5.1, 5.2, 5.3, 5.4, 6.1, 6.2, 6.4_

  - [x] 2.4 Write property test for upstream bytes accumulation
    - **Property 6: Upstream Bytes Accumulation**
    - **Validates: Requirements 2.3, 2.4, 2.7, 2.8**

  - [x] 2.5 Write property test for upstream API calls timing consistency
    - **Property 7: Upstream API Calls Timing Consistency**
    - **Validates: Requirements 4.4**

- [x] 3. Instrument the paginator for page-level tracking
  - [x] 3.1 Modify `CursorPaginator.fetch_all` in `app/client/paginator.py` to set page numbers on `UpstreamCallRecord` entries
    - Ensure each upstream call record has its `page` field set correctly (1-based)
    - For non-paginated calls, set `page` to 1
    - On pagination failure, still include a record for the failed call with measured duration and status_code 0 if no response
    - _Requirements: 4.2, 4.3, 4.5_

  - [x] 3.2 Propagate `PaginationError` status code to `metrics.upstream_status_code`
    - Extract the last HTTP status code from the paginator's failed attempt and set it on metrics
    - _Requirements: 3.3_

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Restructure `_handle_tools_call` for full instrumentation
  - [x] 5.1 Modify `_handle_tools_call` in `app/main.py` to create and populate `RequestMetrics`
    - Create `RequestMetrics(start_time=time.time())` at handler entry
    - Record `mcp_request_bytes` from `request.get_data()` byte length
    - Time the validation step and set `metrics.validation_ms`
    - Pass `metrics` to the API client via tool handler invocations
    - Time the response serialization step and set `metrics.serialization_ms`
    - Record `mcp_response_bytes` as byte length of final JSON response encoded to UTF-8
    - Compute `overhead_ms` via `metrics.compute_overhead_ms()`
    - On validation failure or tool-not-found, set `upstream_api_ms`, `retry_wait_ms`, `serialization_ms` to 0
    - _Requirements: 1.2, 1.4, 1.5, 1.9, 2.1, 2.2, 2.5, 2.6, 2.9_

  - [x] 5.2 Replace the existing `tool_call` INFO log with the enhanced Tool_Call_Event
    - Emit `timings` (full with steps), `mcp_request_bytes`, `mcp_response_bytes`, `upstream_request_bytes`, `upstream_response_bytes`, `upstream_status_code` (omit if no upstream call), `upstream_api_calls`
    - Remove the old flat `duration_ms` field
    - _Requirements: 1.1, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.6, 4.2, 4.3, 6.1, 6.2_

  - [x] 5.3 Add exception resilience: wrap metrics computation in try/except
    - If an unhandled exception occurs, still emit the Tool_Call_Event with `timings` populated up to the point of failure (remaining steps set to 0)
    - If metrics computation itself fails, emit a degraded log without `timings` and log a warning
    - _Requirements: 1.11_

  - [x] 5.4 Write property test for zero steps on early exit
    - **Property 3: Zero Steps on Early Exit**
    - **Validates: Requirements 1.4, 2.9**

  - [x] 5.5 Write property test for MCP request bytes round-trip
    - **Property 4: MCP Request Bytes Round-Trip**
    - **Validates: Requirements 2.1, 2.5**

  - [x] 5.6 Write property test for MCP response bytes round-trip
    - **Property 5: MCP Response Bytes Round-Trip**
    - **Validates: Requirements 2.2, 2.6**

- [x] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Wire tool handlers to pass metrics through
  - [x] 7.1 Update tool handler signatures and the registry dispatch to thread `metrics` through to `api_client._request`
    - Add `metrics` keyword argument to tool handler calls
    - Each tool handler passes `metrics` when calling `api_client.post()`, `api_client.get()`, etc.
    - For tools that make multiple API calls (e.g., paginated list tools), ensure all calls accumulate into the same `metrics` instance
    - _Requirements: 1.6, 1.7, 1.8, 2.3, 2.4, 4.2_

  - [x] 7.2 Write property test for upstream status code presence
    - **Property 8: Upstream Status Code Presence**
    - **Validates: Requirements 3.1, 3.2, 3.6**

  - [x] 7.3 Write property test for event field partitioning
    - **Property 9: Event Field Partitioning**
    - **Validates: Requirements 6.1, 6.2, 6.3**

  - [x] 7.4 Write property test for exception resilience
    - **Property 10: Exception Resilience**
    - **Validates: Requirements 1.11**

- [x] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The implementation language is Python (matching the existing codebase and design)
- The `RequestMetrics` threading approach is explicit rather than using thread-locals, keeping the code testable
- The `overhead_ms` step guarantees the timing sum invariant without requiring perfect accounting of every CPU cycle

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "3.1"] },
    { "id": 3, "tasks": ["2.4", "2.5", "3.2"] },
    { "id": 4, "tasks": ["5.1"] },
    { "id": 5, "tasks": ["5.2", "5.3"] },
    { "id": 6, "tasks": ["5.4", "5.5", "5.6", "7.1"] },
    { "id": 7, "tasks": ["7.2", "7.3", "7.4"] }
  ]
}
```
