import asyncio
import logging
import aiohttp
import sys

from src import config
from src.api_client import WinterAPIClient
from src import discord_bot
from src import monitor

# --- GLOBAL LOGGING SETUP ---
def setup_logging():
    logger = logging.getLogger('fleet_monitor')
    logger.setLevel(logging.INFO)
    
    formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    
    # File Handler (saves to logs/fleet_activity.log)
    file_handler = logging.FileHandler(config.LOG_FILE, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Console Handler (prints to your terminal)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger

logger = setup_logging()

# --- MONITOR LOOP ---
async def monitor_loop(api_client):
    """Runs the monitoring/webhook update loop continuously."""
    # Give the Discord bot 15 seconds to connect and create the first fleet_data.json
    logger.info("⏳ Waiting 15 seconds for bot to initialize before starting monitor loop...")
    await asyncio.sleep(15)
    
    while True:
        try:
            await monitor.update_monitor(api_client)
        except Exception as e:
            logger.error(f"❌ Unhandled error in monitor loop: {e}")
        
        # Wait 10 minutes before checking again (600 seconds)
        await asyncio.sleep(600)

# --- MAIN RUNNER ---
async def main():
    logger.info("🚀 Starting WinterFleet Master Process...")
    
    # Global HTTP timeout to prevent hanging connections
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # Initialize our dedicated API client with the shared session
        api_client = WinterAPIClient(session)
        
        # Run both the Discord Bot and the Monitor Loop concurrently!
        await asyncio.gather(
            discord_bot.start_bot(),
            monitor_loop(api_client)
        )

if __name__ == "__main__":
    try:
        # This starts the entire application
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down gracefully...")