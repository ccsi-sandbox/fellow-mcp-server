# Fellow MCP Server

A custom [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that bridges MCP-compatible AI tools to the [Fellow.ai Developer API](https://developer.fellow.app). Runs as a Docker container on your local network, accepting JSON-RPC 2.0 messages over HTTP.

Unlike Fellow's official read-only MCP server, this implementation provides **full CRUD coverage** of the Fellow.ai API — including completing action items, deleting notes, managing webhooks, and more — with simple token-based authentication that avoids OAuth complexity.

## Features

- **16 MCP tools** covering action items, notes, recordings, webhooks, and user info
- **Full CRUD** — list, get, create, update, delete operations where the Fellow API supports them
- **Automatic pagination** — transparently fetches all pages (up to 1,000 results) for list operations
- **Retry with backoff** — exponential backoff on transient errors (429, 5xx) with Retry-After support
- **Rate limiting** — built-in token bucket enforcing Fellow's 3 requests/second limit
- **Input validation** — validates all parameters before calling Fellow, reporting all errors at once
- **Structured logging** — JSON-formatted logs with per-request correlation IDs
- **Simple auth** — optional `X-MCP-AUTH-TOKEN` header with constant-time comparison
- **Docker-ready** — multi-stage build, non-root user, health check included

## Available Tools

| Tool | Description |
|------|-------------|
| `list_action_items` | List action items with filters (completed, archived, scope, ordering) |
| `get_action_item` | Get a single action item by ID |
| `complete_action_item` | Mark an action item as complete or incomplete |
| `archive_action_item` | Archive an action item |
| `list_notes` | List meeting notes with filters and include options |
| `get_note` | Get a single note by ID |
| `delete_note` | Delete a note |
| `list_recordings` | List recordings with filters, includes, and media URL option |
| `get_recording` | Get a recording with optional transcript/AI notes/media URL |
| `delete_recording` | Delete a recording |
| `list_webhooks` | List webhooks with optional limit and cursor |
| `get_webhook` | Get a single webhook by ID |
| `create_webhook` | Create a new webhook subscription |
| `update_webhook` | Update a webhook's URL, events, description, or status |
| `delete_webhook` | Delete a webhook |
| `get_current_user` | Get the authenticated user's info and workspace details |

## Quick Start

### 1. Get a Fellow API Key

Generate an API key from your Fellow.ai workspace at **Settings → Integrations → Developer API**.

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```dotenv
FELLOW_API_KEY=your-fellow-api-key
FELLOW_SUBDOMAIN=your-company
```

### 3. Run with Docker Compose

```bash
docker compose up --build -d
```

The server starts on port 8000. Verify it's running:

```bash
curl http://localhost:8000/health
# {"status": "healthy", "fellow_api": "reachable"}
```

## Configuration

All configuration is via environment variables. No config files needed.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `FELLOW_API_KEY` | **Yes** | — | Your Fellow.ai Developer API key |
| `FELLOW_SUBDOMAIN` | **Yes** | — | Your Fellow workspace subdomain (e.g., `acme` for `acme.fellow.app`) |
| `MCP_AUTH_ENABLED` | No | `false` | Set to `true` (case-sensitive) to require token authentication |
| `MCP_AUTH_TOKEN` | Conditional | — | Authentication token (min 16 characters). Required when `MCP_AUTH_ENABLED=true` |
| `GUNICORN_WORKERS` | No | `2` | Number of Gunicorn worker processes (1–8) |
| `LOG_LEVEL` | No | `INFO` | Log verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `MCP_ENDPOINT_PATH` | No | `/mcp` | HTTP path for the MCP endpoint |

### Startup Validation

The server validates configuration on startup and refuses to start with a descriptive error if:
- `FELLOW_API_KEY` or `FELLOW_SUBDOMAIN` is missing or empty
- `MCP_AUTH_TOKEN` is missing or shorter than 16 characters when auth is enabled
- `GUNICORN_WORKERS` is not an integer between 1 and 8

## Connecting an AI Tool

### MCP Client Configuration

Point your MCP-compatible client at the server's HTTP endpoint. For example, in an MCP client configuration:

```json
{
  "mcpServers": {
    "fellow": {
      "url": "http://localhost:8000/mcp",
      "headers": {
        "X-MCP-AUTH-TOKEN": "your-token-here"
      }
    }
  }
}
```

### Protocol Details

- **Transport**: HTTP POST
- **Endpoint**: `/mcp` (configurable via `MCP_ENDPOINT_PATH`)
- **Protocol**: JSON-RPC 2.0
- **Methods**: `tools/list`, `tools/call`
- **Content-Type**: `application/json`

### Example Request

```bash
# List available tools
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "X-MCP-AUTH-TOKEN: your-token-here" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'

# Call a tool
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "X-MCP-AUTH-TOKEN: your-token-here" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "get_current_user",
      "arguments": {}
    }
  }'
```

## Authentication

Authentication is **optional** and disabled by default. When enabled, every request to `/mcp` must include the `X-MCP-AUTH-TOKEN` header with a value matching the configured token.

To enable:

```dotenv
MCP_AUTH_ENABLED=true
MCP_AUTH_TOKEN=a-secure-random-token-at-least-16-chars
```

Requests with missing or invalid tokens receive HTTP 401 with a JSON error body. Token comparison uses constant-time comparison to prevent timing attacks.

## Health Endpoint

`GET /health` returns the server and Fellow API connectivity status:

```json
{"status": "healthy", "fellow_api": "reachable"}
```

The `fellow_api` field is `"unreachable"` if the Fellow API doesn't respond, but the server itself remains available. This endpoint is used by Docker's HEALTHCHECK.

## Deployment

### Docker Compose (Recommended)

```bash
docker compose up --build -d
```

### Docker (Manual)

```bash
docker build -t fellow-mcp-server .
docker run -d \
  --name fellow-mcp \
  -p 8000:8000 \
  --env-file .env \
  fellow-mcp-server
```

### Security Notes

- The container runs as a non-root user (`appuser`)
- Enable `MCP_AUTH_ENABLED=true` if the server is accessible beyond localhost
- The Fellow API key grants access to your workspace data — keep `.env` out of version control
- Consider placing behind a reverse proxy with TLS for non-local deployments

## Resilience

- **Retry**: Transient errors (HTTP 429, 500, 502, 503, 504, timeouts) are retried up to 3 times with exponential backoff (1s, 2s, 4s). The `Retry-After` header on 429 responses is honored.
- **Rate Limiting**: A token bucket enforces 3 requests/second to the Fellow API. Excess requests queue rather than fail.
- **Timeouts**: Each Fellow API request has a 30-second timeout.
- **Pagination**: List endpoints auto-paginate up to 20 pages (1,000 results). A truncation indicator is included when the limit is reached.

## Development

### Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### Run Tests

```bash
source venv/bin/activate
pytest                    # All tests
pytest -m unit            # Unit tests only
pytest -m property        # Property-based tests (Hypothesis)
pytest -m integration     # Integration tests
pytest --cov=app          # With coverage report
```

### Run Locally (without Docker)

```bash
source venv/bin/activate
export FELLOW_API_KEY=your-key
export FELLOW_SUBDOMAIN=your-subdomain
python3 app/main.py
```

## License

MIT
