"""
Food Basket Fetcher — Dynamic Real-Time Kenyan Household Prices

STRATEGY:
─────────
1. SCRAPE  — Search Quickmart per item using keyword-{term}&pagesize-30.
             Parse product cards: img title + first KES price found in card.
             Each item gets its own dedicated search → clean, targeted results.

2. AI MATCH — Pass raw scraped candidates (title + price) for this item
              to Claude to pick the best match. This handles:
              - Brand name variations (Dola vs Jogoo vs Pembe)
              - Unit mismatches (500g vs 1kg)  
              - Noise products (e.g. "Maize Flour Porridge Mix" when we want plain flour)

3. AI FALLBACK — If scrape returns zero results, ask Claude for estimated
                 market price. Batched: one call covers all missed items.
"""

import httpx
import re
import json
import logging
import asyncio
from bs4 import BeautifulSoup
from datetime import datetime
from db.client import get_db
from ai.core import call_ai

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

QUICKMART_BASE   = "https://www.quickmart.co.ke"
SEARCH_URL       = f"{QUICKMART_BASE}/products/search"
BRANCH_ID        = "3501"   # Tom Mboya CBD — confirmed working

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
    "Referer": f"{QUICKMART_BASE}/{BRANCH_ID}",
}

# ─────────────────────────────────────────────────────────────────────────────
# BASKET DEFINITION
# search_keyword: what to pass to ?keyword-{term}  (keep it short & specific)
# ─────────────────────────────────────────────────────────────────────────────

BASKET_ITEMS = [
    {
        "name":           "maize_flour",
        "label":          "Maize Flour (Unga)",
        "unit":           "1kg",
        "category":       "grains",
        "search_keyword": "maize flour",
        "match_keywords": ["maize", "flour"],
    },
    {
        "name":           "wheat_flour",
        "label":          "Wheat Flour",
        "unit":           "1kg",
        "category":       "grains",
        "search_keyword": "wheat flour",
        "match_keywords": ["wheat", "flour"],
    },
    {
        "name":           "rice",
        "label":          "Rice",
        "unit":           "1kg",
        "category":       "grains",
        "search_keyword": "rice 1kg",
        "match_keywords": ["rice"],
    },
    {
        "name":           "sugar",
        "label":          "Sugar",
        "unit":           "1kg",
        "category":       "sweeteners",
        "search_keyword": "sugar 1kg",
        "match_keywords": ["sugar"],
    },
    {
        "name":           "cooking_oil",
        "label":          "Cooking Oil",
        "unit":           "1L",
        "category":       "oils",
        "search_keyword": "cooking oil 1l",
        "match_keywords": ["cooking", "oil"],
    },
    {
        "name":           "milk",
        "label":          "Milk (Fresh)",
        "unit":           "1L",
        "category":       "dairy",
        "search_keyword": "fresh milk 1l",
        "match_keywords": ["milk"],
    },
    {
        "name":           "eggs",
        "label":          "Eggs",
        "unit":           "tray (30)",
        "category":       "protein",
        "search_keyword": "eggs tray",
        "match_keywords": ["egg"],
    },
    {
        "name":           "bread",
        "label":          "Bread (White Sliced)",
        "unit":           "400g loaf",
        "category":       "baked",
        "search_keyword": "white bread loaf",
        "match_keywords": ["bread"],
    },
    {
        "name":           "beans",
        "label":          "Beans (Rose Coco)",
        "unit":           "1kg",
        "category":       "legumes",
        "search_keyword": "beans 1kg",
        "match_keywords": ["bean"],
    },
    {
        "name":           "tomatoes",
        "label":          "Tomatoes",
        "unit":           "1kg",
        "category":       "vegetables",
        "search_keyword": "tomatoes",
        "match_keywords": ["tomato"],
    },
    {
        "name":           "onions",
        "label":          "Onions",
        "unit":           "1kg",
        "category":       "vegetables",
        "search_keyword": "onions",
        "match_keywords": ["onion"],
    },
]

BASKET_BY_NAME: dict[str, dict] = {i["name"]: i for i in BASKET_ITEMS}


# ─────────────────────────────────────────────────────────────────────────────
# HTML PARSER — extracts product cards from Quickmart search results
# ─────────────────────────────────────────────────────────────────────────────

