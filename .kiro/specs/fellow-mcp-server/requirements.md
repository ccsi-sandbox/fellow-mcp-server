# Requirements Document

## Introduction

This document defines the requirements for a custom MCP (Model Context Protocol) server that bridges AWS Q Developer desktop client to the Fellow.ai Developer API. The server runs as a Docker container on the user's local network, accepting MCP tool calls over HTTP and translating them into Fellow.ai REST API requests. It provides full CRUD coverage of the Fellow.ai API (action items, notes, recordings, webhooks, user info), unlike Fellow's own read-only MCP server. Authentication is handled via a configurable custom header mechanism that avoids the OAuth complexity of Fellow's native MCP server.

## Glossary

- **MCP_Server**: The custom Model Context Protocol server application that receives MCP tool call requests over HTTP and translates them into Fellow.ai API calls
- **Fellow_API**: The Fellow.ai Developer REST API (v1.0.2) accessed at `https://{subdomain}.fellow.app`
- **MCP_Client**: The AI tooling (AWS Q Developer) that connects to the MCP_Server via HTTP to invoke tools
- **Auth_Guard**: The middleware component responsible for validating the `X-MCP-AUTH-TOKEN` header on incoming requests
- **Tool_Router**: The component that maps incoming MCP tool call requests to the appropriate Fellow_API endpoint handler
- **Rate_Limiter**: The component that enforces Fellow.ai's rate limits (3 requests/second, 10,000 requests/day) to prevent API throttling
- **Cursor_Paginator**: The component that handles cursor-based pagination when retrieving multi-page results from the Fellow_API

## Requirements

### Requirement 1: MCP HTTP Transport

**User Story:** As an MCP_Client user, I want to connect to the MCP_Server over HTTP, so that I can invoke Fellow.ai tools from AI development environments that support HTTP-based MCP servers.

#### Acceptance Criteria

1. THE MCP_Server SHALL expose an HTTP POST endpoint at a configurable path (default `/mcp`) that accepts MCP protocol messages in JSON format and returns responses with Content-Type `application/json`
2. WHEN the MCP_Server receives a valid MCP tool call request, THE Tool_Router SHALL route the request to the corresponding Fellow_API handler and return the result in MCP protocol response format
3. WHEN the MCP_Server receives a malformed MCP request (invalid JSON or missing required MCP protocol fields), THE MCP_Server SHALL return an MCP-compliant JSON-RPC error response with an error code and message indicating the nature of the malformation
4. THE MCP_Server SHALL support the MCP `tools/list` method by returning all available tool definitions with their names, descriptions, and input schemas
5. THE MCP_Server SHALL support the MCP `tools/call` method by executing the requested tool and returning the result
6. IF the MCP_Server receives a `tools/call` request with a tool name that does not match any registered tool, THEN THE MCP_Server SHALL return an MCP-compliant error response indicating that the requested tool was not found

### Requirement 2: Custom Header Authentication

**User Story:** As a server operator, I want to protect the MCP_Server with a simple token-based authentication header, so that unauthorized clients on the local network cannot invoke Fellow.ai tools.

#### Acceptance Criteria

1. WHILE authentication is enabled, THE Auth_Guard SHALL reject any request that does not include the `X-MCP-AUTH-TOKEN` header, or includes a header value that does not match the configured token, with an HTTP 401 response and a JSON body containing an error message indicating the authentication failure reason
2. WHILE authentication is enabled, THE Auth_Guard SHALL compare the `X-MCP-AUTH-TOKEN` header value against the `MCP_AUTH_TOKEN` environment variable using a constant-time comparison
3. WHILE authentication is disabled, THE Auth_Guard SHALL allow all requests without requiring the `X-MCP-AUTH-TOKEN` header
4. THE MCP_Server SHALL determine authentication mode from the `MCP_AUTH_ENABLED` environment variable where a case-sensitive value of "true" enables authentication and any other value, including unset or empty, disables authentication
5. IF the `MCP_AUTH_TOKEN` environment variable is empty or unset while authentication is enabled, THEN THE MCP_Server SHALL refuse to start and log an error describing the misconfiguration
6. IF the `MCP_AUTH_TOKEN` environment variable is set to a value shorter than 16 characters while authentication is enabled, THEN THE MCP_Server SHALL refuse to start and log an error indicating the token does not meet the minimum length requirement

### Requirement 3: Docker Container Deployment

**User Story:** As a server operator, I want to run the MCP_Server as a Docker container, so that I can deploy it easily on my local network with minimal setup.

#### Acceptance Criteria

