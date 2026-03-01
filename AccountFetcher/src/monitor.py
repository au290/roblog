import time
import asyncio
import logging
from datetime import datetime, timedelta
from src import config
from src import utils
from src.sync import sync_accounts

logger = logging.getLogger('fleet_monitor')

# --- GLOBALS FOR PERFORMANCE TRACKING ---
start_time = int(time.time() * 1000)

global_perf_history = {
    "lastTotalCaught": 0, "lastCheckTime": None, 
    "currentFPM": "0.0", "currentFPH": "0", 
    "prevFPM": "0.0", "prevFPH": "0"
}
server_perf_history = {}

def get_stored_message_id():
    data = utils.load_json_safe(config.DATABASE_FILE)
    return data.get("lastMessageId")

def save_message_id(msg_id):
    utils.save_json_safe(config.DATABASE_FILE, {"lastMessageId": msg_id})

async def fetch_all_data(api_client):
    """Gathers all player data from Wintercode and calculates performance."""
    global global_perf_history, server_perf_history
    
    fleet_data = utils.load_json_safe(config.FLEET_DATA_FILE)
    if not fleet_data:
        logger.warning(f"⚠️ Fleet data '{config.FLEET_DATA_FILE}' is empty or missing.")
        return None
        
    player_mapping = {}
    player_list_for_api = []
    
    # Map players from the local registry
    ps_groups = fleet_data.get("ps_groups", {})
    for server_name, players in ps_groups.items():
        for player in players:
            username = player.get("username")
            if username:
                player_mapping[username] = server_name
                player_list_for_api.append(username)
                
    system_health = fleet_data.get("system_health", {})

    # Ensure API Authentication
    if not api_client.token:
        success = await api_client.login()
        if not success:
            logger.error("❌ Failed to log into WinterAPI for monitoring.")
            return None

    all_profiles = {}
    chunk_size = 25
    
    # Fetch Player Profiles in Batches
    for i in range(0, len(player_list_for_api), chunk_size):
        chunk = player_list_for_api[i:i + chunk_size]
        logger.info(f"[PROGRESS] Fetching profiles: {i + len(chunk)}/{len(player_list_for_api)}...")
        try:
            data = await api_client.fetch_profiles_batch(chunk)
            if data:
                all_profiles.update(data)
        except Exception as err:
            logger.error(f"⚠️ Error in chunk {i}: {err}")
        if i + chunk_size < len(player_list_for_api):
            await asyncio.sleep(1)

    if not all_profiles:
        return None

    # Fetch Global API Stats in Parallel
    info_task = api_client.fetch_endpoint("/captcha/info")
    captcha_task = api_client.fetch_endpoint("/captcha/yescaptcha-balance")
    stats_task = api_client.fetch_endpoint("/captcha/stats?hours=24")
    
    info_json, captcha_json, stats_json = await asyncio.gather(info_task, captcha_task, stats_task)

    total_success, total_failed = 0, 0
    stats_dict = utils.safe_dict(stats_json)
    if stats_dict.get("success") and isinstance(stats_dict.get("data"), list):
        for hour in stats_dict["data"]:
            total_success += hour.get("success", 0)
            total_failed += hour.get("failed", 0)

    # Initialize counters
    total_evo, total_sctb, online_real, offline_real = 0, 0, 0, 0
    global_total_caught = 0
    server_totals = {}
    active_quest_count = 0
    quest_summary = {}
    rod_stats = {}
    
    now = int(time.time() * 1000)
    TIME_TOLERANCE = 15 * 60 * 1000
    obj_names = {0: "300 Rare", 1: "3 Mythic", 2: "1 Secret", 3: "1M Coin"}

    # Process individual profiles
    for name in player_list_for_api:
        profile = all_profiles.get(name)
        if isinstance(profile, dict):
            caught = profile.get("totalCaught", 0)
            global_total_caught += caught
            
            server_name = player_mapping.get(name, "Unassigned")
            server_totals[server_name] = server_totals.get(server_name, 0) + caught
            
            last_update_ms = profile.get("lastUpdate", 0)
            if last_update_ms < 10000000000:
                last_update_ms *= 1000
                
            if profile.get("status") == "online" and (now - last_update_ms) < TIME_TOLERANCE:
                online_real += 1
            else:
                offline_real += 1
                
            # Safe Quest Parsing
            quests = utils.safe_dict(profile.get("Quests"))
            mainline = utils.safe_dict(quests.get("Mainline"))
            ds_quest = utils.safe_dict(mainline.get("Deep Sea Quest"))
            
            if ds_quest.get("Active") is True:
                objectives = utils.safe_list(ds_quest.get("Objectives"))
                remaining = [obj_names.get(idx) for idx, obj in enumerate(objectives) 
                             if isinstance(obj, dict) and obj.get("Completed") is False]
                remaining = [r for r in remaining if r is not None]
                if remaining:
                    active_quest_count += 1
                    label = f"sisa {', '.join(remaining)}"
                    quest_summary[label] = quest_summary.get(label, 0) + 1
                    
            # Safe Rod Parsing
            player_data = utils.safe_dict(profile.get("Player"))
            equipped = utils.safe_dict(player_data.get("Equipped"))
            rod = utils.safe_dict(equipped.get("Rod"))
            equipped_rod = rod.get("Name", "No Rod")
            rod_stats[equipped_rod] = rod_stats.get(equipped_rod, 0) + 1
            
            # Safe Inventory Parsing
            inventory = utils.safe_dict(profile.get("Inventory"))
            for item in utils.safe_list(inventory.get("Enchant Stones")):
                if isinstance(item, dict) and item.get("Name") == "Evolved Enchant Stone":
                    total_evo += item.get("Quantity", 1)
                    
            for item in utils.safe_list(inventory.get("Fish")):
                if isinstance(item, dict) and (item.get("Name") in config.TARGET_ITEMS or item.get("Type") in config.TARGET_ITEMS):
                    total_sctb += item.get("Quantity", 1)
        else:
            offline_real += 1

    # Calculate Global Performance
    if global_perf_history["lastCheckTime"] is not None:
        t_diff = (now - global_perf_history["lastCheckTime"]) / (1000 * 60)
        c_diff = global_total_caught - global_perf_history["lastTotalCaught"]
        if c_diff >= 0 and t_diff > 0:
            global_perf_history["prevFPM"] = global_perf_history["currentFPM"]
            global_perf_history["prevFPH"] = global_perf_history["currentFPH"]
            global_perf_history["currentFPM"] = f"{(c_diff / t_diff):.2f}"
            global_perf_history["currentFPH"] = f"{(float(global_perf_history['currentFPM']) * 60):.0f}"
            
    global_perf_history["lastTotalCaught"] = global_total_caught
    global_perf_history["lastCheckTime"] = now

    # Calculate Server Performance
    for s_name, current_total in server_totals.items():
        if s_name not in server_perf_history:
            server_perf_history[s_name] = {"lastTotalCaught": 0, "lastCheckTime": None, "fpm": "0.00", "fph": "0", "prevFPM": "0.00", "prevFPH": "0"}
        
        hist = server_perf_history[s_name]
        if hist["lastCheckTime"] is not None:
            t_diff = (now - hist["lastCheckTime"]) / (1000 * 60)
            c_diff = current_total - hist["lastTotalCaught"]
            if c_diff >= 0 and t_diff > 0:
                hist["prevFPM"] = hist["fpm"]
                hist["prevFPH"] = hist["fph"]
                hist["fpm"] = f"{(c_diff / t_diff):.2f}"
                hist["fph"] = f"{(float(hist['fpm']) * 60):.0f}"
                
        hist["lastTotalCaught"] = current_total
        hist["lastCheckTime"] = now

    rate = "0.0"
    if (total_success + total_failed) > 0:
        rate = f"{((total_success / (total_success + total_failed)) * 100):.1f}"

    return {
        "totalAccounts": len(player_list_for_api),
        "onlineCount": online_real,
        "globalFPM": global_perf_history["currentFPM"],
        "globalFPH": global_perf_history["currentFPH"],
        "globalPrevFPH": global_perf_history["prevFPH"],
        "serverStats": server_perf_history,
        "systemHealth": system_health,
        "activeQuestCount": active_quest_count,
        "questSummary": quest_summary,
        "rodStats": rod_stats,
        "totalEvo": total_evo,
        "totalSctb": total_sctb,
        "saldoRp": utils.safe_dict(info_json).get("data", {}).get("balance", utils.safe_dict(info_json).get("balance", 0)),
        "poinYes": utils.safe_dict(captcha_json).get("balance", utils.safe_dict(captcha_json).get("data", {}).get("balance", "0")),
        "captchaHealth": {"success": total_success, "failed": total_failed, "rate": rate}
    }

