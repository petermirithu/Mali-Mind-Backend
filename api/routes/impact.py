from fastapi import APIRouter, HTTPException
from datetime import datetime
from db.client import get_db
from schemas.models import ImpactResponse, ImpactItem
from ai.insights import generate_insight

router = APIRouter(prefix="/impact", tags=["impact"])


def compute_change_pct(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return round(((current - previous) / previous) * 100, 2)


@router.get("/", response_model=ImpactResponse)
async def get_impact():
    """
    Computes impact of latest price changes on a Kenyan household.
    Powers the Impact Page on mobile.
    """
    db = get_db()

    try:
        # Get 2 latest fuel records to compute change
        fuel_res = db.table("fuel_prices").select("*").order("created_at", desc=True).limit(2).execute()
        fuel_data = fuel_res.data

        # Get 2 latest forex records
        forex_res = db.table("forex_rates").select("*").order("created_at", desc=True).limit(2).execute()
        forex_data = forex_res.data

        items: list[ImpactItem] = []
        data_for_ai = {}

        # ── Fuel Impact ───────────────────────────────────────────────────────
        if len(fuel_data) >= 2:
            curr_petrol = fuel_data[0]["petrol_per_litre"]
            prev_petrol = fuel_data[1]["petrol_per_litre"]
            pct = compute_change_pct(curr_petrol, prev_petrol)
            direction = "up" if pct > 0 else ("down" if pct < 0 else "stable")
            # Assume avg 30L/month fuel consumption → transport cost
            monthly_impact = round(30 * (curr_petrol - prev_petrol), 2)

            items.append(ImpactItem(
                category="Transport / Fuel",
                change_pct=pct,
                direction=direction,
                monthly_estimate_kes=monthly_impact,
                explanation=f"Petrol is KES {curr_petrol}/L ({'+' if pct > 0 else ''}{pct}%). "
                            f"Expect monthly transport costs to {'rise' if pct > 0 else 'fall'} "
                            f"by ~KES {abs(monthly_impact):.0f}.",
            ))
            data_for_ai["fuel"] = {"current": curr_petrol, "previous": prev_petrol, "change_pct": pct}

        # ── Forex Impact ──────────────────────────────────────────────────────
        if len(forex_data) >= 2:
            curr_usd = forex_data[0]["usd_kes"]
            prev_usd = forex_data[1]["usd_kes"]
            pct = compute_change_pct(curr_usd, prev_usd)
            direction = "up" if pct > 0 else ("down" if pct < 0 else "stable")

            items.append(ImpactItem(
                category="Imports / USD Rate",
                change_pct=pct,
                direction=direction,
                monthly_estimate_kes=None,
                explanation=f"USD/KES is {curr_usd} ({'+' if pct > 0 else ''}{pct}%). "
                            f"Imported goods (electronics, fuel, medicine) will likely "
                            f"{'cost more' if pct > 0 else 'become cheaper'}.",
            ))
            data_for_ai["forex"] = {"current": curr_usd, "previous": prev_usd, "change_pct": pct}

        # ── AI Summary ────────────────────────────────────────────────────────
        ai_insight = await generate_insight("impact_request", data_for_ai)
        overall_score = ai_insight.get("impact_score", 0.0)

        return ImpactResponse(
            items=items,
            overall_score=overall_score,
            ai_summary=ai_insight["summary"],
            computed_at=datetime.utcnow(),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))