1. THE MCP_Server SHALL run inside a Docker container built from a multi-stage Dockerfile with a Python 3.11 base image
2. THE MCP_Server SHALL execute as a non-root user inside the container
3. THE MCP_Server SHALL use Gunicorn 21.2.0 as the WSGI server with a worker count configured via the `GUNICORN_WORKERS` environment variable, defaulting to 2 workers when the variable is unset
4. THE MCP_Server SHALL expose a `/health` endpoint on port 8000 that returns HTTP 200 with a JSON body containing a server status field indicating "healthy" and a Fellow_API connectivity field indicating "reachable" or "unreachable" based on whether the Fellow_API base URL responds successfully
5. IF the `/health` endpoint determines that the Fellow_API is unreachable, THEN THE MCP_Server SHALL still return HTTP 200 but set the Fellow_API connectivity field to "unreachable"
6. THE MCP_Server SHALL support configuration exclusively through environment variables for: `FELLOW_API_KEY`, `FELLOW_SUBDOMAIN`, `MCP_AUTH_ENABLED`, `MCP_AUTH_TOKEN`, `GUNICORN_WORKERS`, and `LOG_LEVEL`
7. WHEN the container starts, THE MCP_Server SHALL validate that all required environment variables (`FELLOW_API_KEY`, `FELLOW_SUBDOMAIN`) are present and refuse to start with an error message identifying which required variables are missing
8. IF the `GUNICORN_WORKERS` environment variable is set to a non-integer value or a value outside the range of 1 to 8, THEN THE MCP_Server SHALL refuse to start with an error message indicating the invalid worker count configuration
9. THE MCP_Server SHALL listen on port 8000 inside the container for all incoming HTTP requests

### Requirement 4: Fellow.ai API Client

**User Story:** As a developer using AI tooling, I want the MCP_Server to communicate reliably with the Fellow.ai API, so that tool calls succeed consistently despite transient network issues.

#### Acceptance Criteria

1. THE MCP_Server SHALL authenticate all requests to the Fellow_API using the `X-API-KEY` header with the value from the `FELLOW_API_KEY` environment variable
2. THE MCP_Server SHALL construct Fellow_API base URLs using the pattern `https://{FELLOW_SUBDOMAIN}.fellow.app`
3. WHEN a Fellow_API request fails with a transient error (HTTP 429, 500, 502, 503, 504), THE MCP_Server SHALL retry the request using exponential backoff with an initial delay of 1 second, a multiplier of 2, and a maximum of 3 retry attempts
4. WHEN a Fellow_API response includes a `Retry-After` header with HTTP 429, THE MCP_Server SHALL use the `Retry-After` value as the delay before the next retry attempt instead of the calculated exponential backoff delay
5. THE Rate_Limiter SHALL enforce a maximum of 3 requests per second to the Fellow_API by delaying excess requests until capacity is available
6. THE MCP_Server SHALL set a timeout of 30 seconds for each individual Fellow_API request
7. IF a Fellow_API request exceeds the 30-second timeout, THEN THE MCP_Server SHALL treat the timeout as a transient error eligible for retry per criterion 3
8. WHEN the Fellow_API returns an error response (HTTP 4xx or 5xx after retries are exhausted), THE MCP_Server SHALL return an MCP error response containing the HTTP status code and error message from the Fellow_API

### Requirement 5: Action Items Tools

**User Story:** As a developer using AI tooling, I want to manage Fellow.ai action items through MCP tools, so that I can view, complete, and archive action items without leaving my development environment.

#### Acceptance Criteria

1. WHEN the `list_action_items` tool is called, THE MCP_Server SHALL send a POST request to `/api/v1/action_items` with optional filters for completed status, archived status, ai_detected flag, scope (assigned_to_me, assigned_to_others, all), and ordering (created_at_desc, created_at_asc, due_date)
2. WHEN the `get_action_item` tool is called with an action item ID, THE MCP_Server SHALL send a GET request to `/api/v1/action_item/{id}` and return the action item details
3. WHEN the `complete_action_item` tool is called with an action item ID and a completion state of "complete", THE MCP_Server SHALL send a POST request to `/api/v1/action_item/{id}/complete` with a body containing `completed` set to `true`
4. WHEN the `complete_action_item` tool is called with an action item ID and a completion state of "incomplete", THE MCP_Server SHALL send a POST request to `/api/v1/action_item/{id}/complete` with a body containing `completed` set to `false`
5. WHEN the `archive_action_item` tool is called with an action item ID, THE MCP_Server SHALL send a POST request to `/api/v1/action_item/{id}/archive`
6. WHEN the `complete_action_item` or `archive_action_item` tool completes successfully, THE MCP_Server SHALL return the updated action item as received from the Fellow_API response
7. WHEN the `list_action_items` tool returns paginated results, THE Cursor_Paginator SHALL automatically retrieve all pages and return the combined results to the MCP_Client

