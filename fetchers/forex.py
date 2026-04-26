"""
Fetches USD/KES (and other pairs) from Open Exchange Rates.
Free tier: hourly updates, base USD.
Sign up at: https://openexchangerates.org/
"""
import httpx
from datetime import datetime
from db.client import get_db
from core.config import settings
import logging

logger = logging.getLogger(__name__)

OER_URL = "https://openexchangerates.org/api/latest.json"


async def fetch_forex_rates() -> dict:
    """Fetch latest KES exchange rates."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                OER_URL,
                params={"app_id": settings.open_exchange_rates_app_id, "symbols": "KES,EUR,GBP"},
            )
            resp.raise_for_status()
            data = resp.json()

        rates = data["rates"]
        usd_kes = rates.get("KES", 0)

        # OER base is USD — convert pairs relative to KES
        eur_kes = usd_kes / rates.get("EUR", 1) if "EUR" in rates else None
        gbp_kes = usd_kes / rates.get("GBP", 1) if "GBP" in rates else None

        result = {
            "usd_kes": round(usd_kes, 2),
            "eur_kes": round(eur_kes, 2) if eur_kes else None,
            "gbp_kes": round(gbp_kes, 2) if gbp_kes else None,            
            "source": "open_exchange_rates",
        }
        logger.info("Forex rates fetched: %s", result)
        return result

    except Exception as e:
        logger.error("Forex fetch failed: %s", e)
        raise


async def store_forex_rates(rates: dict) -> None:
    db = get_db()
    db.table("forex_rates").insert(rates).execute()
    logger.info("Forex rates stored.")


async def run_forex_fetcher() -> dict:
    rates = await fetch_forex_rates()
    await store_forex_rates(rates)
    return rates