import asyncio
import logging
from src import config

logger = logging.getLogger('fleet_monitor')

class WinterAPIClient:
    def __init__(self, session):
        self.session = session
        self.token = None
        self.headers = {}

    async def login(self):
        """Fetches a fresh token and updates headers."""
        url = f"{config.WINTER_API_URL}/auth/login"
        payload = {"username": config.WINTER_USERNAME, "password": config.WINTER_PASSWORD}
        
        try:
            async with self.session.post(url, json=payload) as res:
                if res.status != 200:
                    logger.error(f"❌ Login failed with status {res.status}")
                    return False
                data = await res.json()
                self.token = data.get("token")
                if self.token:
                    self.headers = {
                        'Authorization': f'Bearer {self.token}', 
                        'Content-Type': 'application/json'
                    }
                    logger.info("✅ API Token refreshed successfully.")
                    return True
                return False
        except Exception as e:
            logger.error(f"❌ Connection error during login: {e}")
            return False

    async def fetch_profiles_batch(self, nicknames):
        url = f"{config.WINTER_API_URL}/player-data/batch"
        
        # Ensure we have a token before starting
        if not self.token: await self.login()

        async with self.session.post(url, headers=self.headers, json={"nicknames": nicknames}) as res:
            data = await res.json()
            
            # --- THE FIX: Check for expiration and retry ---
            if data.get("error") == "Token expired" or "refresh your token" in str(data.get("message")):
                logger.warning("⚠️ Token expired! Refreshing and retrying batch fetch...")
                if await self.login():
                    async with self.session.post(url, headers=self.headers, json={"nicknames": nicknames}) as retry_res:
                        data = await retry_res.json()
            
            return data.get("data", {})

    async def fetch_endpoint(self, endpoint):
        url = f"{config.WINTER_API_URL}{endpoint}"
        
        if not self.token: await self.login()

        async with self.session.get(url, headers=self.headers) as res:
            data = await res.json()
            
            # --- THE FIX: Check for expiration and retry ---
            if data.get("error") == "Token expired" or "refresh your token" in str(data.get("message")):
                logger.warning(f"⚠️ Token expired! Refreshing for endpoint: {endpoint}")
                if await self.login():
                    async with self.session.get(url, headers=self.headers) as retry_res:
                        data = await retry_res.json()
            
            return data

    async def add_nickname(self, nickname):
        url = f"{config.WINTER_API_URL}/user/nicknames"
        payload = {"action": "add", "nickname": nickname, "game": "fishIt"}
        
        if not self.token: await self.login()

        async with self.session.post(url, headers=self.headers, json=payload) as res:
            data = await res.json()
            
            if data.get("error") == "Token expired":
                if await self.login():
                    async with self.session.post(url, headers=self.headers, json=payload) as retry_res:
                        data = await retry_res.json()
            
            return data