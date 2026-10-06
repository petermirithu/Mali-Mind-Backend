"""Authenticated GET cron triggers and backward-compatible POST fetchers."""
from fastapi import APIRouter, Depends

from core.cron_auth import require_cron_secret
from fetchers.fuel import run_fuel_fetcher
from fetchers.forex import run_forex_fetcher
from fetchers.food import run_food_fetcher
from ai.insights import run_insight_pipeline
from fetchers.feed import run_feed_fetcher

router = APIRouter(
    prefix="/fetch", tags=["fetchers"], dependencies=[Depends(require_cron_secret)]
)


@router.get("/fuel", include_in_schema=False)
@router.post("/fuel")
async def trigger_fuel():
    data = await run_fuel_fetcher()
    insight = await run_insight_pipeline("fuel_update", data)
    return {"status": "ok", "data": data, "insight": insight["summary"]}


@router.get("/forex", include_in_schema=False)
@router.post("/forex")
async def trigger_forex():
    data = await run_forex_fetcher()
    insight = await run_insight_pipeline("forex_update", data)
    return {"status": "ok", "data": data, "insight": insight["summary"]}


@router.get("/food", include_in_schema=False)
@router.post("/food")
async def trigger_food():
    data = await run_food_fetcher()
    insight = await run_insight_pipeline("food_update", {"items": data})
    return {"status": "ok", "seeded": len(data), "insight": insight["summary"]}

@router.get("/feed", include_in_schema=False)
@router.post("/feed")
async def trigger_feed():
    data = await run_feed_fetcher()        
    return data