### Requirement 6: Notes Tools

**User Story:** As a developer using AI tooling, I want to search and retrieve Fellow.ai meeting notes through MCP tools, so that I can reference meeting content directly from my development environment.

#### Acceptance Criteria

1. WHEN the `list_notes` tool is called, THE MCP_Server SHALL send a POST request to `/api/v1/notes` with optional filters for event_guid, created_at_start, created_at_end, updated_at_start, updated_at_end, channel_id, title, and event_attendees
2. WHEN the `list_notes` tool is called with include options, THE MCP_Server SHALL request the specified includes (limited to `event_attendees` and `content_markdown`) from the Fellow_API in the request body alongside filters
3. WHEN the `get_note` tool is called with a note ID, THE MCP_Server SHALL send a GET request to `/api/v1/note/{id}` and return the note details including content
4. WHEN the `delete_note` tool is called with a note ID, THE MCP_Server SHALL send a DELETE request to `/api/v1/note/{id}` and return a confirmation indicating the operation succeeded
5. WHEN the `list_notes` tool returns paginated results, THE Cursor_Paginator SHALL automatically retrieve all pages and return the combined results to the MCP_Client
6. IF the `list_notes` tool is called with an include option not in the set (event_attendees, content_markdown), THEN THE MCP_Server SHALL return an MCP error response identifying the invalid include option

### Requirement 7: Recordings Tools

**User Story:** As a developer using AI tooling, I want to access Fellow.ai meeting recordings, transcripts, and AI-generated notes through MCP tools, so that I can review meeting content without switching applications.

#### Acceptance Criteria

1. WHEN the `list_recordings` tool is called, THE MCP_Server SHALL send a POST request to `/api/v1/recordings` with optional filters for event_guid, created_at_start, created_at_end, updated_at_start, updated_at_end, channel_id, and title
2. WHEN the `list_recordings` tool is called with include options, THE MCP_Server SHALL request the specified includes (limited to `transcript` and `ai_notes`) and a boolean `media_url` flag indicating whether to return pre-signed media URLs from the Fellow_API
3. WHEN the `get_recording` tool is called with a recording ID, THE MCP_Server SHALL send a GET request to `/api/v1/recording/{id}` with optional include parameters (transcript, ai_notes, media_url) and return the recording details
4. WHEN the `delete_recording` tool is called with a recording ID, THE MCP_Server SHALL send a DELETE request to `/api/v1/recording/{id}` and return the operation result
5. WHEN the `list_recordings` tool returns paginated results, THE Cursor_Paginator SHALL automatically retrieve all pages and return the combined results to the MCP_Client
6. IF the `list_recordings` or `get_recording` tool is called with an include option not in the set (transcript, ai_notes, media_url), THEN THE MCP_Server SHALL return an MCP error response identifying the invalid include option

### Requirement 8: Webhooks Management Tools

**User Story:** As a developer using AI tooling, I want to manage Fellow.ai webhooks through MCP tools, so that I can configure event-driven integrations without using the Fellow.ai web interface.

#### Acceptance Criteria

1. WHEN the `create_webhook` tool is called with a URL, enabled events, description, and status, THE MCP_Server SHALL send a POST request to `/api/v1/webhook` with the provided parameters
2. WHEN the `list_webhooks` tool is called, THE MCP_Server SHALL send a GET request to `/api/v1/webhook` with optional query parameters for limit (integer, 1 to 50, default 50) and cursor (string for pagination)
3. WHEN the `get_webhook` tool is called with a webhook ID, THE MCP_Server SHALL send a GET request to `/api/v1/webhook/{id}` and return the webhook details
4. WHEN the `update_webhook` tool is called with a webhook ID and one or more updatable fields (URL, enabled_events, description, status), THE MCP_Server SHALL send a PUT request to `/api/v1/webhook/{id}` with the provided parameters
5. WHEN the `delete_webhook` tool is called with a webhook ID, THE MCP_Server SHALL send a DELETE request to `/api/v1/webhook/{id}` and return the operation result
6. THE MCP_Server SHALL validate that enabled_events values are limited to: ai_note.shared_to_channel, ai_note.generated, action_item.assigned, action_item.completed
7. IF the `create_webhook` or `update_webhook` tool is called with an enabled_events list containing a value not in the allowed set, THEN THE MCP_Server SHALL return an MCP error response identifying the invalid event type without sending a request to the Fellow_API
8. THE MCP_Server SHALL validate that the webhook URL parameter is a non-empty string with a maximum length of 2048 characters before making Fellow_API requests

