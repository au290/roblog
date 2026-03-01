import time
import json
import os
import logging

logger = logging.getLogger('fleet_monitor')

def get_uptime_string(start_time_ms):
    if not start_time_ms: return "0d 0h 0m 0s"
    diff = int(time.time() * 1000) - start_time_ms
    days = diff // (24 * 60 * 60 * 1000)
    hours = (diff % (24 * 60 * 60 * 1000)) // (60 * 60 * 1000)
    mins = (diff % (60 * 60 * 1000)) // (60 * 1000)
    return f"{days}d {hours}h {mins}m"

def get_trend_emoji(current, previous):
    try:
        c, p = float(current), float(previous)
        if not p or p == 0 or c == p: return ""
        return " ⬆️" if c > p else " ⬇️"
    except (ValueError, TypeError):
        return ""

# Lua JSON Quirk Protections
def safe_dict(obj): return obj if isinstance(obj, dict) else {}
def safe_list(obj): return obj if isinstance(obj, list) else []

# Thread-safe JSON handlers
def load_json_safe(filepath, default_type=dict):
    if not os.path.exists(filepath): 
        return default_type()
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to read {filepath}: {e}")
        return default_type()

def save_json_safe(filepath, data):
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to save {filepath}: {e}")