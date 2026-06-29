# Fellow MCP Server — AWS Quick Desktop Setup

This guide walks through setting up the Fellow MCP Server as a **local MCP server** in the [AWS Quick](https://aws.amazon.com/quicksight/) desktop application. Quick manages the server process lifecycle — starting it when needed and stopping it when idle — so you don't need Docker or any manual process management.

## Prerequisites

- **AWS Quick Desktop** application installed and signed in
- **Fellow.ai API key** — generate one from your Fellow workspace at **Settings → Integrations → Developer API**
- **Python 3.12+** installed on your machine (the bootstrap script will verify this)

## How It Works

The Fellow MCP Server runs in **stdio transport mode** when used with AWS Quick. Instead of listening on an HTTP port, the server reads JSON-RPC messages from standard input and writes responses to standard output. Quick launches the server process automatically and communicates with it over this channel.

This means:
- No Docker required
- No port management or firewall configuration
- No manual process management
- Authentication is handled by the local process boundary (no token needed)

---

## macOS Setup

### Step 1: Install Python 3.12+

If you don't already have Python 3.12 or later:

**Option A — Homebrew (recommended):**
```bash
brew install python@3.12
```

**Option B — Python.org installer:**
Download from [python.org/downloads](https://www.python.org/downloads/) and run the installer.

Verify your installation:
```bash
python3 --version
# Should output: Python 3.12.x or higher
```

### Step 2: Clone the Repository

```bash
git clone <repository-url> fellow-mcp
cd fellow-mcp
```

### Step 3: Run the Bootstrap Script

The bootstrap script creates a virtual environment, installs dependencies, configures the `.env` file, and generates the wrapper script that Quick will execute.

```bash
chmod +x scripts/bootstrap-macos.sh
./scripts/bootstrap-macos.sh
```

You should see output ending with `Bootstrap Complete!` and the configuration values to use in Quick.

### Step 4: Configure Your API Credentials

Edit the `.env` file with your Fellow API credentials:

```bash
# Use your preferred editor
nano .env
# Or:
open -e .env
```

Set these two required values:

```dotenv
FELLOW_API_KEY=your-fellow-api-key-here
FELLOW_SUBDOMAIN=your-company
```

Optional settings you may also configure:

```dotenv
# Timezone (IANA format). Default: America/Los_Angeles
TZ=America/Los_Angeles

# Log verbosity: DEBUG, INFO, WARNING, ERROR, CRITICAL. Default: INFO
LOG_LEVEL=INFO
```

### Step 5: Add to AWS Quick Desktop

1. Open **AWS Quick Desktop**
2. Open **Settings** (sidebar) → **Capabilities** → **Connectors** tab
3. In the **MCP Servers** section, click **+ Create** → **MCP server**
4. Select **Local** as the connection type
5. Fill in the fields:

| Field | Value |
|-------|-------|
| **Name** | `Fellow MCP` |
| **Command** | `/full/path/to/fellow-mcp/scripts/run-stdio.sh` |
| **Arguments** | *(leave empty)* |
| **Description** | `Fellow.ai MCP server — action items, notes, recordings, and webhooks` |
| **Timeout** | `60` |

6. Add environment variables (click **+ Add variable** for each):

| Key | Value |
|-----|-------|
| `FELLOW_API_KEY` | Your Fellow API key |
| `FELLOW_SUBDOMAIN` | Your workspace subdomain (e.g., `acme` for `acme.fellow.app`) |

Optional environment variables:

| Key | Value |
|-----|-------|
| `TZ` | `America/Los_Angeles` (or your timezone) |
| `LOG_LEVEL` | `INFO` |

> **Note:** Environment variables set in the Quick UI override values in the `.env` file. You can use either location — the Quick UI is convenient for keeping credentials out of files on disk.

7. Click **Test connection** to verify the server starts and responds
8. Click **+ Add MCP** to save

### Step 6: Verify

In a Quick chat, ask something like:

> "Use the Fellow MCP to get my user info"

Quick should invoke the `get_current_user` tool and return your Fellow.ai profile information.

---

## Windows Setup

### Step 1: Install Python 3.12+

Download Python 3.12+ from [python.org/downloads](https://www.python.org/downloads/) and run the installer.

> **Important:** During installation, check the box **"Add python.exe to PATH"**. This ensures the `python` command is available system-wide.

Verify your installation by opening **PowerShell** and running:

```powershell
python --version
# Should output: Python 3.12.x or higher
```

### Step 2: Clone the Repository

Open PowerShell and navigate to where you want the project:

```powershell
git clone <repository-url> fellow-mcp
cd fellow-mcp
```

### Step 3: Run the Bootstrap Script

```powershell
.\scripts\bootstrap-windows.ps1
```

> **Note:** If you see an execution policy error, run this first:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

You should see output ending with `Bootstrap Complete!` and the configuration values to use in Quick.

### Step 4: Configure Your API Credentials

Edit the `.env` file with your Fellow API credentials:

```powershell
notepad .env
```

Set these two required values:

```dotenv
FELLOW_API_KEY=your-fellow-api-key-here
FELLOW_SUBDOMAIN=your-company
```

Optional settings you may also configure:

```dotenv
# Timezone (IANA format). Default: America/Los_Angeles
TZ=America/Los_Angeles

# Log verbosity: DEBUG, INFO, WARNING, ERROR, CRITICAL. Default: INFO
LOG_LEVEL=INFO
```

### Step 5: Add to AWS Quick Desktop

1. Open **AWS Quick Desktop**
2. Open **Settings** (sidebar) → **Capabilities** → **Connectors** tab
3. In the **MCP Servers** section, click **+ Create** → **MCP server**
4. Select **Local** as the connection type
5. Fill in the fields:

| Field | Value |
|-------|-------|
| **Name** | `Fellow MCP` |
| **Command** | `C:\full\path\to\fellow-mcp\scripts\run-stdio.bat` |
| **Arguments** | *(leave empty)* |
| **Description** | `Fellow.ai MCP server — action items, notes, recordings, and webhooks` |
| **Timeout** | `60` |

6. Add environment variables (click **+ Add variable** for each):

| Key | Value |
|-----|-------|
| `FELLOW_API_KEY` | Your Fellow API key |
| `FELLOW_SUBDOMAIN` | Your workspace subdomain (e.g., `acme` for `acme.fellow.app`) |

Optional environment variables:

| Key | Value |
|-----|-------|
| `TZ` | `America/Los_Angeles` (or your timezone) |
| `LOG_LEVEL` | `INFO` |

> **Note:** Environment variables set in the Quick UI override values in the `.env` file. You can use either location — the Quick UI is convenient for keeping credentials out of files on disk.

7. Click **Test connection** to verify the server starts and responds
8. Click **+ Add MCP** to save

### Step 6: Verify

In a Quick chat, ask something like:

> "Use the Fellow MCP to get my user info"

Quick should invoke the `get_current_user` tool and return your Fellow.ai profile information.

---

## Troubleshooting

### "Python not found" during bootstrap

Ensure Python 3.12+ is installed and on your system PATH:
- **macOS:** `python3 --version`
- **Windows:** `python --version` (from PowerShell)

If installed via Homebrew on macOS, ensure `/opt/homebrew/bin` is in your PATH.

### "FELLOW_API_KEY is required" error

The server exits immediately if credentials are missing. Ensure either:
- Your `.env` file contains `FELLOW_API_KEY` and `FELLOW_SUBDOMAIN`, or
- You've added them as environment variables in the Quick MCP configuration

### Connection test fails in Quick

1. **Check the timeout** — increase to 60 seconds if the default 30s isn't enough for the first startup (dependency imports take a moment)
2. **Check your API key** — verify it works by running the server manually:
   ```bash
   # macOS
   ./scripts/run-stdio.sh
   # Then paste this line and press Enter:
   {"jsonrpc":"2.0","id":1,"method":"initialize"}
   ```
   You should see a JSON response. Press Ctrl+C to exit.
3. **Check the wrapper script path** — ensure the full absolute path is entered in the Quick Command field with no surrounding quotes

### Server starts but tools don't work

- Verify your Fellow API key has the necessary permissions in your Fellow workspace
- Check that `FELLOW_SUBDOMAIN` matches your actual workspace (the part before `.fellow.app` in your Fellow URL)

### Windows: "running scripts is disabled on this system"

Run PowerShell as Administrator and execute:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Updating the Server

When you pull new changes from the repository:

```bash
# macOS
cd fellow-mcp
git pull
./scripts/bootstrap-macos.sh   # Re-runs cleanly, updates dependencies
```

```powershell
# Windows
cd fellow-mcp
git pull
.\scripts\bootstrap-windows.ps1   # Re-runs cleanly, updates dependencies
```

---

## Available Tools

Once connected, Quick has access to all 16 Fellow MCP tools:

| Tool | Description |
|------|-------------|
| `list_action_items` | List action items with filters (completed, archived, scope, ordering) |
| `get_action_item` | Get a single action item by ID |
| `complete_action_item` | Mark an action item as complete or incomplete |
| `archive_action_item` | Archive an action item |
| `list_notes` | List meeting notes with filters |
| `get_note` | Get a single note by ID |
| `delete_note` | Delete a note |
| `list_recordings` | List recordings with filters and include options |
| `get_recording` | Get a recording with optional transcript/AI notes/media URL |
| `delete_recording` | Delete a recording |
| `list_webhooks` | List webhooks |
| `get_webhook` | Get a single webhook by ID |
| `create_webhook` | Create a new webhook subscription |
| `update_webhook` | Update a webhook |
| `delete_webhook` | Delete a webhook |
| `get_current_user` | Get your Fellow user info and workspace details |

## Environment Variable Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `FELLOW_API_KEY` | **Yes** | — | Your Fellow.ai Developer API key |
| `FELLOW_SUBDOMAIN` | **Yes** | — | Your workspace subdomain (e.g., `acme` for `acme.fellow.app`) |
| `TZ` | No | `America/Los_Angeles` | Timezone in IANA format |
| `LOG_LEVEL` | No | `INFO` | Log verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
