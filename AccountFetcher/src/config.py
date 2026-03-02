import os
from dotenv import load_dotenv

# Load variables from the .env file in the root directory
load_dotenv()

# --- DIRECTORY SETUP ---
# This dynamically finds the root 'roblog' folder
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, 'data')
LOG_DIR = os.path.join(ROOT_DIR, 'logs')

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# --- FILE PATHS ---
FLEET_DATA_FILE = os.path.join(DATA_DIR, 'fleet_data.json')
DATABASE_FILE = os.path.join(DATA_DIR, 'database.json')
REGISTRY_FILE = os.path.join(DATA_DIR, 'ps_registry.json')
MSG_ID_FILE = os.path.join(DATA_DIR, 'msg_ids.txt')
LOG_FILE = os.path.join(LOG_DIR, 'fleet_activity.log')

# --- DISCORD SETTINGS ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID', 0))
STATUS_WEBHOOK_URL = os.getenv('STATUS_WEBHOOK_URL')
MONITOR_WEBHOOK_URL = os.getenv('MONITOR_WEBHOOK_URL')  # Add this to your .env!
AUTH_USERS = [int(uid.strip()) for uid in os.getenv('AUTHORIZED_USERS', '').split(',') if uid.strip()]

# --- WINTERCODE API SETTINGS ---
WINTER_USERNAME = os.getenv('WINTER_USERNAME')
WINTER_PASSWORD = os.getenv('WINTER_PASSWORD')
WINTER_API_URL = os.getenv('WINTER_API_URL', 'https://apiweb.wintercode.dev/api')
ANCHOR_USER = os.getenv('ANCHOR_USER', 'UdinXAsetot_1')

# --- GAME SETTINGS ---
TARGET_ITEMS = [
    "Evolved Enchant Stone", "Giant Squid", "Great Whale",
    "Queen Crab", "Panther Eel", "King Crab",
    "Depthseeker Ray", "Cryoshade Glider"
]

WEB_USERNAME = os.getenv('WEB_USERNAME', 'admin')
WEB_PASSWORD = os.getenv('WEB_PASSWORD', 'admin')