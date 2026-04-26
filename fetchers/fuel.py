import httpx
import re
import json
import logging
from bs4 import BeautifulSoup
from datetime import datetime
from core.config import settings
from db.client import get_db
from ai.core import call_ai

logger = logging.getLogger(__name__)

EPRA_URL = "https://www.epra.go.ke/pump-prices/"

# Map common city name variants to what EPRA uses in their table/ticker
CITY_NAME_MAP = {
    "nairobi":  "Nairobi",
    "mombasa":  "Mombasa",
    "kisumu":   "Kisumu",
    "nakuru":   "Nakuru",
    "eldoret":  "Eldoret",
}


# ─────────────────────────────────────────────────────────────
# TIER 1: Parse the live ticker in the EPRA page <head>/<body>
# The ticker contains lines like:
#   "Nairobi PMS 197.6 ▲ 10.84%"
#   "Nairobi AGO 196.63 ▲ 18.07%"
#   "Nairobi IK 152.78 ■ 0.00%"
# ─────────────────────────────────────────────────────────────
def _parse_ticker(html: str, city: str) -> dict | None:
    """
    Extract PMS / AGO / IK prices for `city` from the EPRA ticker text.
    Returns a dict or None if city not found.
    """
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator="\n")

    pattern = re.compile(
        rf"{re.escape(city)}\s+(PMS|AGO|IK)\s+([\d.]+)",
        re.IGNORECASE,
    )
    matches = pattern.findall(text)

    if not matches:
        return None

    prices: dict[str, float] = {}
    for fuel_type, price_str in matches:
        prices[fuel_type.upper()] = float(price_str)

    if "PMS" not in prices:
        return None

    logger.info("Ticker prices for %s: %s", city, prices)
    return {
        "petrol_per_litre":   prices.get("PMS"),
        "diesel_per_litre":   prices.get("AGO"),
        "kerosene_per_litre": prices.get("IK"),
        "source": "EPRA_TICKER",
    }


# ─────────────────────────────────────────────────────────────
# TIER 2: Scrape the full pump prices table
# Filter by city, then pick the row with the MOST RECENT "From" date
# ─────────────────────────────────────────────────────────────
def _parse_table(html: str, city: str) -> dict | None:
    """
    Parse the EPRA pump prices DataTable for a specific city.
    Returns the row with the latest effective date.
    """
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if not table:
        logger.warning("No table found on EPRA page.")
        return None

    rows = table.find_all("tr")
    city_rows = []

    for row in rows:
        cells = [td.get_text(strip=True) for td in row.find_all("td")]
        # Table columns: From | To | Town | Super(PMS) | Diesel(AGO) | Kerosene(IK)
        if len(cells) < 6:
            continue
        town = cells[2].strip()
        if city.lower() not in town.lower():
            continue

        try:
            from_date = datetime.strptime(cells[0].strip(), "%d-%m-%Y")
            city_rows.append({
                "from_date":          from_date,
                "petrol_per_litre":   float(cells[3].replace(",", "")),
                "diesel_per_litre":   float(cells[4].replace(",", "")),
                "kerosene_per_litre": float(cells[5].replace(",", "")),
            })
        except (ValueError, IndexError):
            continue

    if not city_rows:
        logger.warning("No rows found for city '%s' in EPRA table.", city)
        return None

    # Pick the row with the most recent "From" date
    latest = max(city_rows, key=lambda r: r["from_date"])
    logger.info(
        "Table parse: %s prices from effective date %s",
        city, latest["from_date"].strftime("%Y-%m-%d")
    )
    return {
        "petrol_per_litre":   latest["petrol_per_litre"],
        "diesel_per_litre":   latest["diesel_per_litre"],
        "kerosene_per_litre": latest["kerosene_per_litre"],
        "source": f"EPRA_TABLE (effective {latest['from_date'].strftime('%Y-%m-%d')})",
    }