def _parse_product_cards(html: str) -> list[dict]:
    """
    Parse Quickmart product cards and return separated structured rows.

    Returns:
    [
        {
            "title": "Pembe Maize Meal 10Kg",
            "price_kes": 830.00,            
        }
    ]
    """

    soup = BeautifulSoup(html, "lxml")
    results = []

    # each product card has products-head + products-body nearby
    bodies = soup.find_all("div", class_="products-body")

    for body in bodies:
        try:
            # locate matching parent container
            parent = body.parent

            # ── title ─────────────────────────────────────
            title_tag = body.find("a", class_="products-title")

            if title_tag:
                title = (
                    title_tag.get("title")
                    or title_tag.get_text(strip=True)
                ).strip()
                href = title_tag.get("href", "")
            else:
                title = ""
                href = ""

            if not title:
                continue

            # ── price ─────────────────────────────────────
            price_tag = body.find(
                "span",
                class_="products-price-new"
            )

            if not price_tag:
                continue

            price_text = price_tag.get_text(" ", strip=True)

            m = re.search(
                r"([\d,]+(?:\.\d{1,2})?)",
                price_text
            )

            if not m:
                continue

            price = float(m.group(1).replace(",", ""))
            
            results.append({
                "title": title,
                "price_kes": price                
            })

        except Exception:
            continue

    # dedupe
    seen = set()
    final = []

    for item in results:
        key = (
            item["title"].lower(),
            item["price_kes"]
        )

        if key not in seen:
            seen.add(key)
            final.append(item)

    return final


# ─────────────────────────────────────────────────────────────────────────────
# TIER 1 — Per-item keyword search on Quickmart
# ─────────────────────────────────────────────────────────────────────────────

async def _search_item(client: httpx.AsyncClient, item: dict) -> dict:
    """
    Search Quickmart for a single basket item.
    Returns {item_name: [list of candidate products]}.

    URL format:  /products/search?keyword-{term}&pagesize-30
    Note: Quickmart uses dashes (keyword-X), NOT equals (keyword=X).
    """
    keyword = item["search_keyword"].replace(" ", "+")
    url = f"{SEARCH_URL}?keyword-{keyword}&pagesize-30"
        
    try:
        resp = await client.get(url)
        if resp.status_code != 200:
            logger.warning("[Search] %s → HTTP %s", item["label"], resp.status_code)
            return {item["name"]: []}
                        
        cards = _parse_product_cards(resp.text)        

        # Filter: at least one match_keyword must appear in title
        match_kws = item.get("match_keywords", [])
        relevant = [
            c for c in cards
            if any(kw.lower() in c["title"].lower() for kw in match_kws)
        ]

        logger.info(
            "[Search] %-20s → %d cards total, %d relevant",
            item["label"], len(cards), len(relevant)
        )            

        return {item["name"]: relevant}

    except Exception as e:
        logger.warning("[Search] %s failed: %s", item["label"], e)
        return {item["name"]: []}


async def _scrape_all_items(target_items: list[dict]) -> dict[str, list[dict]]:
    """
    Run per-item searches concurrently.
    Returns {item_name: [candidate products]}.
    """
    async with httpx.AsyncClient(
        headers=HEADERS,
        timeout=20.0,
        follow_redirects=True,
    ) as client:
        # First hit the branch page to set any session state
        try:
            await client.get(f"{QUICKMART_BASE}/{BRANCH_ID}")
        except Exception:
            pass  # not critical

        tasks = [_search_item(client, item) for item in target_items]
        results = await asyncio.gather(*tasks)

    combined: dict[str, list[dict]] = {}
    for r in results:
        combined.update(r)
    return combined


# ─────────────────────────────────────────────────────────────────────────────
# TIER 2 — AI picks best match from scraped candidates (per item)
# ─────────────────────────────────────────────────────────────────────────────

def _ai_pick_best_match(item: dict, candidates: list[dict]) -> float | None:
    """
    Ask AI to pick the best matching product for a basket item
    from the scraped candidates list.
    Returns the selected price or None.
    """
    if not candidates:
        return None

    candidate_text = "\n".join([
        f"  {i+1}. {c['title']} — KES {c['price_kes']}"
        for i, c in enumerate(candidates)
    ])

    prompt = f"""
        You are a Kenyan household cost tracker.

        BASKET ITEM: {item['label']} ({item['unit']})

        SCRAPED PRODUCTS FROM QUICKMART:
        {candidate_text}

        Pick the single best match for the basket item above.
        Rules:
        - Match the unit as closely as possible ({item['unit']})
        - Prefer the most common/affordable brand (not premium)
        - Ignore products that are clearly wrong (wrong item type)
        - If no good match, return null

        Return ONLY valid JSON:
        {{
        "selected_index": <1-based integer or null>,
        "price_kes": <float or null>,
        "reason": "<one line>"
        }}
    """
    try:
        data = call_ai(
            prompt,
            system_prompt="Return valid JSON only. No markdown. No explanation outside JSON.",
            max_tokens=150,
        )
        price = data.get("price_kes")
        reason = data.get("reason", "")
        if price and float(price) > 5:
            logger.info(
                "[AI Match] %-20s → KES %.2f  (%s)",
                item["label"], float(price), reason
            )
            return float(price)
    except Exception as e:
        logger.warning("[AI Match] %s failed: %s", item["label"], e)

    return None


