# Implementation Plan: Fellow MCP Server

## Overview

Implement a custom MCP (Model Context Protocol) server in Python that bridges MCP-compatible clients to the Fellow.ai Developer API. The server runs as a Docker container, accepts JSON-RPC 2.0 over HTTP, and provides full CRUD coverage of Fellow.ai resources (action items, notes, recordings, webhooks, user info) with retry logic, rate limiting, cursor pagination, structured logging, and token-based authentication.

## Tasks

- [x] 1. Project scaffolding and configuration
  - [x] 1.1 Create project structure, dependency files, and app factory
    - Create directory structure matching the design: `app/`, `app/auth/`, `app/mcp/`, `app/tools/`, `app/validation/`, `app/client/`, `app/logging/`, `tests/`, `tests/unit/`, `tests/integration/`, `tests/property/`
    - Create `requirements.txt` with pinned versions: Flask==3.0.0, gunicorn==21.2.0, requests==2.31.0, tenacity==8.2.3, structlog==23.2.0, jsonschema==4.20.0, python-dotenv==1.0.0
    - Create `requirements-dev.txt` with: pytest==7.4.3, pytest-flask==1.3.0, pytest-mock==3.12.0, hypothesis==6.92.1, responses==0.24.1, black==23.11.0, flake8==6.1.0, mypy==1.7.1, pytest-cov==4.1.0
    - Create `app/__init__.py` and all sub-package `__init__.py` files
    - Create `.env.example` with all env vars documented
    - Create `app/main.py` with Flask app factory pattern and `/mcp` and `/health` route registration
    - _Requirements: 1.1, 3.1, 3.6, 3.9_

  - [x] 1.2 Implement configuration module with environment variable validation
    - Create `app/config.py` with frozen `AppConfig` dataclass
    - Implement `from_env()` class method that loads and validates all env vars
    - Validate required vars (`FELLOW_API_KEY`, `FELLOW_SUBDOMAIN`) are present and non-empty
    - Validate `MCP_AUTH_TOKEN` is ≥16 chars when `MCP_AUTH_ENABLED` is "true"
    - Validate `GUNICORN_WORKERS` is integer in [1, 8], default 2
    - Validate `LOG_LEVEL` is in accepted set, default to INFO with warning on invalid
    - Raise `SystemExit` with descriptive error messages on validation failure
    - _Requirements: 2.4, 2.5, 2.6, 3.3, 3.6, 3.7, 3.8, 10.5, 10.6_

  - [x] 1.3 Write property test for configuration validation
    - **Property 3: Configuration validation rejects invalid startup state**
    - **Validates: Requirements 2.5, 2.6, 3.7, 3.8**

  - [x] 1.4 Write unit tests for configuration module
    - Test valid configurations load correctly
    - Test missing required vars produce descriptive errors
    - Test auth token length enforcement
    - Test worker count range enforcement
    - Test log level fallback behavior
    - _Requirements: 2.4, 2.5, 2.6, 3.7, 3.8, 10.5, 10.6_

- [x] 2. Structured logging setup
  - [x] 2.1 Implement structlog configuration
    - Create `app/logging/setup.py` with structlog JSON processor chain
    - Configure log level from `AppConfig.log_level`
    - Add request_id context variable binding for correlation
    - Implement Flask `before_request` hook to generate and bind unique `request_id` per request
    - Ensure all log entries include the `request_id` field
    - _Requirements: 10.1, 10.5, 10.6, 10.7_

  - [x] 2.2 Write property test for request ID correlation
    - **Property 12: Request ID correlates all log entries**
    - **Validates: Requirements 10.7**

