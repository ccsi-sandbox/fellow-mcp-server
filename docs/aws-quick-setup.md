# Fellow MCP Server — AWS Quick Desktop Setup

This guide walks through setting up the Fellow MCP Server as a **local MCP server** in the [AWS Quick](https://aws.amazon.com/quicksight/) desktop application. Quick manages the server process lifecycle — starting it when needed and stopping it when idle — so you don't need Docker or any manual process management.

## Prerequisites

- **AWS Quick Desktop** application installed and signed in
- **Fellow.ai API key** — generate one from your Fellow workspace at **Settings → Integrations → Developer API**
- **Python 3.12+** installed on your machine (the bootstrap script will verify this)

## How It Works

The Fellow MCP Server runs in **stdio transport mode** when used with AWS Quick. Instead of listening on an HTTP port, the server reads messages from standard input and writes responses to standard output. Quick launches the server process automatically and communicates with it over this channel.

This means:
- No Docker required
- No port management or firewall configuration
- No manual process management
- Authentication is handled by the local process boundary (no token needed)

---

## macOS Setup

### Step 1: Install Python 3.12+

If you don't already have Python 3.12 or later, you need to install it first.

**Option A — Homebrew (recommended if you already have Homebrew):**

Open **Terminal** (press `Cmd + Space`, type "Terminal", press Enter) and run:

```bash
brew install python@3.12
```

**Option B — Download from python.org (recommended if you don't use Homebrew):**

1. Open your browser and go to [python.org/downloads](https://www.python.org/downloads/)
2. Click the yellow **"Download Python 3.12.x"** button
3. Open the downloaded `.pkg` file from your Downloads folder
4. Follow the installer steps — click **Continue** on each screen, then **Install**
5. When prompted, enter your Mac password to allow the installation

**Verify the installation:**

Open **Terminal** (press `Cmd + Space`, type "Terminal", press Enter) and type:

```bash
python3 --version
```

You should see output like `Python 3.12.x` or higher. If you see an older version or "command not found", revisit the installation steps above.

### Step 2: Download the Project

You can get the project files using **either** Git (if you have it) or by downloading a ZIP file from your browser.

**Option A — Download as ZIP (no Git required):**

1. Open your browser and go to the project's repository page
2. Click the green **"Code"** button near the top of the page
3. Click **"Download ZIP"**
4. Open your Downloads folder and find the file (it will be named something like `fellow-mcp-main.zip`)
5. Double-click the ZIP file to extract it — macOS will create a folder like `fellow-mcp-main`
6. Drag this folder to a permanent location. A good choice is your home folder. To do this:
   - Open **Finder**
   - In the menu bar, click **Go → Home** (or press `Cmd + Shift + H`)
   - Drag the extracted `fellow-mcp-main` folder into this window
7. **Rename the folder** to `fellow-mcp` for simplicity (right-click → Rename)

**Option B — Clone with Git (if you have Git installed):**

Open **Terminal** and run:

```bash
cd ~
git clone <repository-url> fellow-mcp
```

### Step 3: Open Terminal in the Project Folder

You need to navigate your Terminal to the project folder:

1. Open **Terminal** (press `Cmd + Space`, type "Terminal", press Enter)
2. Type `cd ` (with a space after it), then drag the `fellow-mcp` folder from Finder directly into the Terminal window — this pastes the full path
3. Press **Enter**

Or, if you placed it in your home folder:

```bash
cd ~/fellow-mcp
```

> **Tip:** You can verify you're in the right place by typing `ls` and pressing Enter. You should see files like `README.md`, `requirements.txt`, and a `scripts` folder.

### Step 4: Run the Bootstrap Script

The bootstrap script automatically sets everything up: creates an isolated Python environment, installs dependencies, and generates the wrapper script that Quick will use.

In your Terminal (still in the project folder), run:

```bash
chmod +x scripts/bootstrap-macos.sh
./scripts/bootstrap-macos.sh
```

> **What does `chmod +x` do?** It makes the script file "executable" — giving your Mac permission to run it as a program. You only need to do this once.

You should see progress messages and output ending with **"Bootstrap Complete!"** along with the values you'll enter into Quick in Step 6.

If you see an error about Python not being found, go back to Step 1 and verify your Python installation.

### Step 5: Configure Your API Credentials

The bootstrap created a file called `.env` in your project folder. This file holds your Fellow API credentials. You need to edit it with your real values.

**To edit the file:**

1. In Terminal (still in the project folder), type:
   ```bash
   open -e .env
   ```
   This opens the file in TextEdit.

2. Find the line that says:
   ```
   FELLOW_API_KEY=your-fellow-api-key-here
   ```
   Replace `your-fellow-api-key-here` with your actual Fellow API key.

3. Find the line that says:
   ```
   FELLOW_SUBDOMAIN=your-company
   ```
   Replace `your-company` with your Fellow workspace subdomain. This is the part before `.fellow.app` in your Fellow URL. For example, if you access Fellow at `acme.fellow.app`, your subdomain is `acme`.

4. Save the file (`Cmd + S`) and close TextEdit.

> **Where do I find my Fellow API key?** Log in to Fellow.ai, click your profile icon → **Settings** → **Integrations** → **Developer API** → **Generate API Key**.

Optional settings (you can leave these at their defaults):

| Setting | Default | What it does |
|---------|---------|--------------|
| `TZ` | `America/Los_Angeles` | Your timezone. Change to your [IANA timezone](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) if needed (e.g., `America/New_York`, `Europe/London`). |
| `LOG_LEVEL` | `INFO` | How much detail to log. Leave as `INFO` unless troubleshooting. |

### Step 6: Add to AWS Quick Desktop

Now you'll tell AWS Quick how to find and run the Fellow MCP Server.

1. Open **AWS Quick Desktop**
2. Click **Settings** in the sidebar
3. Click **Capabilities**
4. Click the **Connectors** tab
5. In the **MCP Servers** section, click **+ Create** → **MCP server**
6. Select **Local** as the connection type

7. Fill in the fields:

| Field | What to enter |
|-------|---------------|
| **Name** | `Fellow MCP` |
| **Command** | The full path to the wrapper script (see below) |
| **Arguments** | *(leave this empty)* |
| **Description** | `Fellow.ai MCP server — action items, notes, recordings, and webhooks` |
| **Timeout** | `60` |

**Finding the full path for the Command field:**

The path you need depends on where you put the project. If you followed the instructions and placed it in your home folder, it will be:

```
/Users/YOUR_USERNAME/fellow-mcp/scripts/run-stdio.sh
```

Replace `YOUR_USERNAME` with your Mac username. Not sure what it is? Run this in Terminal:
```bash
echo $HOME/fellow-mcp/scripts/run-stdio.sh
```
This prints the exact path — copy and paste it into the Command field.

8. Add environment variables by clicking **+ Add variable** for each:

| Key | Value |
|-----|-------|
| `FELLOW_API_KEY` | Your Fellow API key (same one from Step 5) |
| `FELLOW_SUBDOMAIN` | Your workspace subdomain (e.g., `acme`) |

Optional environment variables (click **+ Add variable** if you want to set these):

| Key | Value |
|-----|-------|
| `TZ` | Your timezone (e.g., `America/New_York`) |
| `LOG_LEVEL` | `INFO` |

> **Note:** Environment variables set in the Quick UI take priority over values in the `.env` file. You can configure your credentials in either place. The Quick UI is convenient because it keeps credentials within the Quick app rather than in a file on disk.

9. Click **Test connection** — you should see a success indicator
10. Click **+ Add MCP** to save

### Step 7: Verify

In a Quick chat, try asking:

> "Use the Fellow MCP to get my user info"

Quick should invoke the `get_current_user` tool and return your Fellow.ai profile information (name, email, workspace details).

---

## Windows Setup

### Step 1: Install Python 3.12+

1. Open your browser and go to [python.org/downloads](https://www.python.org/downloads/)
2. Click the yellow **"Download Python 3.12.x"** button
3. Open the downloaded `.exe` file from your Downloads folder
4. **Important:** On the first installer screen, check the box that says **"Add python.exe to PATH"** at the bottom — this is critical
5. Click **"Install Now"**
6. Wait for the installation to complete, then click **Close**

**Verify the installation:**

Open **PowerShell** (press the `Windows` key, type "PowerShell", click **Windows PowerShell**) and type:

```powershell
python --version
```

You should see output like `Python 3.12.x` or higher.

> **Troubleshooting:** If you see "'python' is not recognized as an internal or external command", you likely missed the "Add python.exe to PATH" checkbox. Uninstall Python (Settings → Apps → Python → Uninstall) and reinstall, making sure to check that box.

### Step 2: Download the Project

You can get the project files using **either** Git (if you have it) or by downloading a ZIP file from your browser.

**Option A — Download as ZIP (no Git required):**

1. Open your browser and go to the project's repository page
2. Click the green **"Code"** button near the top of the page
3. Click **"Download ZIP"**
4. Open your Downloads folder and find the file (it will be named something like `fellow-mcp-main.zip`)
5. Right-click the ZIP file and select **"Extract All..."**
6. Choose a permanent location to extract to. A good choice is your user folder:
   - Click **Browse**, then navigate to `C:\Users\YOUR_USERNAME`
   - Click **Select Folder**, then click **Extract**
7. This creates a folder like `fellow-mcp-main`. **Rename it** to `fellow-mcp` (right-click → Rename).

Your project should now be at a path like `C:\Users\YOUR_USERNAME\fellow-mcp`.

**Option B — Clone with Git (if you have Git installed):**

Open **PowerShell** and run:

```powershell
cd $HOME
git clone <repository-url> fellow-mcp
```

### Step 3: Open PowerShell in the Project Folder

1. Open **File Explorer** and navigate to the `fellow-mcp` folder
2. Click in the **address bar** at the top of the File Explorer window (where it shows the path)
3. Type `powershell` and press **Enter** — this opens a PowerShell window already pointed at the correct folder

Alternatively, open PowerShell manually and navigate:

```powershell
cd C:\Users\YOUR_USERNAME\fellow-mcp
```

Replace `YOUR_USERNAME` with your Windows username.

> **Tip:** You can verify you're in the right place by typing `dir` and pressing Enter. You should see files like `README.md`, `requirements.txt`, and a `scripts` folder.

### Step 4: Run the Bootstrap Script

The bootstrap script automatically sets everything up: creates an isolated Python environment, installs dependencies, and generates the wrapper script that Quick will use.

In your PowerShell window (still in the project folder), run:

```powershell
.\scripts\bootstrap-windows.ps1
```

> **If you see an error about "running scripts is disabled":**
>
> Windows blocks script execution by default for security. To allow it for your user account, run this command first, then try again:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```
> When prompted, type `Y` and press Enter.

You should see progress messages and output ending with **"Bootstrap Complete!"** along with the values you'll enter into Quick in Step 6.

### Step 5: Configure Your API Credentials

The bootstrap created a file called `.env` in your project folder. This file holds your Fellow API credentials. You need to edit it with your real values.

**To edit the file:**

1. In PowerShell (still in the project folder), type:
   ```powershell
   notepad .env
   ```
   This opens the file in Notepad.

2. Find the line that says:
   ```
   FELLOW_API_KEY=your-fellow-api-key-here
   ```
   Replace `your-fellow-api-key-here` with your actual Fellow API key.

3. Find the line that says:
   ```
   FELLOW_SUBDOMAIN=your-company
   ```
   Replace `your-company` with your Fellow workspace subdomain. This is the part before `.fellow.app` in your Fellow URL. For example, if you access Fellow at `acme.fellow.app`, your subdomain is `acme`.

4. Save the file (`Ctrl + S`) and close Notepad.

> **Where do I find my Fellow API key?** Log in to Fellow.ai, click your profile icon → **Settings** → **Integrations** → **Developer API** → **Generate API Key**.

Optional settings (you can leave these at their defaults):

| Setting | Default | What it does |
|---------|---------|--------------|
| `TZ` | `America/Los_Angeles` | Your timezone. Change to your [IANA timezone](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) if needed (e.g., `America/New_York`, `Europe/London`). |
| `LOG_LEVEL` | `INFO` | How much detail to log. Leave as `INFO` unless troubleshooting. |

### Step 6: Add to AWS Quick Desktop

Now you'll tell AWS Quick how to find and run the Fellow MCP Server.

1. Open **AWS Quick Desktop**
2. Click **Settings** in the sidebar
3. Click **Capabilities**
4. Click the **Connectors** tab
5. In the **MCP Servers** section, click **+ Create** → **MCP server**
6. Select **Local** as the connection type

7. Fill in the fields:

| Field | What to enter |
|-------|---------------|
| **Name** | `Fellow MCP` |
| **Command** | The full path to the wrapper script (see below) |
| **Arguments** | *(leave this empty)* |
| **Description** | `Fellow.ai MCP server — action items, notes, recordings, and webhooks` |
| **Timeout** | `60` |

**Finding the full path for the Command field:**

The path you need depends on where you put the project. If you followed the instructions and placed it in your user folder, it will be:

```
C:\Users\YOUR_USERNAME\fellow-mcp\scripts\run-stdio.bat
```

Replace `YOUR_USERNAME` with your Windows username. Not sure what it is? Run this in PowerShell:
```powershell
echo "$HOME\fellow-mcp\scripts\run-stdio.bat"
```
This prints the exact path — copy and paste it into the Command field.

> **Alternative way to get the path:** In File Explorer, navigate to `fellow-mcp\scripts`, find `run-stdio.bat`, hold `Shift` and right-click it, then select **"Copy as path"**. Paste this into the Command field and remove the surrounding quotes if present.

8. Add environment variables by clicking **+ Add variable** for each:

| Key | Value |
|-----|-------|
| `FELLOW_API_KEY` | Your Fellow API key (same one from Step 5) |
| `FELLOW_SUBDOMAIN` | Your workspace subdomain (e.g., `acme`) |

Optional environment variables (click **+ Add variable** if you want to set these):

| Key | Value |
|-----|-------|
| `TZ` | Your timezone (e.g., `America/New_York`) |
| `LOG_LEVEL` | `INFO` |

> **Note:** Environment variables set in the Quick UI take priority over values in the `.env` file. You can configure your credentials in either place. The Quick UI is convenient because it keeps credentials within the Quick app rather than in a file on disk.

9. Click **Test connection** — you should see a success indicator
10. Click **+ Add MCP** to save

### Step 7: Verify

In a Quick chat, try asking:

> "Use the Fellow MCP to get my user info"

Quick should invoke the `get_current_user` tool and return your Fellow.ai profile information (name, email, workspace details).

---

## Troubleshooting

### "Python not found" during bootstrap

**macOS:**
- Open Terminal and run `python3 --version`. If it says "command not found", Python isn't installed or isn't on your PATH.
- If you installed via Homebrew, try running `brew link python@3.12` then try again.
- If you installed from python.org, try closing and re-opening Terminal.

**Windows:**
- Open PowerShell and run `python --version`. If it says "'python' is not recognized", Python isn't on your PATH.
- The most common fix: uninstall Python, then reinstall it and make sure to check **"Add python.exe to PATH"** on the first installer screen.
- After reinstalling, close and re-open PowerShell before trying again.

### "FELLOW_API_KEY is required" error

The server exits immediately if credentials are missing. Ensure either:
- Your `.env` file contains valid values for `FELLOW_API_KEY` and `FELLOW_SUBDOMAIN` (not the placeholder text), or
- You've added them as environment variables in the Quick MCP configuration

### Connection test fails in Quick

1. **Check the timeout** — increase to 60 seconds if the default 30s isn't enough for the first startup (Python needs a moment to load on first run)
2. **Check the Command path** — make sure the full absolute path to `run-stdio.sh` (macOS) or `run-stdio.bat` (Windows) is entered with no surrounding quotes
3. **Check your API key** — verify it works by testing manually:

   **macOS:**
   ```bash
   cd ~/fellow-mcp
   ./scripts/run-stdio.sh
   ```
   Then paste this line and press Enter:
   ```
   {"jsonrpc":"2.0","id":1,"method":"initialize"}
   ```
   You should see a JSON response starting with `{"jsonrpc":"2.0","id":1,"result":...}`. Press `Ctrl+C` to exit.

   **Windows:**
   ```powershell
   cd $HOME\fellow-mcp
   .\scripts\run-stdio.bat
   ```
   Then paste this line and press Enter:
   ```
   {"jsonrpc":"2.0","id":1,"method":"initialize"}
   ```
   You should see a JSON response. Press `Ctrl+C` to exit.

4. **If the manual test also fails**, check the error message. Common issues:
   - "FELLOW_API_KEY is required" → your `.env` file is missing credentials
   - "No module named 'app'" → your Terminal/PowerShell isn't pointed at the project folder
   - "No such file or directory" → the wrapper script path is wrong

### Server starts but tools don't work

- Verify your Fellow API key has the necessary permissions in your Fellow workspace
- Check that `FELLOW_SUBDOMAIN` matches your actual workspace (the part before `.fellow.app` in your Fellow URL)
- If you recently generated a new API key, the old one may be revoked — update your `.env` or Quick environment variables

### Windows: "running scripts is disabled on this system"

This is a Windows security feature. To allow running the bootstrap script for your user account:

1. Open PowerShell
2. Run:
   ```powershell
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
   ```
3. Type `Y` and press Enter when prompted
4. Try the bootstrap script again

### File doesn't open or can't find `.env`

Files starting with a dot (`.env`) are hidden by default on both macOS and Windows.

**macOS:** In Finder, press `Cmd + Shift + .` to toggle hidden files visible.

**Windows:** In File Explorer, click **View** in the toolbar, then check **Hidden items**.

Alternatively, use the command-line editors shown in Step 5 (`open -e .env` on macOS, `notepad .env` on Windows), which work regardless of file visibility settings.

### Updating the Server

When a new version of the server is available:

**If you downloaded as ZIP originally:**
1. Download the new ZIP from the repository
2. Extract it to a temporary location
3. Copy the contents over your existing `fellow-mcp` folder (overwrite when prompted)
4. Re-run the bootstrap script to update dependencies:
   - macOS: `./scripts/bootstrap-macos.sh`
   - Windows: `.\scripts\bootstrap-windows.ps1`

**If you used Git:**
```bash
# macOS
cd ~/fellow-mcp
git pull
./scripts/bootstrap-macos.sh
```

```powershell
# Windows
cd $HOME\fellow-mcp
git pull
.\scripts\bootstrap-windows.ps1
```

Your `.env` file and Quick configuration are preserved during updates.

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
