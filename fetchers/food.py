import httpx
import re
import json
import logging
from bs4 import BeautifulSoup
from datetime import datetime
import asyncio
from db.client import get_db
from ai.core import call_ai

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# BASKET DEFINITION
# Add / remove items here. Unit should reflect what we track.
# quickmart_slug: the URL path on quickmart.co.ke for the product
# search_term: what to search/ask AI if scrape fails
# ─────────────────────────────────────────────────────────────
BASKET_ITEMS = [
    # ── Grains & Flour ────────────────────────────────────────
    {
        "name":          "maize_flour",
        "label":         "Maize Flour (Unga)",
        "unit":          "1kg",
        "category":      "grains",
        "quickmart_slug": "dola-maize-flour-1kg-1501",
        "search_term":   "Dola maize flour 1kg Kenya price KES",
    },
    {
        "name":          "wheat_flour",
        "label":         "Wheat Flour",
        "unit":          "1kg",
        "category":      "grains",
        "quickmart_slug": "jogoo-wheat-flour-1kg-1501",
        "search_term":   "Jogoo wheat flour 1kg Kenya price KES",
    },
    {
        "name":          "rice",
        "label":         "Rice",
        "unit":          "1kg",
        "category":      "grains",
        "quickmart_slug": "pishori-rice-1kg-1501",
        "search_term":   "pishori rice 1kg Kenya supermarket price KES",
    },
    # ── Sugar & Sweeteners ────────────────────────────────────
    {
        "name":          "sugar",
        "label":         "Sugar",
        "unit":          "1kg",
        "category":      "sweeteners",
        "quickmart_slug": "mumias-sugar-1kg-1501",
        "search_term":   "Mumias sugar 1kg Kenya price KES",
    },
    # ── Oils & Fats ───────────────────────────────────────────
    {
        "name":          "cooking_oil",
        "label":         "Cooking Oil",
        "unit":          "1L",
        "category":      "oils",
        "quickmart_slug": "fresh-fri-cooking-oil-1l-1501",
        "search_term":   "Fresh Fri cooking oil 1 litre Kenya price KES",
    },
    # ── Dairy ─────────────────────────────────────────────────
    {
        "name":          "milk",
        "label":         "Milk (Fresh)",
        "unit":          "1L",
        "category":      "dairy",
        "quickmart_slug": "brookside-fresh-milk-1l-1501",
        "search_term":   "Brookside fresh milk 1 litre Kenya price KES",
    },
    # ── Protein ───────────────────────────────────────────────
    {
        "name":          "eggs",
        "label":         "Eggs",
        "unit":          "tray (30)",
        "category":      "protein",
        "quickmart_slug": "eggs-tray-30-1501",
        "search_term":   "eggs tray 30 Kenya supermarket price KES 2026",
    },
    # ── Bread ─────────────────────────────────────────────────
    {
        "name":          "bread",
        "label":         "Bread (White Sliced)",
        "unit":          "400g loaf",
        "category":      "baked",
        "quickmart_slug": "supa-loaf-white-bread-400g-1501",
        "search_term":   "Supa Loaf bread 400g Kenya price KES",
    },
    # ── Legumes ───────────────────────────────────────────────
    {
        "name":          "beans",
        "label":         "Beans (Rose Coco)",
        "unit":          "1kg",
        "category":      "legumes",
        "quickmart_slug": "rose-coco-beans-1kg-1501",
        "search_term":   "rose coco beans 1kg Kenya supermarket price KES",
    },            
    # ── Vegetables (proxy — harder to scrape, AI preferred) ───
    {
        "name":          "tomatoes",
        "label":         "Tomatoes",
        "unit":          "1kg",
        "category":      "vegetables",
        "quickmart_slug": None,             # No fixed product page; AI handles
        "search_term":   "tomatoes 1kg Kenya market price KES 2026",
    },
    {
        "name":          "onions",
        "label":         "Onions",
        "unit":          "1kg",
        "category":      "vegetables",
        "quickmart_slug": None,
        "search_term":   "onions 1kg Kenya market price KES 2026",
    },
]

# Quickmart Nairobi branch (Waiyaki Way) — stable Nairobi reference
QUICKMART_BASE = "https://www.quickmart.co.ke"
QUICKMART_BRANCH_ID = "1501"   # Waiyaki Way, Nairobi

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MaliMind/1.0; +https://malimind.co.ke)",
    "Accept-Language": "en-US,en;q=0.9",
}


