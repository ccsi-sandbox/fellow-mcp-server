#!/usr/bin/env bash
# Wrapper script for running Fellow MCP Server in stdio mode.
# Used as the Command target in AWS Quick Desktop MCP configuration.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load environment variables from .env
set -a
source "$PROJECT_DIR/.env" 2>/dev/null || true
set +a

# Execute the stdio server
cd "$PROJECT_DIR" || exit 1
exec "$PROJECT_DIR/venv/bin/python3" -m app --stdio