# ─────────────────────────────────────────────────────────────
# TIER 3: AI fallback — ask AI for latest known EPRA prices
# Used only when EPRA site is unreachable or layout changes
# ─────────────────────────────────────────────────────────────
async def _ai_fallback(city: str) -> dict:
    """
    Ask AI for the latest known EPRA pump prices for a city.
    Uses Gemini (primary) with OpenRouter fallback via ai.core.
    Returns structured price data with a clear AI_FALLBACK source tag.
    """    
    logger.warning("Both scrape methods failed. Using AI fallback for %s.", city)

    today = datetime.utcnow().strftime("%B %Y")

    prompt = f"""
        You are a Kenyan fuel price data assistant.
        The EPRA website (epra.go.ke) is currently unreachable.
        Based on your most recent training knowledge, provide the EPRA-regulated pump 
        prices for {city}, Kenya as of around {today}.

        Respond ONLY with valid JSON and nothing else:
        {{
        "petrol_per_litre": <float, Super PMS price in KES>,
        "diesel_per_litre": <float, Diesel AGO price in KES>,
        "kerosene_per_litre": <float, Kerosene IK price in KES>,
        "estimated_date": "<YYYY-MM string of when you believe these prices are from>",
        "confidence": "high" | "medium" | "low"
        }}

        If you are not confident about exact figures, still provide your best estimate 
        but set confidence accordingly. Do NOT add explanations outside the JSON.
    """

    data = call_ai(prompt, max_tokens=300)

    logger.info(
        "AI fallback prices for %s — confidence: %s, estimated: %s",
        city, data.get("confidence"), data.get("estimated_date")
    )

    return {
        "petrol_per_litre":   float(data["petrol_per_litre"]),
        "diesel_per_litre":   float(data["diesel_per_litre"]),
        "kerosene_per_litre": float(data["kerosene_per_litre"]),
        "source": f"AI_FALLBACK (est. {data.get('estimated_date', 'unknown')}, confidence: {data.get('confidence', 'unknown')})",
    }


# ─────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────
async def fetch_fuel_prices(city: str = "Nairobi") -> dict:
    """
    Fetch current EPRA pump prices for a given Kenyan city.
    Falls through: Tier 1 (ticker) → Tier 2 (table) → Tier 3 (AI fallback).

    Args:
        city: City name e.g. "Nairobi", "Mombasa", "Kisumu", "Nakuru", "Eldoret"

    Returns:
        dict with petrol_per_litre, diesel_per_litre, kerosene_per_litre,
        effective_date, city, source
    """
    canonical_city = CITY_NAME_MAP.get(city.lower(), city.title())

    html = None
    prices = None

    # ── Fetch EPRA page HTML ────────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as http:
            resp = await http.get(
                EPRA_URL,
                headers={"User-Agent": "MaliMind/1.0 (malimind.co.ke)"}
            )
            resp.raise_for_status()
            html = resp.text
            logger.info("EPRA page fetched: %d bytes.", len(html))
    except Exception as e:
        logger.error("Could not fetch EPRA page: %s", e)

    # ── Tier 1: Ticker (fastest, most reliable) ─────────────────────
    if html:
        prices = _parse_ticker(html, canonical_city)
        if prices:
            logger.info("[Tier 1 ✓] Ticker parse succeeded for %s.", canonical_city)

    # ── Tier 2: Full table (slower, still accurate) ─────────────────
    if not prices and html:
        logger.info("[Tier 1 ✗] Falling back to table parse for %s.", canonical_city)
        prices = _parse_table(html, canonical_city)
        if prices:
            logger.info("[Tier 2 ✓] Table parse succeeded for %s.", canonical_city)

    # ── Tier 3: AI fallback (last resort) ──────────────────────────
    if not prices:
        logger.warning("[Tier 2 ✗] Falling back to AI for %s.", canonical_city)
        prices = await _ai_fallback(canonical_city)
        logger.info("[Tier 3 ✓] AI fallback used for %s.", canonical_city)

    return {
        **prices,
        "location": canonical_city
    }


async def store_fuel_prices(prices: dict) -> None:
    """Persist fuel prices to Supabase fuel_prices table."""
    db = get_db()
    db.table("fuel_prices").insert(prices).execute()
    logger.info(
        "Stored %s fuel prices. Petrol: KES %.2f (source: %s)",
        prices["location"], prices["petrol_per_litre"], prices["source"]
    )


async def run_fuel_fetcher(city: str = "Nairobi") -> dict:
    """
    Main entry point — fetch + store fuel prices for one city.
    Called by cron jobs and /fetch/fuel API route.
    """
    prices = await fetch_fuel_prices(city)
    await store_fuel_prices(prices)
    return prices


# async def run_fuel_fetcher_all_cities(cities: list[str] | None = None) -> list[dict]:
#     """
#     Fetch + store prices for multiple cities in sequence.
#     Useful when you expand beyond Nairobi.

#     Default: Nairobi only (MVP).
#     """
#     if cities is None:
#         cities = ["Nairobi"]

#     results = []
#     for city in cities:
#         try:
#             result = await run_fuel_fetcher(city)
#             results.append(result)
#         except Exception as e:
#             logger.error("Failed fuel fetch for %s: %s", city, e)

#     return results