# ─────────────────────────────────────────────────────────────
# TIER 1: Quickmart product page scrape
# ─────────────────────────────────────────────────────────────
async def _scrape_quickmart_price(slug: str, item_label: str) -> float | None:
    """
    Fetch a Quickmart product page and extract the KES price.
    Returns price as float or None if not found.
    """
    url = f"{QUICKMART_BASE}/{slug}"
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers=HEADERS)
            if resp.status_code != 200:
                logger.warning("Quickmart %s returned HTTP %s", slug, resp.status_code)
                return None

        html = resp.text
        soup = BeautifulSoup(html, "lxml")

        # Quickmart price patterns:
        # 1. Look for "KES 250.00" pattern anywhere in page text
        text = soup.get_text(separator=" ")
        kes_matches = re.findall(r"KES\s*([\d,]+(?:\.\d{1,2})?)", text)
        if kes_matches:
            # Filter out obviously wrong values (< 5 or > 50000)
            candidates = [
                float(p.replace(",", "")) for p in kes_matches
                if 5 < float(p.replace(",", "")) < 50000
            ]
            if candidates:
                # Take the lowest reasonable price (avoids picking discounted-from price)
                price = min(candidates)
                logger.info("[Quickmart scrape] %s → KES %.2f", item_label, price)
                return price

        # 2. Try meta og:price tag
        meta_price = soup.find("meta", {"property": "product:price:amount"})
        if meta_price and meta_price.get("content"):
            return float(meta_price["content"])

    except Exception as e:
        logger.warning("Quickmart scrape failed for %s: %s", slug, e)

    return None


# ─────────────────────────────────────────────────────────────
# TIER 2: AI HTML extraction
# When we get HTML but can't parse price cleanly, pass to Claude
# ─────────────────────────────────────────────────────────────
async def _ai_extract_price_from_html(html: str, item_label: str, unit: str) -> float | None:
    """
    Ask AI to extract price from raw HTML.
    Used when BeautifulSoup finds price candidates but they're ambiguous.
    """
    # Truncate HTML to avoid token overload
    truncated = html[:6000]

    system_prompt = "You are a price extraction assistant for a Kenyan household cost tracker. Return ONLY valid JSON, nothing else."
    prompt = f"""
From the HTML below, extract the CURRENT selling price in KES for:
Item: {item_label} ({unit})

Return ONLY valid JSON:
{{
  "price_kes": <float or null if not found>,
  "confidence": "high" | "medium" | "low"
}}

HTML:
{truncated}
"""
    try:
        data = call_ai(prompt, system_prompt=system_prompt, max_tokens=100)
        price = data.get("price_kes")
        if price and float(price) > 5:
            logger.info("[AI HTML extract] %s → KES %.2f (confidence: %s)", item_label, float(price), data.get("confidence"))
            return float(price)
    except Exception as e:
        logger.error("[AI HTML extract error] %s", e)
    return None


# ─────────────────────────────────────────────────────────────
# TIER 3: AI knowledge fallback (Batched)
# ─────────────────────────────────────────────────────────────
async def _ai_batch_price_fallback(items: list[dict]) -> dict[str, float]:
    """
    Ask AI for best estimates of market prices in Kenya for multiple items at once.
    Returns a dictionary mapping item 'name' to the estimated price float.
    """
    today = datetime.utcnow().strftime("%B %Y")
    
    items_text = "\n".join([
        f"- Name: {item['name']}, Label: {item['label']}, Quantity: {item['unit']}, Context: {item.get('search_term', '')}" 
        for item in items
    ])

    system_prompt = "You are a Kenyan market price expert. Return ONLY valid JSON, nothing else."
    prompt = f"""
Provide the current retail supermarket price in Nairobi, Kenya for the following items:

{items_text}

Date: {today}

Return ONLY valid JSON matching this exact structure:
{{
  "prices": {{
    "<item_name>": <float, best estimate in KES>,
    ...
  }}
}}
"""
    try:
        data = call_ai(prompt, system_prompt=system_prompt, max_tokens=500)
        prices = data.get("prices", {})
        for item in items:
            name = item["name"]
            price = prices.get(name)
            if price is not None:
                logger.info("[AI batch fallback] %s → KES %.2f", item["label"], float(price))
            else:
                logger.warning("[AI batch fallback] Missing price for %s", item["label"])
        return {k: float(v) for k, v in prices.items() if v is not None}
    except Exception as e:
        logger.error("[AI batch fallback error] %s", e)
        return {}


