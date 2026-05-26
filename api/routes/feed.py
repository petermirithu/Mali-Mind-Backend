from fastapi import APIRouter, HTTPException, Query
from db.client import get_db
from schemas.models import FeedItem
from ai.insights import generate_insight

router = APIRouter(prefix="/feed", tags=["feed"])


@router.get("/", response_model=list[FeedItem])
async def get_feed(limit: int = Query(default=20, le=50)):
    """
    Returns latest Kenya economic events with AI-generated explanations.
    Powers the Kenya Pulse Feed on mobile.
    """
    db = get_db()
    try:
        result = (
            db.table("feed_items")
            .select("*")
            .order("published_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ask", tags=["ask-mali"])
async def ask_mali(q: str = Query(..., description="User question about Kenyan economy")):
    """
    Simple Ask Mali endpoint — proxies a user question to AI with economic context.
    """    
    db = get_db()

    # Pull latest snapshot as context
    fuel = db.table("fuel_prices").select("*").order("created_at", desc=True).limit(1).execute().data
    forex = db.table("forex_rates").select("*").order("created_at", desc=True).limit(1).execute().data

    context = {
        "user_question": q,
        "fuel": fuel[0] if fuel else {},
        "forex": forex[0] if forex else {},
    }

    insight = await generate_insight("ask_mali", context)
    return {"question": q, "answer": insight["summary"]}