"""Package entry point supporting both HTTP and stdio transport modes.

Usage:
    python3 -m app --stdio    # Run in stdio mode (for MCP clients like AWS Quick)
    python3 -m app            # Run in HTTP mode (default, Flask dev server)
"""

import sys


def main() -> None:
    """Dispatch to the appropriate transport based on CLI arguments."""
    if "--stdio" in sys.argv:
        from app.stdio import run_stdio
        run_stdio()
    else:
        from app.main import create_app
        app = create_app()
        app.run(host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
