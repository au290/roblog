import json
import asyncio
import os
import logging

logger = logging.getLogger('fleet_monitor')

# The Master Lock to prevent RAM corruption when reading/writing at the same time
state_lock = asyncio.Lock()

# The Master RAM Dictionary
fleet_state = {
    "metadata": {},
    "global_stats": {},
    "ps_groups": {},
    "system_health": {},
    "history": []  # Ensures the graph array exists even on the very first boot
}

CACHE_FILE = "fleet_cache.json"

def save_state_to_disk():
    """Dumps the entire RAM state (including graph history) to a JSON file."""
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            # indent=4 makes the JSON file human-readable if you ever want to open it
            json.dump(fleet_state, f, indent=4)
    except Exception as e:
        logger.error(f"❌ Failed to save state to cache: {e}")

def load_state_from_disk():
    """Loads the previous state from the JSON file on startup."""
    global fleet_state
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)
                
                # Merge the cached data into our live RAM
                fleet_state.update(cached_data)
                
                # Double-check that history survived
                if "history" not in fleet_state:
                    fleet_state["history"] = []
                    
            logger.info(f"💾 Cache Restored! Loaded {len(fleet_state['history'])} historical graph points.")
        except Exception as e:
            logger.error(f"❌ Failed to load cache from disk: {e}")