import httpx
import asyncio
import time
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging

# ================= CONFIG =================
SCRAPER_APIS = [
    "https://without-proxy-yyjc.onrender.com",   # Primary
    "https://without-proxy2.onrender.com"  # Secondary
    
]

CURRENT_PRIMARY_INDEX = 0

# Telegram Bot config
TELEGRAM_BOT_TOKEN = "8495512623:AAF6lpsd0vAAfcbCABre05IJ_-_WAdzItYk"
TELEGRAM_CHAT_ID = "5029478739"

# Stats / Alerts
STATS = {
    "last_alerts": []
}

# ================= APP INIT =================
app = FastAPI(title="Master Instagram Scraper API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("master-api")

# ================= UTILS =================
def get_api_order():
    global CURRENT_PRIMARY_INDEX
    n = len(SCRAPER_APIS)
    return [SCRAPER_APIS[(CURRENT_PRIMARY_INDEX + i) % n] for i in range(n)]

async def notify_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, data=payload)
        STATS["last_alerts"].append({"time": time.time(), "msg": message})
        STATS["last_alerts"] = STATS["last_alerts"][-10:]
    except Exception as e:
        logger.error(f"Failed to send Telegram notification: {e}")

def format_error_message(api_name: str, attempt: int, error: str, status_code: int = None):
    base = f"❌ ERROR | API: {api_name} | Attempt: {attempt}"
    if status_code:
        return f"{base} | Status: {status_code} | {error}"
    else:
        return f"{base} | Exception: {error}"

# ================= SCRAPE ENDPOINT =================
@app.get("/scrape/{username}")
async def scrape_master(username: str):
    global CURRENT_PRIMARY_INDEX
    apis_to_try = get_api_order()

    for base_url in apis_to_try:
        url = f"{base_url}/scrape/{username}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)

            if resp.status_code == 200:
                data = resp.json()
                CURRENT_PRIMARY_INDEX = SCRAPER_APIS.index(base_url)
                data["source_api"] = base_url
                logger.info(f"✅ User {username} fetched via {base_url}")
                return data

            elif resp.status_code == 404:
                message = f"⚠️ User not found: {username} on {base_url}"
                logger.warning(message)
                await notify_telegram(message)
                raise HTTPException(status_code=404, detail="User not found")

            else:
                msg = format_error_message(base_url, 1, "Request failed", resp.status_code)
                logger.warning(msg)
                await notify_telegram(msg)

        except httpx.RequestError as e:
            msg = format_error_message(base_url, 1, str(e))
            logger.warning(msg)
            await notify_telegram(msg)
            continue

    raise HTTPException(status_code=502, detail="All scraper APIs failed")

# ================== MANUAL PRIMARY SET ==================
@app.get("/set_primary")
async def set_primary(api: str = Query(..., description="API base URL to set as primary")):
    """
    Manually set which scraper API should be primary.
    Example:
    /set_primary?api=https://without-proxy1.vercel.app
    """
    global CURRENT_PRIMARY_INDEX

    if api not in SCRAPER_APIS:
        raise HTTPException(status_code=400, detail="Invalid API URL. Must be one of configured SCRAPER_APIS.")

    CURRENT_PRIMARY_INDEX = SCRAPER_APIS.index(api)
    msg = f"✅ Primary API manually set to: {api}"
    logger.info(msg)
    await notify_telegram(msg)
    return {"success": True, "new_primary": api}

# ================= HEALTH CHECK =================
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "current_primary": SCRAPER_APIS[CURRENT_PRIMARY_INDEX],
        "last_alerts": STATS["last_alerts"]
    }

@app.head("/health")
async def health_head():
    return JSONResponse(content=None, status_code=200)

# ================= STATS =================
@app.get("/stats")
async def stats():
    return {
        "current_primary": SCRAPER_APIS[CURRENT_PRIMARY_INDEX],
        "last_alerts": STATS["last_alerts"]
    }