- [x] 3. Authentication guard
  - [x] 3.1 Implement auth guard middleware
    - Create `app/auth/guard.py` with `AuthGuard` class
    - Implement `check_request()` method that returns `None` (pass) or error `Response` (reject)
    - Use `hmac.compare_digest` for constant-time token comparison
    - Return HTTP 401 with JSON error body on auth failure
    - Skip validation entirely when auth is disabled
    - Log rejection reason and client IP at WARNING level
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 10.4_

  - [x] 3.2 Write property test for auth guard correctness
    - **Property 2: Auth guard correctness**
    - **Validates: Requirements 2.1, 2.3, 2.4**

  - [x] 3.3 Write unit tests for auth guard
    - Test valid token passes
    - Test invalid token returns 401
    - Test missing header returns 401
    - Test auth disabled allows all requests
    - Test constant-time comparison is used
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 4. MCP protocol layer
  - [x] 4.1 Implement JSON-RPC parsing and MCP message handling
    - Create `app/mcp/errors.py` with error code constants (-32700, -32600, -32601, -32602, -32603)
    - Create `app/mcp/protocol.py` with `parse_jsonrpc_request()`, `build_tool_result()`, `build_tools_list_response()`, `build_jsonrpc_error()`
    - Validate JSON-RPC 2.0 envelope: `jsonrpc` field must be "2.0", `method` field required
    - For `tools/call`: validate `params.name` and `params.arguments` are present
    - Return appropriate error codes for each failure mode
    - _Requirements: 1.1, 1.3, 1.4, 1.5_

  - [x] 4.2 Implement tool registry
    - Create `app/mcp/registry.py` with `ToolRegistry` class
    - Implement `register()`, `get_handler()`, `list_tools()` methods
    - Raise `ToolNotFoundError` for unknown tool names
    - Store tool definitions (name, description, input_schema) for `tools/list`
    - _Requirements: 1.2, 1.4, 1.6_

  - [x] 4.3 Write property test for malformed input handling
    - **Property 1: Malformed input always produces valid JSON-RPC error**
    - **Validates: Requirements 1.3, 1.6**

  - [x] 4.4 Write unit tests for protocol and registry
    - Test valid JSON-RPC parsing
    - Test invalid JSON returns -32700
    - Test missing fields returns -32600
    - Test unknown method returns -32601
    - Test unknown tool returns -32602
    - Test tools/list returns all registered tools
    - _Requirements: 1.1, 1.3, 1.4, 1.5, 1.6_

- [x] 5. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Fellow API client layer
  - [x] 6.1 Implement token bucket rate limiter
    - Create `app/client/rate_limiter.py` with `TokenBucketRateLimiter` class
    - Implement thread-safe token bucket with `max_per_second=3.0`
    - `acquire()` blocks until a token is available using `threading.Lock`
    - Refill tokens based on elapsed time since last refill
    - _Requirements: 4.5_

  - [x] 6.2 Implement Fellow API HTTP client with retry logic
    - Create `app/client/fellow_api.py` with `FellowApiClient` class
    - Implement `get()`, `post()`, `put()`, `delete()` methods
    - Set `X-API-KEY` header from config
    - Construct base URL as `https://{subdomain}.fellow.app`
    - Use tenacity for retry: initial delay 1s, multiplier 2, max 3 retries
    - Retry on HTTP 429, 500, 502, 503, 504 and timeouts
    - Honor `Retry-After` header on 429 responses
    - Set 30-second timeout per request
    - Integrate rate limiter `acquire()` before each request
    - Implement `health_check()` method for `/health` endpoint
    - Raise `FellowApiError` on non-transient failure after retries
    - Log retry attempts at WARNING level with attempt number, wait duration, reason
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 10.3_

  - [x] 6.3 Implement cursor paginator
    - Create `app/client/paginator.py` with `CursorPaginator` class
    - Implement `fetch_all()` method that iterates pages until cursor is null or max_pages (20) reached
    - Use page_size=50 by default
    - Return `(combined_results, was_truncated)` tuple
    - Concatenate results in page order (first page first)
    - Include truncation indicator when stopped by page limit
    - Raise `PaginationError` with page number on mid-pagination failure, discarding partial results
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

  - [x] 6.4 Write property test for rate limiter
    - **Property 9: Rate limiter enforces 3 requests per second**
    - **Validates: Requirements 4.5**

  - [x] 6.5 Write property test for retry logic
    - **Property 8: Retry logic on transient errors**
    - **Validates: Requirements 4.3, 4.4, 4.8**

  - [x] 6.6 Write property tests for pagination
    - **Property 10: Pagination combines results in order and terminates correctly**
    - **Validates: Requirements 12.1, 12.2, 12.4, 12.5**
    - **Property 11: Mid-pagination failure discards partial results**
    - **Validates: Requirements 12.6**

  - [x] 6.7 Write unit tests for rate limiter, API client, and paginator
    - Test rate limiter blocks when tokens exhausted
    - Test retry on transient errors with correct backoff
    - Test Retry-After header honored
    - Test timeout treated as transient error
    - Test paginator combines multiple pages in order
    - Test paginator stops at null cursor
    - Test paginator stops at max page limit with truncation flag
    - Test paginator discards results on mid-pagination failure
    - _Requirements: 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

