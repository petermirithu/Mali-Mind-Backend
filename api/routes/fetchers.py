"""
Internal routes to manually trigger data fetchers.
These are also called by GitHub Actions cron jobs.
Protect with a secret header in production.
"""
from fastapi import APIRouter, Header, HTTPException
from fetchers.fuel import run_fuel_fetcher
from fetchers.forex import run_forex_fetcher
from fetchers.food import run_food_fetcher
from ai.insights import run_insight_pipeline
from fetchers.feed import run_feed_fetcher
from core.config import settings

router = APIRouter(prefix="/fetch", tags=["fetchers"])

CRON_SECRET = settings.cron_secret


def _auth(x_cron_secret: str):
    if x_cron_secret != CRON_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/fuel")
async def trigger_fuel(x_cron_secret: str = Header(...)):
    _auth(x_cron_secret)
    data = await run_fuel_fetcher()
    insight = await run_insight_pipeline("fuel_update", data)
    return {"status": "ok", "data": data, "insight": insight["summary"]}


@router.post("/forex")
async def trigger_forex(x_cron_secret: str = Header(...)):
    _auth(x_cron_secret)
    data = await run_forex_fetcher()
    insight = await run_insight_pipeline("forex_update", data)
    return {"status": "ok", "data": data, "insight": insight["summary"]}


@router.post("/food")
async def trigger_food(x_cron_secret: str = Header(...)):
    _auth(x_cron_secret)
    data = await run_food_fetcher()
    insight = await run_insight_pipeline("food_update", {"items": data})
    return {"status": "ok", "seeded": len(data), "insight": insight["summary"]}

@router.post("/feed")
async def trigger_feed(x_cron_secret: str = Header(...)):
    _auth(x_cron_secret)    
    data = await run_feed_fetcher()        
    return data