# ─────────────────────────────────────────────────────────────────────────────
# TIER 3 — AI batch price fallback (for items with zero scrape results)
# ─────────────────────────────────────────────────────────────────────────────

async def _ai_batch_price_fallback(items: list[dict]) -> dict[str, float]:
    """
    One batched AI call for all items that returned zero search results.
    Returns {item_name: price_kes}.
    """
    if not items:
        return {}

    today = datetime.utcnow().strftime("%B %Y")
    items_text = "\n".join([
        f"  - {item['name']} | {item['label']} | {item['unit']}"
        for item in items
    ])

    prompt = f"""
        Current date: {today}
        Location: Nairobi, Kenya — Quickmart / Naivas supermarket retail prices

        Estimate the current KES retail price for each item:

        {items_text}

        Return ONLY valid JSON:
        {{
        "prices": {{
            "<item_name>": <float in KES>,
            ...
        }},
        "confidence": "high" | "medium" | "low"
        }}
    """
    try:
        data = call_ai(
            prompt,
            system_prompt="You are a Kenyan retail price expert. Return valid JSON only.",
            max_tokens=500,
        )
        raw = data.get("prices", {})
        result = {}
        for item in items:
            name = item["name"]
            if name in raw and raw[name]:
                result[name] = float(raw[name])
                logger.info("[AI Fallback] %-20s → KES %.2f", item["label"], result[name])
            else:
                logger.warning("[AI Fallback] No price for %s", item["label"])
        return result
    except Exception as e:
        logger.error("[AI Fallback] Batch call failed: %s", e)
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_food_basket(items: list[dict] | None = None) -> list[dict]:
    """
    Full pipeline:
      1. Search Quickmart for each item individually (concurrent)
      2. Pass candidates to AI for best-match selection (per item)
      3. Batch AI fallback for any item with zero search results
    """
    target_items = items or BASKET_ITEMS
    logger.info("Starting food basket fetch for %d items...", len(target_items))

    # ── Step 1: Scrape — per-item keyword search ──────────────────────────────
    search_results = await _scrape_all_items(target_items)

    # ── Step 2: AI match — pick best product from candidates ──────────────────
    final_prices: dict[str, float] = {}
    no_candidates: list[dict] = []

    for item in target_items:
        candidates = search_results.get(item["name"], [])                
        if candidates:
            price = _ai_pick_best_match(item, candidates)
            if price:
                final_prices[item["name"]] = price
            else:
                # AI rejected all candidates — treat as missed
                no_candidates.append(item)
        else:
            no_candidates.append(item)

    logger.info(
        "[Pipeline] Matched: %d | Needs fallback: %d",
        len(final_prices), len(no_candidates)
    )
    
    # ── Step 3: AI fallback for items with no usable candidates ───────────────
    if no_candidates:
        fallback_prices = await _ai_batch_price_fallback(no_candidates)
        final_prices.update(fallback_prices)

    # ── Assemble rows ─────────────────────────────────────────────────────────
    now = datetime.utcnow().isoformat()
    rows = []

    for item in target_items:
        name = item["name"]
        price = final_prices.get(name)

        if price is None:
            logger.error("No price resolved for %s — skipping row.", item["label"])
            continue

        had_candidates = bool(search_results.get(name))
        source   = f"quickmart.co.ke/products/search?keyword-{item['search_keyword'].replace(' ', '+')}&pagesize-30"
        retailer = "Quickmart"

        if name in [i["name"] for i in no_candidates]:
            source   = "AI_FALLBACK"
            retailer = "AI_ESTIMATE"

        rows.append({
            "name":       name,            
            "price_kes":  round(float(price), 2),
            "unit":       item["unit"],            
            "retailer":   retailer,
            "source":     source,            
        })

    logger.info("Food basket complete: %d/%d items resolved.", len(rows), len(target_items))
    return rows


async def store_food_basket(basket: list[dict]) -> None:
    """Insert fetched basket prices into Supabase food_basket table."""
    db = get_db()
    db.table("food_basket").insert(basket).execute()
    logger.info("Stored %d food basket items.", len(basket))


async def get_latest_basket() -> list[dict]:
    """Fetch most recent price per item from Supabase."""
    db = get_db()
    result = (
        db.table("food_basket")
        .select("*")
        .order("fetched_at", desc=True)
        .limit(len(BASKET_ITEMS) * 3)
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
    """Main entry point — fetch + store all basket prices."""
    basket = await fetch_food_basket(custom_items)
    await store_food_basket(basket)
    return basket