- [x] 7. Input validation
  - [x] 7.1 Implement input validation module with JSON schemas
    - Create `app/validation/schemas.py` with `InputValidator` class
    - Define JSON schemas for all 16 tools' input parameters
    - Validate required parameters are present
    - Validate types and formats (IDs: 1-255 chars, dates: ISO 8601, page_size: 1-50)
    - Validate enum values (scope, ordering, enabled_events, note includes, recording includes)
    - Validate webhook URL length (1-2048 chars)
    - Collect ALL validation errors before returning (not fail-fast)
    - Ignore unrecognized parameters silently
    - Include allowed values in enum validation error messages
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 8.6, 8.7, 8.8, 6.6, 7.6_

  - [x] 7.2 Write property tests for input validation
    - **Property 4: Input validation reports all errors simultaneously**
    - **Validates: Requirements 11.1, 11.2, 11.6, 11.7, 11.8**
    - **Property 5: ID and string constraint validation**
    - **Validates: Requirements 11.3, 11.4, 8.8**
    - **Property 6: Enum validation rejects invalid values and lists allowed values**
    - **Validates: Requirements 6.6, 7.6, 8.6, 8.7, 11.6**

  - [x] 7.3 Write unit tests for input validation
    - Test missing required params lists all missing names
    - Test invalid types produce clear error messages
    - Test ID length boundaries (empty, 255, 256)
    - Test date format validation (valid and invalid)
    - Test page_size boundaries (0, 1, 50, 51)
    - Test enum rejection includes allowed values
    - Test unrecognized params are ignored
    - Test multiple errors returned in single response
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8_

- [x] 8. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Tool handlers
  - [x] 9.1 Implement action items tool handlers
    - Create `app/tools/action_items.py` with handlers for: `list_action_items`, `get_action_item`, `complete_action_item`, `archive_action_item`
    - `list_action_items`: POST to `/api/v1/action_items` with optional filters (completed, archived, ai_detected, scope, ordering), use paginator for results
    - `get_action_item`: GET to `/api/v1/action_item/{id}`
    - `complete_action_item`: POST to `/api/v1/action_item/{id}/complete` with `{"completed": true/false}`
    - `archive_action_item`: POST to `/api/v1/action_item/{id}/archive`
    - Return updated action item on success for complete/archive
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

  - [x] 9.2 Implement notes tool handlers
    - Create `app/tools/notes.py` with handlers for: `list_notes`, `get_note`, `delete_note`
    - `list_notes`: POST to `/api/v1/notes` with optional filters and include options (event_attendees, content_markdown), use paginator
    - `get_note`: GET to `/api/v1/note/{id}`
    - `delete_note`: DELETE to `/api/v1/note/{id}`, return success confirmation
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 9.3 Implement recordings tool handlers
    - Create `app/tools/recordings.py` with handlers for: `list_recordings`, `get_recording`, `delete_recording`
    - `list_recordings`: POST to `/api/v1/recordings` with optional filters, includes (transcript, ai_notes), and media_url flag, use paginator
    - `get_recording`: GET to `/api/v1/recording/{id}` with optional include params
    - `delete_recording`: DELETE to `/api/v1/recording/{id}`
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 9.4 Implement webhooks tool handlers
    - Create `app/tools/webhooks.py` with handlers for: `list_webhooks`, `get_webhook`, `create_webhook`, `update_webhook`, `delete_webhook`
    - `create_webhook`: POST to `/api/v1/webhook` with url, enabled_events, description, status
    - `list_webhooks`: GET to `/api/v1/webhook` with optional limit and cursor params
    - `get_webhook`: GET to `/api/v1/webhook/{id}`
    - `update_webhook`: PUT to `/api/v1/webhook/{id}` with updatable fields
    - `delete_webhook`: DELETE to `/api/v1/webhook/{id}`
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 9.5 Implement user info tool handler
    - Create `app/tools/user.py` with handler for `get_current_user`
    - GET to `/api/v1/me`, return user info (user ID, full name, email, workspace ID, workspace name, workspace subdomain)
    - Handle 401 response with specific error message about invalid/expired API key
    - _Requirements: 9.1, 9.2_

  - [x] 9.6 Write property test for filter passthrough
    - **Property 7: Filter parameters pass through to Fellow API requests**
    - **Validates: Requirements 5.1, 6.1, 7.1**

  - [x] 9.7 Write unit tests for tool handlers
    - Test each tool handler makes correct API call with correct parameters
    - Test paginated results combined for list tools
    - Test complete_action_item sends correct body for both complete and incomplete
    - Test delete operations return confirmation
    - Test get_current_user handles 401 with specific message
    - Test webhook enabled_events validated before API call
    - _Requirements: 5.1–5.7, 6.1–6.5, 7.1–7.5, 8.1–8.5, 9.1, 9.2_

