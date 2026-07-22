import sys
import logging
import asyncio

try:
    from dotenv import load_dotenv
    load_dotenv()
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