async def update_monitor(api_client):
    """Syncs accounts, fetches data, and updates the Discord Webhook."""
    logger.info("🔄 Running Account Sync Check...")
    await sync_accounts(api_client)
    
    data = await fetch_all_data(api_client)
    if not data:
        return

    # Using WITA timezone (UTC+8)
    wita_time = datetime.utcnow() + timedelta(hours=8)
    timestamp = wita_time.strftime("%d/%m/%Y, %H:%M:%S")
    
    # Format Rod Stats
    rod_text = ""
    sorted_rods = sorted(data["rodStats"].items(), key=lambda x: 0 if "ghost" in x[0].lower() else 1)
    for name, count in sorted_rods:
        if "ghostfinn" in name.lower():
            rod_text += f"### <:ghostfinn_rod:1469932309896626353> **{name.upper()} : {count}**\n"
        else:
            rod_text += f"🎣 {name.ljust(12)} : {count}\n"
            
    # Format Quest Details
    quest_details = "".join([f"🔹 {count} Akun {label}\n" for label, count in data["questSummary"].items()])
    if not quest_details: quest_details = "🔹 Tidak ada quest aktif\n"

    # Split servers into left/right columns
    def extract_num(s_name):
        nums = [int(s) for s in s_name.split() if s.isdigit()]
        return nums[0] if nums else 0

    sorted_servers = sorted(data["serverStats"].items(), key=lambda x: extract_num(x[0]))
    mid = (len(sorted_servers) + 1) // 2
    left_servers, right_servers = sorted_servers[:mid], sorted_servers[mid:]
    
    def format_server_column(servers):
        text = ""
        for name, stats in servers:
            trend = utils.get_trend_emoji(stats["fph"], stats["prevFPH"])
            sys = data["systemHealth"].get(name, {})
            text += f"📍 **{name}**: `{stats['fpm']}` M | `{stats['fph']}` H{trend}\n"
            text += f"└ 💻 `{sys.get('cpu_usage', 'N/A')}` | 💾 `{sys.get('memory_details', 'N/A')}`\n\n"
        return text.strip() or "Calculating..."

    # Build Embed
    global_trend = utils.get_trend_emoji(data["globalFPH"], data["globalPrevFPH"])
    embed = {
        "title": "📋 GLOBAL STOCK & STATUS MONITOR",
        "description": f"# Online / Accounts\n# <:profile:1469943406498156649> **{data['onlineCount']}** / **{data['totalAccounts']}**\n{rod_text}```\n🌊 GF QUEST: {data['activeQuestCount']}\n{quest_details}```",
        "color": 0x3498db,
        "fields": [
            {"name": "🚀 GLOBAL PERFORMANCE", "value": f"```{data['globalFPM']} FPM |\n{data['globalFPH']} FPH{global_trend}```", "inline": False},
            {"name": "📡 SERVER PERFORMANCE (LEFT)", "value": format_server_column(left_servers), "inline": True},
            {"name": "📡 SERVER PERFORMANCE (RIGHT)", "value": format_server_column(right_servers), "inline": True},
            {"name": "💎 TOTAL EVO", "value": f"```{data['totalEvo']}```", "inline": False},
            {"name": "🐟 TOTAL SC TB", "value": f"```{data['totalSctb']}```", "inline": True},
            {"name": "💳 SALDO UTAMA", "value": f"```Rp {data['saldoRp']:,}```", "inline": False},
            {"name": "🤖 YESCAPTCHA", "value": f"```{data['poinYes']} pts```", "inline": False},
            {"name": "🛡️ CAPTCHA HEALTH", "value": f"✅ Success: `{data['captchaHealth']['success']}` | ❌ Failed: `{data['captchaHealth']['failed']}` |\n📉 Rate: `{data['captchaHealth']['rate']}%`", "inline": False}
        ],
        "footer": {"text": f"Last Sync: {timestamp} WITA |\nUptime: {utils.get_uptime_string(start_time)}"}
    }
    
    # Send Webhook
    last_message_id = get_stored_message_id()
    url = f"{config.MONITOR_WEBHOOK_URL}/messages/{last_message_id}" if last_message_id else f"{config.MONITOR_WEBHOOK_URL}?wait=true"
    method = api_client.session.patch if last_message_id else api_client.session.post

    try:
        async with method(url, json={"embeds": [embed]}) as res:
            if res.status in (200, 204) and not last_message_id:
                result = await res.json()
                save_message_id(result.get("id"))
    except Exception as err:
        logger.error(f"Webhook Error: {str(err)}")