import asyncio
from src import config

class WinterAPIClient:
    def __init__(self, session):
        self.session = session
        self.token = None
        self.headers = {}

    async def login(self):
        url = f"{config.WINTER_API_URL}/auth/login"
        payload = {"username": config.WINTER_USERNAME, "password": config.WINTER_PASSWORD}
        
        async with self.session.post(url, json=payload) as res:
            if res.status != 200:
                return False
            data = await res.json()
            self.token = data.get("token")
            if self.token:
                self.headers = {'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json'}
                return True
            return False

    async def fetch_profiles_batch(self, nicknames):
        url = f"{config.WINTER_API_URL}/player-data/batch"
        async with self.session.post(url, headers=self.headers, json={"nicknames": nicknames}) as res:
            data = await res.json()
            return data.get("data", {})

    async def fetch_endpoint(self, endpoint):
        url = f"{config.WINTER_API_URL}{endpoint}"
        async with self.session.get(url, headers=self.headers) as res:
            return await res.json()

    async def add_nickname(self, nickname):
        url = f"{config.WINTER_API_URL}/user/nicknames"
        payload = {"action": "add", "nickname": nickname, "game": "fishIt"}
        async with self.session.post(url, headers=self.headers, json=payload) as res:
            return await res.json()