import discord
from discord.ext import commands, tasks
import re
import time
import logging
import aiohttp
import asyncio
from datetime import datetime
from src import config
from src import utils

logger = logging.getLogger('fleet_monitor')

# --- GLOBALS & STATE ---
START_TIME = None
LAST_FETCH_TIME = 0 
FETCH_COUNT = 0
fetch_lock = asyncio.Lock()
webhook_session = None

# --- BOT SETUP ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# --- AUTHORIZATION DECORATOR ---
def is_authorized():
    async def predicate(ctx):
        if ctx.author.id not in config.AUTH_USERS:
            await ctx.send("🚫 **Access Denied:** You are not authorized to run this command.")
            logger.warning(f"🔒 Unauthorized access attempt by {ctx.author} ({ctx.author.id})")
            return False
        return True
    return commands.check(predicate)

# --- REGISTRY HELPERS ---
def get_registry():
    return utils.load_json_safe(config.REGISTRY_FILE, default_type=dict)

def save_registry(registry):
    utils.save_json_safe(config.REGISTRY_FILE, registry)

# --- CORE LOGIC ---
async def update_status_webhook():
    """Send or patch the heartbeat/status embed via webhook."""
    global webhook_session
    if webhook_session is None or webhook_session.closed:
        webhook_session = aiohttp.ClientSession()

    webhook = discord.Webhook.from_url(config.STATUS_WEBHOOK_URL, session=webhook_session)
    embed = discord.Embed(title="🤖 Bot Heartbeat Status", color=0x1abc9c)
    
    current_uptime = utils.get_uptime_string(START_TIME * 1000 if START_TIME else None)
    fetch_ts = f"<t:{int(LAST_FETCH_TIME)}:R>" if LAST_FETCH_TIME > 0 else "Never"
    
    embed.add_field(name="⏱️ Uptime", value=f"`{current_uptime}`", inline=True)
    embed.add_field(name="📡 Last Fetch", value=fetch_ts, inline=True)
    
    async with fetch_lock:
        embed.add_field(name="📥 Total Fetches", value=f"`{FETCH_COUNT}` messages", inline=True)
    
    embed.add_field(name="💾 Registry Size", value=f"`{len(get_registry())}` Private Servers", inline=True)
    embed.set_footer(text=f"Last Update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Read the last message ID (Wait, we'll store this in a simple txt file like before, or a single key json)
    msg_id = None
    try:
        with open(config.MSG_ID_FILE, 'r') as f:
            content = f.read().strip()
            if content: msg_id = int(content)
    except FileNotFoundError:
        pass

    try:
        if msg_id:
            await webhook.edit_message(msg_id, embed=embed)
            logger.info("📡 Status Webhook: Patched existing message.")
        else:
            sent_msg = await webhook.send(embed=embed, username="Fleet Watchdog", wait=True)
            with open(config.MSG_ID_FILE, 'w') as f: 
                f.write(str(sent_msg.id))
            logger.info("📡 Status Webhook: Sent new initial message.")
    except Exception as e:
        logger.error(f"Failed to update status webhook: {e}")
        import os
        if os.path.exists(config.MSG_ID_FILE): os.remove(config.MSG_ID_FILE)

async def perform_sync():
    """Fetch registered messages, parse contents, and build fleet_state."""
    global FETCH_COUNT, LAST_FETCH_TIME
    registry = get_registry()
    channel = bot.get_channel(config.CHANNEL_ID)
    
    if not channel:
        logger.error(f"Could not find channel with ID {config.CHANNEL_ID}")
        return None

    fleet_state = {
        "metadata": {
            "last_sync_iso": datetime.now().isoformat(),
            "last_sync_unix": int(time.time()),
            "total_online_count": 0,
            "total_ps_registered": len(registry),
            "bot_uptime": utils.get_uptime_string(START_TIME * 1000 if START_TIME else None)
        },
        "ps_groups": {},
        "system_health": {}
    }
    
    for msg_id, ps_name in registry.items():
        try:
            msg = await channel.fetch_message(int(msg_id))
            
            async with fetch_lock: 
                FETCH_COUNT += 1
                LAST_FETCH_TIME = time.time()

            content = msg.content
            for e in msg.embeds:
                if e.description: content += "\n" + e.description
                for f in e.fields: content += f"\n{f.value}"

            ts_match = re.search(r"<t:(\d+):[RAfdtT]>", content)
            last_msg_ts = int(ts_match.group(1)) if ts_match else 0
            is_stale = (time.time() - last_msg_ts) > 1800 if last_msg_ts > 0 else True

            sys_cpu = re.search(r"CPU:\s+([\d.]+%?)", content)
            sys_mem = re.search(r"Memory:\s+([\d./\sA-Z]+GB\s+\([\d.]+%?\s+used\))", content)

            fleet_state["system_health"][ps_name] = {
                "cpu_usage": sys_cpu.group(1) if sys_cpu else "0%",
                "memory_details": sys_mem.group(1) if sys_mem else "N/A",
                "last_reported_unix": last_msg_ts,
                "is_data_stale": is_stale
            }

            pattern = (
                r"🆔\s+(?:`|\|\|)(\d+)(?:`|\|\|)\n"
                r"👤\s+(?:`|\|\|)([\w_]+)(?:`|\|\|)\n"
                r"📊\s+`([\d.]+%?)`\n"
                r"💾\s+`([\d.]+\s+MB)`\n"
                r"(?:⏱\s+`([^`]+)`\n)?"
                r"(IN-GAME|LOBBY|DISCONNECTED|CLOSED)"
            )
            
            players_found = re.findall(pattern, content, re.MULTILINE)
            fleet_state["ps_groups"][ps_name] = []

            for p in players_found:
                raw_status = p[5]
                is_online = (raw_status == "IN-GAME" and not is_stale)
                if is_online:
                    fleet_state["metadata"]["total_online_count"] += 1

                fleet_state["ps_groups"][ps_name].append({
                    "player_id": p[0], "username": p[1],
                    "api_status": "ONLINE" if is_online else "OFFLINE",
                    "raw_status": raw_status, "is_active": is_online, 
                    "load_cpu": p[2], "load_ram": p[3],
                    "session_uptime": p[4] if p[4] else "00:00:00"
                })

        except Exception as e:
            logger.error(f"Error syncing {ps_name}: {e}")

    # Safely save the scraped data
    utils.save_json_safe(config.FLEET_DATA_FILE, fleet_state)
    return fleet_state

def create_discord_embed(fleet_state):
    embed = discord.Embed(title="❄️ Winter Fleet Live Monitor", color=0x3498db)
    embed.description = f"**Global Status:** {fleet_state['metadata']['total_online_count']} Bots Active"
    for ps_name, players in fleet_state["ps_groups"].items():
        health = fleet_state["system_health"].get(ps_name, {})
        ts_str = f"<t:{health['last_reported_unix']}:R>" if health.get('last_reported_unix') else "N/A"
        p_list = [f"{'🟢' if p['is_active'] else '🔴'} `{p['username']}` | **{p['api_status']}**" for p in players]
        val = f"**Update:** {ts_str}\n**CPU:** `{health.get('cpu_usage')}`\n" + "\n".join(p_list)
        embed.add_field(name=f"🖥️ {ps_name}", value=val or "🔴 No Active Bots", inline=False)
    return embed

# --- LOOPS & EVENTS ---
@tasks.loop(minutes=5)
async def heartbeat_loop():
    await perform_sync()
    await update_status_webhook()

@bot.event
async def on_ready():
    global START_TIME
    if START_TIME is None:
        START_TIME = time.time()
        
    logger.info(f"✅ Bot connected as {bot.user}")
    await perform_sync()
    await update_status_webhook()
    if not heartbeat_loop.is_running(): 
        heartbeat_loop.start()

# --- COMMANDS ---
@bot.command()
@is_authorized()
async def listcommand(ctx):
    embed = discord.Embed(title="📜 Authorized Fleet Commands", color=0x2ecc71)
    cmds = [("`!addps [id] [name]`","Reg new PS"), ("`!listps`","List all"), ("`!remove [name]`","Delete PS"), ("`!rename [o] [n]`","Rename PS"), ("`!dashboard`","View Status"), ("`!force_sync`","Sync JSON/Webh"), ("`!logs`","View Logs")]
    for c, d in cmds: embed.add_field(name=c, value=d, inline=False)
    await ctx.send(embed=embed)

@bot.command()
@is_authorized()
async def dashboard(ctx):
    data = utils.load_json_safe(config.FLEET_DATA_FILE)
    if not data: 
        return await ctx.send("🔄 Syncing... Please wait a moment.")
    await ctx.send(embed=create_discord_embed(data))

@bot.command()
@is_authorized()
async def addps(ctx, message_id: str, *, ps_name: str):
    reg = get_registry()
    reg[message_id] = ps_name
    save_registry(reg)
    await ctx.send(f"✅ Added {ps_name}. Syncing...")
    await perform_sync()
    await update_status_webhook()

@bot.command()
@is_authorized()
async def force_sync(ctx):
    msg = await ctx.send("⚡ **Force Syncing...**")
    if await perform_sync():
        await update_status_webhook()
        await msg.edit(content="✅ **Sync & Webhook Updated!**")

@bot.command()
@is_authorized()
async def logs(ctx, lines: int = 10):
    try:
        with open(config.LOG_FILE, 'r', encoding='utf-8') as f:
            content = "".join(f.readlines()[-lines:])
        await ctx.send(f"```text\n{content[-1900:]}```")
    except Exception:
        await ctx.send("❌ Could not read log file.")

@bot.command()
@is_authorized()
async def remove(ctx, ps_name: str):
    registry = get_registry()
    target_id = next((k for k, v in registry.items() if v.lower() == ps_name.lower()), None)
    if target_id:
        del registry[target_id]
        save_registry(registry)
        await ctx.send(f"🗑️ Removed **{ps_name}**. Refreshing data...")
        await perform_sync()
        await update_status_webhook()
    else:
        await ctx.send(f"❌ PS `{ps_name}` not found.")

@bot.command()
@is_authorized()
async def listps(ctx):
    registry = get_registry()
    if not registry: return await ctx.send("❌ No PS registered.")
    
    embed = discord.Embed(title="📂 Registered Private Servers", color=0x9b59b6)
    description = ""
    for msg_id, ps_name in registry.items():
        link = f"https://discord.com/channels/{ctx.guild.id}/{config.CHANNEL_ID}/{msg_id}"
        description += f"• **{ps_name}** — [Jump]({link}) | `ID: {msg_id}`\n\n"
    embed.description = description
    await ctx.send(embed=embed)

@bot.command()
@is_authorized()
async def rename(ctx, old_name: str, new_name: str):
    registry = get_registry()
    target_id = next((k for k, v in registry.items() if v.lower() == old_name.lower()), None)
    if target_id:
        registry[target_id] = new_name
        save_registry(registry)
        await ctx.send(f"✅ Renamed **{old_name}** to **{new_name}**. Refreshing data...")
        await perform_sync()
        await update_status_webhook()
    else:
        await ctx.send(f"❌ PS `{old_name}` not found.")

async def start_bot():
    """Entry point used by run.py to start the Discord bot."""
    await bot.start(config.DISCORD_TOKEN)