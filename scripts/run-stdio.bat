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