# ─────────────────────────────────────────────────────────────
# MAIN FETCH LOGIC — per item
# ─────────────────────────────────────────────────────────────
async def fetch_item_scrape_only(item: dict) -> dict:
    """
    Fetch the current price for a single basket item via scrape only.
    """
    label = item["label"]
    slug = item.get("quickmart_slug")
    price = None
    source = "unknown"

    # ── Tier 1: Quickmart scrape ────────────────────────────
    if slug:
        price = await _scrape_quickmart_price(slug, label)
        if price:
            source = f"quickmart ({QUICKMART_BASE}/{slug})"

    return {
        "item": item,
        "price": price,
        "source": source
    }


# ─────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────
async def fetch_food_basket(items: list[dict] | None = None) -> list[dict]:
    """
    Fetch current prices for all basket items concurrently.
    First tries to scrape each item, then batches all failures into a single AI fallback request.
    """    
    target_items = items or BASKET_ITEMS
    logger.info("Fetching food basket prices for %d items...", len(target_items))

    # Phase 1: Fetch all items concurrently via scrape
    tasks = [fetch_item_scrape_only(item) for item in target_items]
    scrape_results = await asyncio.gather(*tasks, return_exceptions=True)

    valid_results = []
    failed_items = []

    for result in scrape_results:
        if isinstance(result, Exception):
            logger.error("Scrape crashed: %s", result)
            continue
            
        item = result["item"]
        price = result["price"]
        source = result["source"]
        
        if price is not None:
            valid_results.append({
                "name":       item["name"],
                "price_kes":  round(price, 2),
                "unit":       item["unit"],
                "retailer":   "Quickmart" if "quickmart" in source else "UNKNOWN",
                "created_at": datetime.utcnow().isoformat(),
            })
        else:
            failed_items.append(item)

    # Phase 2: Batch AI fallback
    if failed_items:
        logger.info("[Tier 1 ✗] Batching AI fallback for %d items...", len(failed_items))
        ai_prices = await _ai_batch_price_fallback(failed_items)
        
        for item in failed_items:
            price = ai_prices.get(item["name"], 0.0)
            valid_results.append({
                "name":       item["name"],
                "price_kes":  round(price, 2) if price else 0.0,
                "unit":       item["unit"],
                "retailer":   "AI_ESTIMATE",
                "created_at": datetime.utcnow().isoformat(),
            })

    logger.info("Food basket: %d items processed.", len(valid_results))
    return valid_results


async def store_food_basket(basket: list[dict]) -> None:
    """Insert fetched basket prices into Supabase food_basket table."""
    db = get_db()
    rows = [
        {
            "name":       r["name"],
            "price_kes":  r["price_kes"],
            "unit":       r["unit"],
            "retailer":   r["retailer"],
            "created_at": r["created_at"],
        }
        for r in basket
    ]
    db.table("food_basket").insert(rows).execute()
    logger.info("Stored %d food basket items.", len(rows))


async def get_latest_basket() -> list[dict]:
    """
    Fetch the most recent price for each item from Supabase.
    Returns one row per unique item name (latest fetched_at).
    """
    db = get_db()
    # Supabase doesn't do DISTINCT ON natively — fetch last N and dedupe in Python
    result = (
        db.table("food_basket")
        .select("*")
        .order("created_at", desc=True)
        .limit(len(BASKET_ITEMS) * 3)   # buffer for dupes
        .execute()
    )
    seen: set[str] = set()
    latest: list[dict] = []
    for row in result.data:
        if row["name"] not in seen:
            seen.add(row["name"])
            latest.append(row)
    return latest


async def run_food_fetcher(custom_items: list[dict] | None = None) -> list[dict]:
    """
    Main entry point — fetch + store all basket prices.
    Called by cron and /fetch/food API route.

    Pass custom_items to override the default basket (e.g. fetch only one category).
    """
    basket = await fetch_food_basket(custom_items)
    await store_food_basket(basket)
    return basket