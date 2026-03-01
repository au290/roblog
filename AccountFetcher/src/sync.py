import asyncio
import logging
from src import config
from src.utils import load_json_safe

# Use the global logger we will set up in run.py
logger = logging.getLogger('fleet_monitor')

async def sync_accounts(api_client):
    """
    Cross-validates fleet_data.json against Winter API and adds missing accounts.
    Uses the shared WinterAPIClient so we don't have to login twice.
    """
    # 1. Load Fleet Data safely using our utility function
    fleet_data = load_json_safe(config.FLEET_DATA_FILE, default_type=dict)
    
    if not fleet_data:
        logger.warning(f"⚠️ {config.FLEET_DATA_FILE} is empty or missing! Skipping sync cycle.")
        return

    # Extract all usernames from fleet_data
    fleet_users = set()
    ps_groups = fleet_data.get("ps_groups", {})
    for server_name, players in ps_groups.items():
        for player in players:
            username = player.get("username")
            if username:
                fleet_users.add(username)

    if not fleet_users:
        logger.warning(f"⚠️ No users found in {config.FLEET_DATA_FILE}.")
        return

    # 2. Authenticate (if the api_client hasn't already)
    if not api_client.token:
        success = await api_client.login()
        if not success:
            logger.error("❌ Login failed during sync.")
            return

    # 3. Fetch the current server list using the anchor user
    logger.info("📡 Fetching registered account list from Winter API...")
    fetch_data = await api_client.add_nickname(config.ANCHOR_USER)

    if not fetch_data or not fetch_data.get("success"):
        logger.warning(f"⚠️ API returned an error during sync: {fetch_data}")
        return

    # Convert the server's list to a set for easy comparison
    server_users = set(fetch_data.get("nicknames", []))

    # 4. Cross-Validate
    missing_users = fleet_users - server_users

    if not missing_users:
        logger.info(f"✅ All {len(fleet_users)} fleet accounts are already synced to Winter API.")
        return

    logger.info(f"🔍 Found {len(missing_users)} missing accounts. Adding them now...")

    # 5. Loop through missing users and add them
    for username in missing_users:
        try:
            add_data = await api_client.add_nickname(username)
            
            if add_data and add_data.get("success"):
                logger.info(f"➕ Successfully added: {username}")
            else:
                logger.warning(f"⚠️ Failed to add {username}: {add_data}")
                    
        except Exception as e:
            logger.error(f"❌ Network Error adding {username}: {e}")

        # 1-second delay to prevent hitting API rate limits
        await asyncio.sleep(1)