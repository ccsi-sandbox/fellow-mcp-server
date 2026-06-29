# Fellow MCP Server - Windows Bootstrap Script
# Downloads dependencies and prepares the server for use with AWS Quick Desktop.
#
# Usage:
#   Open PowerShell, navigate to the project directory, and run:
#   .\scripts\bootstrap-windows.ps1
#
# After running, follow the printed instructions to configure AWS Quick.

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
$VenvDir = Join-Path $ProjectDir "venv"
$RequiredPythonVersion = "3.12"

Write-Host "=====================================" -ForegroundColor Cyan
Write-Host " Fellow MCP Server - Windows Bootstrap" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""

# --- Check for Python 3.12 ---
function Check-Python {
    $pythonCmd = $null

    # Try python3 first (Windows Store/custom installs), then python
    foreach ($cmd in @("python3", "python")) {
        try {
            $version = & $cmd --version 2>&1
            if ($version -match "Python (\d+)\.(\d+)") {
                $major = [int]$Matches[1]
                $minor = [int]$Matches[2]
                if ($major -ge 3 -and $minor -ge 12) {
                    $pythonCmd = $cmd
                    Write-Host "[OK] Found $cmd ($version)" -ForegroundColor Green
                    break
                }
            }
        } catch {
            continue
        }
    }

    if (-not $pythonCmd) {
        Write-Host "ERROR: Python ${RequiredPythonVersion}+ not found." -ForegroundColor Red
        Write-Host ""
        Write-Host "Install Python ${RequiredPythonVersion} from:" -ForegroundColor Yellow
        Write-Host "  https://www.python.org/downloads/" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "IMPORTANT: Check 'Add python.exe to PATH' during installation." -ForegroundColor Yellow
        exit 1
    }

    return $pythonCmd
}

# --- Create virtual environment ---
function Create-Venv {
    param([string]$PythonCmd)

    if (Test-Path $VenvDir) {
        Write-Host "[OK] Virtual environment already exists at $VenvDir" -ForegroundColor Green
    } else {
        Write-Host "[..] Creating virtual environment..." -ForegroundColor Yellow
        & $PythonCmd -m venv $VenvDir
        Write-Host "[OK] Virtual environment created" -ForegroundColor Green
    }
}

# --- Install dependencies ---
function Install-Deps {
    Write-Host "[..] Installing dependencies..." -ForegroundColor Yellow
    $pipExe = Join-Path $VenvDir "Scripts\pip.exe"
    & $pipExe install --quiet --upgrade pip
    & $pipExe install --quiet -r (Join-Path $ProjectDir "requirements.txt")
    Write-Host "[OK] Dependencies installed" -ForegroundColor Green
}

# --- Create .env if missing ---
function Setup-Env {
    $envFile = Join-Path $ProjectDir ".env"
    $envExample = Join-Path $ProjectDir ".env.example"

    if (-not (Test-Path $envFile)) {
        Write-Host "[..] Creating .env from .env.example..." -ForegroundColor Yellow
        Copy-Item $envExample $envFile
        Write-Host "[!!] IMPORTANT: Edit $envFile with your Fellow API credentials" -ForegroundColor Red
    } else {
        Write-Host "[OK] .env file exists" -ForegroundColor Green
    }
}

# --- Create the wrapper script ---
function Create-Wrapper {
    $wrapperPath = Join-Path $ProjectDir "scripts\run-stdio.bat"

    $wrapperContent = @"
@echo off
REM Wrapper script for running Fellow MCP Server in stdio mode.
REM Used as the Command target in AWS Quick Desktop MCP configuration.

set "PROJECT_DIR=%~dp0.."

REM Load environment variables from .env
if exist "%PROJECT_DIR%\.env" (
    for /f "usebackq tokens=1,* delims==" %%a in ("%PROJECT_DIR%\.env") do (
        set "%%a=%%b"
    )
)

REM Execute the stdio server
"%PROJECT_DIR%\venv\Scripts\python.exe" -m app --stdio
"@

    Set-Content -Path $wrapperPath -Value $wrapperContent -Encoding ASCII
    Write-Host "[OK] Wrapper script created: $wrapperPath" -ForegroundColor Green
}

# --- Run bootstrap ---
$PythonCmd = Check-Python
Create-Venv -PythonCmd $PythonCmd
Install-Deps
Setup-Env
Create-Wrapper

$WrapperPath = Join-Path $ProjectDir "scripts\run-stdio.bat"

Write-Host ""
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host " Bootstrap Complete!" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor White
Write-Host ""
Write-Host "1. Edit your .env file with your Fellow API credentials:" -ForegroundColor White
Write-Host "   $ProjectDir\.env" -ForegroundColor Yellow
Write-Host ""
Write-Host "2. In AWS Quick Desktop, add a new Local MCP server with:" -ForegroundColor White
Write-Host ""
Write-Host "   Name:      Fellow MCP" -ForegroundColor Yellow
Write-Host "   Command:   $WrapperPath" -ForegroundColor Yellow
Write-Host "   Arguments: (leave empty)" -ForegroundColor Yellow
Write-Host "   Timeout:   60" -ForegroundColor Yellow
Write-Host ""
Write-Host "   Environment variables (add these in the Quick UI):" -ForegroundColor White
Write-Host "   FELLOW_API_KEY       = <your Fellow API key>" -ForegroundColor Yellow
Write-Host "   FELLOW_SUBDOMAIN     = <your Fellow workspace subdomain>" -ForegroundColor Yellow
Write-Host ""
Write-Host "   Optional environment variables:" -ForegroundColor White
Write-Host "   TZ                   = America/Los_Angeles" -ForegroundColor Yellow
Write-Host "   LOG_LEVEL            = INFO" -ForegroundColor Yellow
Write-Host ""
Write-Host "3. Click 'Test connection' to verify, then '+ Add MCP'" -ForegroundColor White
Write-Host ""
