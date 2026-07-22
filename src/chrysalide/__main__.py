import sys
import logging
import asyncio

try:
    from dotenv import load_dotenv
    from pathlib import Path as _Path
    # Look for .env next to the package root, so the server works no matter
    # which cwd Claude Code / another MCP client launches it from.
    _pkg_env = _Path(__file__).resolve().parent.parent.parent / ".env"
    if _pkg_env.exists():
        load_dotenv(_pkg_env, override=False)
    else:
        load_dotenv(override=False)  # fall back to cwd
except ImportError:
    pass

from chrysalide.server import main as server_main

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr  # Important for MCP stdio server to log to stderr
)
logger = logging.getLogger(__name__)

def main():
    logger.info("Chrysalide MCP server starting...")
    asyncio.run(server_main())

if __name__ == "__main__":
    main()
