#!/usr/bin/env bash
# Fellow MCP Server - macOS Bootstrap Script
# Downloads dependencies and prepares the server for use with AWS Quick Desktop.
#
# Usage:
#   chmod +x scripts/bootstrap-macos.sh
#   ./scripts/bootstrap-macos.sh
#
# After running, follow the printed instructions to configure AWS Quick.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_DIR/venv"
REQUIRED_PYTHON_VERSION="3.12"

echo "====================================="
echo " Fellow MCP Server - macOS Bootstrap"
echo "====================================="
echo ""

# --- Check for Python 3.12 ---
check_python() {
    # Try python3.12 first, then python3
    if command -v python3.12 &>/dev/null; then
        PYTHON_CMD="python3.12"
    elif command -v python3 &>/dev/null; then
        PYTHON_CMD="python3"
    else
        echo "ERROR: Python 3 not found."
        echo ""
        echo "Install Python ${REQUIRED_PYTHON_VERSION} using one of:"
        echo "  brew install python@${REQUIRED_PYTHON_VERSION}"
        echo "  Or download from https://www.python.org/downloads/"
        exit 1
    fi

    # Verify version
    PY_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
    PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

    if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 12 ]; }; then
        echo "ERROR: Python ${REQUIRED_PYTHON_VERSION}+ is required (found $PY_VERSION)."
        echo ""
        echo "Install Python ${REQUIRED_PYTHON_VERSION} using one of:"
        echo "  brew install python@${REQUIRED_PYTHON_VERSION}"
        echo "  Or download from https://www.python.org/downloads/"
        exit 1
    fi

    echo "[OK] Found $PYTHON_CMD ($PY_VERSION)"
}

# --- Create virtual environment ---
create_venv() {
    if [ -d "$VENV_DIR" ]; then
        echo "[OK] Virtual environment already exists at $VENV_DIR"
    else
        echo "[..] Creating virtual environment..."
        $PYTHON_CMD -m venv "$VENV_DIR"
        echo "[OK] Virtual environment created"
    fi
}

# --- Install dependencies ---
install_deps() {
    echo "[..] Installing dependencies..."
    "$VENV_DIR/bin/pip" install --quiet --upgrade pip
    "$VENV_DIR/bin/pip" install --quiet -r "$PROJECT_DIR/requirements.txt"
    echo "[OK] Dependencies installed"
}

# --- Create .env if missing ---
setup_env() {
    if [ ! -f "$PROJECT_DIR/.env" ]; then
        echo "[..] Creating .env from .env.example..."
        cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
        echo "[!!] IMPORTANT: Edit $PROJECT_DIR/.env with your Fellow API credentials"
    else
        echo "[OK] .env file exists"
    fi
}

# --- Create the wrapper script ---
create_wrapper() {
    WRAPPER="$PROJECT_DIR/scripts/run-stdio.sh"
    cat > "$WRAPPER" << 'WRAPPER_EOF'
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
WRAPPER_EOF
    chmod +x "$WRAPPER"
    echo "[OK] Wrapper script created: $WRAPPER"
}

# --- Run bootstrap ---
check_python
create_venv
install_deps
setup_env
create_wrapper

echo ""
echo "====================================="
echo " Bootstrap Complete!"
echo "====================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Edit your .env file with your Fellow API credentials:"
echo "   $PROJECT_DIR/.env"
echo ""
echo "2. In AWS Quick Desktop, add a new Local MCP server with:"
echo ""
echo "   Name:      Fellow MCP"
echo "   Command:   $PROJECT_DIR/scripts/run-stdio.sh"
echo "   Arguments: (leave empty)"
echo "   Timeout:   60"
echo ""
echo "   Environment variables (add these in the Quick UI):"
echo "   FELLOW_API_KEY       = <your Fellow API key>"
echo "   FELLOW_SUBDOMAIN     = <your Fellow workspace subdomain>"
echo ""
echo "   Optional environment variables:"
echo "   TZ                   = America/Los_Angeles"
echo "   LOG_LEVEL            = INFO"
echo ""
echo "3. Click 'Test connection' to verify, then '+ Add MCP'"
echo ""
