# Requirements Document

## Introduction

Enhance the Fellow MCP Server's request logging to provide granular timing breakdowns, request/response size metrics, and upstream API response codes. The current `duration_ms` field is replaced with a structured `timings` object that decomposes total request duration into discrete, additive steps. These metrics appear on all log events related to request handling (`tool_call`, `fellow_api_retry`, and per-call DEBUG events) to support operational troubleshooting of MCP performance and upstream API behavior.

## Glossary

- **MCP_Server**: The Fellow MCP Server Flask application that receives JSON-RPC requests and dispatches tool calls.
- **Upstream_API**: The Fellow.ai HTTP API that the MCP_Server calls to fulfill tool requests.
- **Tool_Call_Event**: The INFO-level structured log event emitted at the end of a `tools/call` request.
- **Retry_Event**: The WARNING-level structured log event emitted before each retry sleep during upstream API calls.
- **API_Call_Event**: A DEBUG-level structured log event emitted for each individual HTTP request to the Upstream_API.
- **Timings_Object**: A nested JSON object containing `total_ms` and a `steps` sub-object with individual duration fields that sum to `total_ms`.
- **Step_Duration**: A named duration field within `timings.steps` representing time spent in one discrete phase of request processing.
- **Request_Bytes**: The byte length of the serialized JSON body of an HTTP request.
- **Response_Bytes**: The byte length of the raw HTTP response body content.

## Requirements

### Requirement 1: Structured Timing Breakdown

**User Story:** As an operator, I want request timings broken into discrete steps in a nested object, so that I can identify which phase of request handling is slow.

#### Acceptance Criteria

1. WHEN a `tools/call` request completes, THE MCP_Server SHALL emit a Tool_Call_Event containing a `timings` field structured as `{"total_ms": <number>, "steps": {"validation_ms": <number>, "rate_limiter_wait_ms": <number>, "upstream_api_ms": <number>, "retry_wait_ms": <number>, "serialization_ms": <number>}}`.
2. THE MCP_Server SHALL compute `timings.total_ms` as the wall-clock elapsed time from the start of `_handle_tools_call` to the point of log emission, measured in milliseconds and rounded to two decimal places.
3. THE MCP_Server SHALL ensure the sum of all Step_Duration values within `timings.steps` equals `timings.total_ms` within a tolerance of 1 millisecond. Any unaccounted time (framework overhead, context switching) SHALL be attributed to a `overhead_ms` step to maintain the sum invariant.
4. WHEN no upstream API call is made (e.g., validation failure), THE MCP_Server SHALL set `upstream_api_ms`, `retry_wait_ms`, and `serialization_ms` to 0 in the Timings_Object.
5. THE MCP_Server SHALL measure `validation_ms` as the elapsed time spent in input validation via InputValidator.
6. THE MCP_Server SHALL measure `rate_limiter_wait_ms` as the cumulative time spent waiting for token bucket tokens across all upstream API call attempts.
7. THE MCP_Server SHALL measure `upstream_api_ms` as the cumulative time spent in HTTP round-trips to the Upstream_API (excluding rate limiter wait and retry sleep).
8. THE MCP_Server SHALL measure `retry_wait_ms` as the cumulative time spent sleeping between retry attempts (tenacity backoff and Retry-After waits).
9. THE MCP_Server SHALL measure `serialization_ms` as the time spent serializing the final tool result to JSON for the MCP response.
10. THE MCP_Server SHALL round all Step_Duration values to two decimal places.
11. IF the request terminates early due to an unhandled exception, THE Tool_Call_Event SHALL still include the `timings` field with steps measured up to the point of failure and remaining steps set to 0.

### Requirement 2: Request and Response Size Logging

**User Story:** As an operator, I want to see request and response sizes at both the MCP layer and upstream API layer, so that I can identify size-related performance issues.

#### Acceptance Criteria

1. WHEN a `tools/call` request completes, THE Tool_Call_Event SHALL include `mcp_request_bytes` containing the byte length of the incoming MCP JSON-RPC request body as a non-negative integer.
2. WHEN a `tools/call` request completes, THE Tool_Call_Event SHALL include `mcp_response_bytes` containing the byte length of the serialized MCP JSON-RPC response body as a non-negative integer.
3. WHEN a `tools/call` request completes, THE Tool_Call_Event SHALL include `upstream_request_bytes` containing the total byte count of all serialized JSON request bodies sent to the Upstream_API during that tool call as a non-negative integer.
4. WHEN a `tools/call` request completes, THE Tool_Call_Event SHALL include `upstream_response_bytes` containing the total byte count of all raw response bodies received from the Upstream_API during that tool call as a non-negative integer.
5. THE MCP_Server SHALL measure MCP request size as the byte length of the raw incoming request body before deserialization.
6. THE MCP_Server SHALL measure MCP response size as the byte length of the fully serialized JSON response string encoded to UTF-8.
7. THE MCP_Server SHALL measure upstream request size as the sum of byte lengths of each JSON-serialized request body encoded to UTF-8 sent to the Upstream_API.
8. THE MCP_Server SHALL measure upstream response size as the sum of byte lengths of each raw response body received from the Upstream_API.
9. IF a `tools/call` request completes without making any Upstream_API calls, THEN THE Tool_Call_Event SHALL report `upstream_request_bytes` as 0 and `upstream_response_bytes` as 0.