### Requirement 9: User Information Tool

**User Story:** As a developer using AI tooling, I want to retrieve my Fellow.ai user and workspace information through an MCP tool, so that I can verify my identity and workspace context.

#### Acceptance Criteria

1. WHEN the `get_current_user` tool is called with no input parameters, THE MCP_Server SHALL send a GET request to `/api/v1/me` and return the authenticated user information including user ID, full name, email, workspace ID, workspace name, and workspace subdomain
2. IF the Fellow_API returns an authentication error (HTTP 401) on the `/api/v1/me` endpoint, THEN THE MCP_Server SHALL return an MCP error response indicating that the Fellow API key is invalid or expired

### Requirement 10: Structured Logging

**User Story:** As a server operator, I want comprehensive structured logging from the MCP_Server, so that I can monitor operations and diagnose issues effectively.

#### Acceptance Criteria

1. THE MCP_Server SHALL use structlog for all log output in JSON format
2. WHEN the MCP_Server processes a tool call, THE MCP_Server SHALL log the tool name, execution duration in milliseconds, and outcome (success or failure) at INFO level
3. WHEN the MCP_Server retries a Fellow_API request, THE MCP_Server SHALL log the retry attempt number, wait duration in seconds, and reason at WARNING level
4. WHEN the Auth_Guard rejects a request, THE MCP_Server SHALL log the rejection reason and client IP address at WARNING level
5. THE MCP_Server SHALL support configurable log levels via the `LOG_LEVEL` environment variable accepting values DEBUG, INFO, WARNING, ERROR, or CRITICAL, with a default of INFO
6. IF the `LOG_LEVEL` environment variable is set to a value not in the accepted set, THEN THE MCP_Server SHALL default to INFO and log a warning at startup indicating the invalid value
7. THE MCP_Server SHALL include a request_id field in all log entries for a given request to enable correlation of log entries across a single tool call execution

### Requirement 11: Input Validation

**User Story:** As a server operator, I want all tool call inputs validated before processing, so that invalid data is rejected early and does not reach the Fellow.ai API.

#### Acceptance Criteria

1. WHEN a tool call includes required parameters that are missing, THE MCP_Server SHALL return an MCP error response listing all missing parameter names
2. WHEN a tool call includes parameters with invalid types or formats, THE MCP_Server SHALL return an MCP error response identifying each invalid parameter and the reason for rejection
3. THE MCP_Server SHALL validate action item IDs, note IDs, recording IDs, and webhook IDs as non-empty strings with a maximum length of 255 characters before making Fellow_API requests
4. THE MCP_Server SHALL validate that date filter parameters conform to ISO 8601 date format (YYYY-MM-DD) before making Fellow_API requests
5. THE MCP_Server SHALL validate that page_size parameters are integers between 1 and 50 inclusive
6. WHEN a tool call includes parameters with enumerated allowed values (scope, ordering, enabled_events), THE MCP_Server SHALL validate that the provided values match the defined allowed values and return an MCP error response listing the allowed values if validation fails
7. WHEN a tool call includes unrecognized parameter names, THE MCP_Server SHALL ignore the unrecognized parameters and process the request using only the recognized parameters
8. WHEN multiple validation failures are detected in a single tool call, THE MCP_Server SHALL return all validation errors in a single MCP error response rather than reporting only the first failure

### Requirement 12: Cursor Pagination Handling

**User Story:** As a developer using AI tooling, I want the MCP_Server to handle Fellow.ai's cursor-based pagination transparently, so that I receive complete result sets without managing pagination manually.

#### Acceptance Criteria

1. WHEN a Fellow_API response includes a non-null cursor value, THE Cursor_Paginator SHALL automatically request the next page using that cursor
2. THE Cursor_Paginator SHALL combine results from all pages into a single response returned to the MCP_Client, preserving the ordering returned by the Fellow_API across pages (first page results first, last page results last)
3. THE Cursor_Paginator SHALL use a default page_size of 50 to minimize the number of API requests
4. THE Cursor_Paginator SHALL stop pagination when the returned cursor is null or when a configured maximum page limit (default 20 pages, yielding up to 1000 results) is reached
5. IF the Cursor_Paginator reaches the maximum page limit, THEN THE MCP_Server SHALL include a truncation indicator in the response containing the total number of results returned and a flag signaling that additional results exist beyond the retrieved set
6. IF a Fellow_API request fails during pagination after one or more pages have been successfully retrieved, THEN THE MCP_Server SHALL discard partial results and return an MCP error response indicating the failure, including which page number failed
