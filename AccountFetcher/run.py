import asyncio
import logging
import aiohttp
import sys

from src import config
from src import state
from src.api_client import WinterAPIClient
from src import discord_bot
from src import monitor

import uvicorn
from src.web import app

def setup_logging():
    logger = logging.getLogger('fleet_monitor')
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    
    file_handler = logging.FileHandler(config.LOG_FILE, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    return logger

logger = setup_logging()

# --- THE WEB SERVER LOOP ---
async def start_web_server():
    """Runs the FastAPI web interface cooperatively with the Discord bot."""
    logger.info("🌐 Starting Web Server on http://127.0.0.1:8000")
    # Changed variable name to 'uv_config' so it doesn't conflict with your 'src.config'
    uv_config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="warning")
    server = uvicorn.Server(uv_config)
    await server.serve()

# --- THE MONITOR LOOP ---
async def monitor_loop(api_client):
    logger.info("⏳ Waiting 15 seconds for bot to initialize before starting monitor loop...")
    await asyncio.sleep(15)
    while True:
        try:
            await monitor.update_monitor(api_client)
        except Exception as e:
            logger.error(f"❌ Unhandled error in monitor loop: {e}")
        await asyncio.sleep(600)

# --- THE BACKUP LOOP ---
async def auto_backup_loop():
    """Saves the RAM state to disk every 5 minutes."""
    while True:
        await asyncio.sleep(300) 
        async with state.state_lock:
            state.save_state_to_disk()

# --- MAIN MASTER PROCESS ---
async def main():
    logger.info("🚀 Starting WinterFleet Master Process...")
    
    # Load historical data into RAM before anything else starts
    state.load_state_from_disk()
    
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        api_client = WinterAPIClient(session)
        
        # Now running FOUR loops perfectly in sync!
        await asyncio.gather(
            discord_bot.start_bot(),
            monitor_loop(api_client),
            auto_backup_loop(),
            start_web_server()  # Web server is now safely locked in!
        )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down gracefully...")
        # Emergency backup on shutdown
        state.save_state_to_disk()