### Requirement 3: Upstream API Response Code Logging

**User Story:** As an operator, I want the upstream API HTTP status code logged on both summary and retry events, so that I can correlate failures with specific HTTP responses.

#### Acceptance Criteria

1. WHEN a `tools/call` request completes successfully, THE Tool_Call_Event SHALL include `upstream_status_code` as an integer containing the HTTP status code of the final successful Upstream_API response.
2. WHEN a `tools/call` request fails due to a FellowApiError, THE Tool_Call_Event SHALL include `upstream_status_code` as an integer containing the HTTP status code from the error.
3. WHEN a `tools/call` request fails due to a PaginationError, THE Tool_Call_Event SHALL include `upstream_status_code` as an integer containing the last HTTP status code received from the Upstream_API before the pagination failure.
4. WHEN a retry is triggered by a transient error, THE Retry_Event SHALL include `status_code` as an integer containing the HTTP status code that caused the retry.
5. WHEN a retry is triggered by a request timeout, THE Retry_Event SHALL include `status_code` with the integer value 408.
6. IF a `tools/call` request completes without making any Upstream_API calls, THEN THE Tool_Call_Event SHALL omit the `upstream_status_code` field.

### Requirement 4: Per-Call Detail Logging for Paginated Requests

**User Story:** As an operator, I want to see individual upstream API call details for paginated requests, so that I can identify which specific page fetch is causing latency.

#### Acceptance Criteria

1. WHEN the MCP_Server makes an HTTP request to the Upstream_API, THE MCP_Server SHALL emit an API_Call_Event at DEBUG level containing: `duration_ms` (rounded to two decimal places), `status_code`, `request_bytes` (byte length of the serialized JSON request body, 0 if no body), and `response_bytes` (byte length of the raw response body) for that individual call.
2. WHEN a `tools/call` request involves multiple upstream API calls (pagination), THE Tool_Call_Event SHALL include an `upstream_api_calls` array where each element contains `{"page": <number>, "duration_ms": <number>, "status_code": <number>, "request_bytes": <number>, "response_bytes": <number>}`, with entries ordered by page number starting at 1.
3. WHEN a `tools/call` request involves a single upstream API call (non-paginated), THE Tool_Call_Event SHALL include `upstream_api_calls` as a single-element array with `page` set to 1.
4. THE MCP_Server SHALL set the `upstream_api_ms` value in `timings.steps` equal to the sum of `duration_ms` values across all entries in `upstream_api_calls`.
5. IF an upstream API call fails (timeout, network error, or HTTP status >= 400), THEN THE MCP_Server SHALL still include an entry in the `upstream_api_calls` array for that call with `duration_ms` set to the elapsed time before failure, `status_code` set to the HTTP status code received (or 0 if no response was received), and `request_bytes` and `response_bytes` reflecting actual bytes sent and received.

### Requirement 5: Enhanced Retry Event Logging

**User Story:** As an operator, I want retry events to carry the same structured metrics as the summary event, so that I can understand the state of the request at each retry point.

#### Acceptance Criteria

1. WHEN a retry is triggered, THE Retry_Event SHALL include a `timings` field containing `total_elapsed_ms` representing the cumulative wall-clock time in milliseconds from the start of the original request to the point of the retry, including the failed attempt that triggered the retry.
2. WHEN a retry is triggered, THE Retry_Event SHALL include `upstream_request_bytes` and `upstream_response_bytes` as integer values representing the cumulative byte sizes of all upstream request bodies sent and response bodies received, including the failed attempt that triggered the retry.
3. WHEN a retry is triggered, THE Retry_Event SHALL include the `upstream_api_calls` array where each entry contains `page`, `duration_ms`, `status_code`, `request_bytes`, and `response_bytes` for each upstream API call made up to and including the failed attempt that triggered the retry.
4. IF a retry is triggered before any upstream API call has completed, THEN THE Retry_Event SHALL include an empty `upstream_api_calls` array, `upstream_request_bytes` of 0, `upstream_response_bytes` of 0, and a `timings` field with `total_elapsed_ms` reflecting only the local processing time elapsed.

### Requirement 6: Consistent Metric Presence on All Request Log Events

**User Story:** As an operator, I want all request-related log events to carry the standard metric fields, so that I can query and filter logs uniformly.

#### Acceptance Criteria

1. THE MCP_Server SHALL include `timings`, `mcp_request_bytes`, `upstream_request_bytes`, and `upstream_response_bytes` on every Tool_Call_Event and Retry_Event emitted during request handling.
2. THE MCP_Server SHALL include `mcp_response_bytes` only on the Tool_Call_Event, since the MCP response is not yet constructed at the time of Retry_Event and API_Call_Event emission.
3. THE API_Call_Event SHALL include only per-call fields (`duration_ms`, `status_code`, `request_bytes`, `response_bytes`) and SHALL NOT include cumulative metrics (`timings`, `mcp_request_bytes`, `upstream_request_bytes`, `upstream_response_bytes`).
4. IF a metric value is not yet available at the time of log emission, THEN THE MCP_Server SHALL omit that field rather than logging a zero or null value.
