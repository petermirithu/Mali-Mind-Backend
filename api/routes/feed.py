from fastapi import APIRouter, HTTPException, Query
from db.client import get_db
from schemas.models import FeedItem
from ai.insights import generate_insight
from api.services.feed import FeedService

router = APIRouter(prefix="/feed", tags=["feed"])

@router.get("/", response_model=list[FeedItem])
async def get_feed():
    """
    Returns latest Kenya economic events with AI-generated explanations.
    """
    try:
        feed_items = await FeedService.fetch_feeds()
        return feed_items
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/ask", tags=["ask-mali"])
async def ask_mali(q: str = Query(..., description="User question about Kenyan economy")):
    """
    Simple Ask Mali endpoint — proxies a user question to AI with economic context.
    """
    db = get_db()

    fuel = db.table("fuel_prices").select("*").order("created_at", desc=True).limit(1).execute().data
    forex = db.table("forex_rates").select("*").order("created_at", desc=True).limit(1).execute().data

    context = {
        "user_question": q,
        "fuel": fuel[0] if fuel else {},
        "forex": forex[0] if forex else {},
    }

    insight = await generate_insight("ask_mali", context)
    return {"question": q, "answer": insight["summary"]}