- [x] 10. Wire everything together — app factory and endpoint routing
  - [x] 10.1 Register all tools and wire Flask endpoint
    - Update `app/main.py` to create Flask app with app factory pattern
    - Initialize `AppConfig.from_env()`, structured logging, auth guard, tool registry, Fellow API client
    - Register all 16 tools in the `ToolRegistry` with schemas and handlers
    - Implement `/mcp` POST endpoint: auth check → parse JSON-RPC → dispatch method → validate input → execute handler → return response
    - Implement `/health` GET endpoint: return status and Fellow API connectivity
    - Log tool name, execution duration, and outcome at INFO level for each tool call
    - Create `gunicorn.conf.py` with worker config from env
    - _Requirements: 1.1, 1.2, 1.4, 1.5, 3.4, 3.5, 3.9, 10.2_

  - [x] 10.2 Write integration tests for full endpoint flow
    - Test complete tool call lifecycle through Flask test client
    - Test auth rejection before tool execution
    - Test malformed JSON-RPC returns proper error
    - Test unknown tool returns -32602
    - Test validation error returns all errors
    - Test Fellow API error propagates correctly
    - Test health endpoint with reachable and unreachable Fellow API
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 3.4, 3.5_

- [x] 11. Docker deployment
  - [x] 11.1 Create Dockerfile and docker-compose.yml
    - Create multi-stage `Dockerfile` with Python 3.11 base
    - Builder stage: install dependencies
    - Production stage: copy app, create non-root user, set CMD to gunicorn
    - Run as non-root user inside container
    - Expose port 8000
    - Add HEALTHCHECK instruction using `/health` endpoint
    - Create `docker-compose.yml` with env_file, port mapping, and health check
    - _Requirements: 3.1, 3.2, 3.3, 3.9_

- [x] 12. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The design specifies Python (Flask + Gunicorn), so all code uses Python 3.11
- Always run tests within the venv using `python3 -m pytest`
- Use `docker compose` (not `docker-compose`) for container operations

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1"] },
    { "id": 2, "tasks": ["1.3", "1.4", "2.2", "3.1"] },
    { "id": 3, "tasks": ["3.2", "3.3", "4.1"] },
    { "id": 4, "tasks": ["4.2", "4.3", "4.4"] },
    { "id": 5, "tasks": ["6.1", "6.2", "7.1"] },
    { "id": 6, "tasks": ["6.3", "6.4", "6.5", "7.2", "7.3"] },
    { "id": 7, "tasks": ["6.6", "6.7", "9.1", "9.2", "9.3", "9.4", "9.5"] },
    { "id": 8, "tasks": ["9.6", "9.7", "10.1"] },
    { "id": 9, "tasks": ["10.2", "11.1"] }
  ]
}
```
