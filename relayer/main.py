import asyncio
import logging
import os
from aiohttp import web
from pathlib import Path

from .config import setup_logging, PROJECT_ROOT
from .database import setup_database
from .blockchain import client
from .endpoints import setup_routes
from .polling import poll_transfers

logger = logging.getLogger(__name__)

# Get the relayer directory path
RELAYER_DIR = Path(__file__).parent.absolute()

async def init_app() -> web.Application:
    """Initialize the web application."""
    logger.info("Initializing web application")
    app = web.Application()
    setup_routes(app)
    logger.info("Web application routes configured")
    return app

async def main() -> None:
    """Main application entry point."""
    logger.info("Starting application")
    
    # Change to base58bruteforce directory and build binary
    logger.info("Building base58bruteforce binary")
    original_dir = os.getcwd()
    os.chdir(RELAYER_DIR / "base58bruteforce")
    os.system("cargo build --release")
    os.chdir(original_dir)
    os.system(f"cp {RELAYER_DIR}/base58bruteforce/target/release/base58bruteforce {RELAYER_DIR}/binary")
    
    # Initialize database
    await setup_database()
    
    # Set up blockchain contracts
    await client.setup_contracts()
    
    # Initialize and start web application
    app = await init_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8454)
    await site.start()
    logger.info("Server started at http://0.0.0.0:8454")
    
    # Start transfer polling task
    logger.info("Starting transfer polling task")
    asyncio.create_task(poll_transfers())
    
    # Keep the application running
    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    try:
        logger.info("Starting application main loop")
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")