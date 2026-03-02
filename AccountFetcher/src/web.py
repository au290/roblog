import os
import copy
import secrets
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from src import state
from src import config

# Initialize FastAPI
app = FastAPI(title="WinterFleet Command Center")
security = HTTPBasic()

# Setup Jinja2 Templates
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """Checks if the user typed the correct username and password."""
    is_correct_username = secrets.compare_digest(credentials.username, config.WEB_USERNAME)
    is_correct_password = secrets.compare_digest(credentials.password, config.WEB_PASSWORD)
    
    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# --- SECURED ROUTES ---
# Notice we added `username: str = Depends(verify_credentials)`
# If they fail the check, FastAPI stops them here and never loads the HTML or Data.

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard(request: Request, username: str = Depends(verify_credentials)):
    """Serves the main HTML webpage (Requires Password)."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/state")
async def get_live_state(username: str = Depends(verify_credentials)):
    """Returns the live in-memory state (Requires Password)."""
    async with state.state_lock:
        return copy.deepcopy(state.fleet_state)