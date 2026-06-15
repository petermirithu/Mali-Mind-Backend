from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin, urlparse
import httpx
from bs4 import BeautifulSoup
from ai.core import call_ai
from db.client import get_db

logger = logging.getLogger(__name__)

# Expanded financial categories to reduce "macro_economy" fallback
MALI_FEED_CATEGORIES = {
    "fuel": [
        "fuel", "petrol", "diesel", "kerosene", "epra", "oil", "crude",
        "energy prices", "lpg", "electricity tariff", "power cost"
    ],
    "forex": [
        "forex", "currency", "exchange rate", "kes", "usd", "euro", "pound",
        "dollar", "cbk rate", "fx reserves", "shilling"
    ],
    "food": [
        "food", "maize", "wheat", "rice", "sugar", "agriculture",
        "farm-gate", "fertilizer", "produce prices", "food inflation"
    ],
    "inflation": [
        "inflation", "cpi", "consumer price", "cost of living",
        "headline inflation", "core inflation", "ppi"
    ],
    "tax": [
        "tax", "vat", "levy", "finance bill", "kra", "duty", "excise",
        "fiscal policy", "revenue", "public debt", "budget statement"
    ],
    "cbk": [
        "cbk", "central bank", "monetary policy", "mpr",
        "interest rate", "repo", "liquidity", "treasury bill", "bond auction"
    ],
    "banking": [
        "bank", "lending", "loan", "credit", "npl", "mortgage",
        "sacco", "deposit rate", "base rate", "microfinance"
    ],
    "capital_markets": [
        "nse", "shares", "equity", "stock market", "bond market",
        "ipo", "investor", "dividend", "market cap", "securities"
    ],
    "trade_industry": [
        "exports", "imports", "trade balance", "manufacturing",
        "industry", "supply chain", "port", "logistics", "eac trade"
    ],
    "real_estate": [
        "real estate", "housing", "rent", "construction",
        "mortgage rates", "land rates", "property market"
    ],
    "employment": [
        "wages", "salary", "income", "jobs", "employment",
        "unemployment", "payroll", "labour market"
    ],
    "smes_business": [
        "sme", "small business", "startup", "business climate",
        "operating costs", "working capital", "enterprise"
    ],
    "transport": [
        "transport cost", "matatu", "fare", "freight", "shipping cost",
        "logistics costs", "commute cost"
    ],
    "utilities": [
        "water tariff", "electricity bill", "utility cost", "power bill",
        "public service fee", "internet cost", "broadband cost"
    ],
}

NEWS_SOURCES: list[dict[str, str]] = [
    {"name": "Kenyan Wall Street", "url": "https://kenyanwallstreet.com/"},
    {"name": "Tuko Kenya", "url": "https://www.tuko.co.ke/kenya/"},
    {"name": "Capital FM Business", "url": "https://www.capitalfm.co.ke/business"},
    {"name": "Capital FM News", "url": "https://www.capitalfm.co.ke/news"},
    {"name": "Kenyans.co.ke", "url": "https://www.kenyans.co.ke/news"},
]

MAX_ITEMS_PER_SOURCE = 15
TOTAL_ITEM_LIMIT = 25
MAX_ARTICLE_FETCH_CONCURRENCY = 8

LISTING_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MaliMindBot/1.0; +https://example.com/bot)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

ARTICLE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MaliMindBot/1.0; +https://example.com/bot)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Positive financial/economic keywords
FINANCE_INCLUDE_TERMS = [
    "economy", "economic", "business", "market", "markets", "price", "prices",
    "inflation", "cpi", "cbk", "central bank", "tax", "taxes", "vat", "levy",
    "finance bill", "treasury", "budget", "fiscal", "interest rate", "loan",
    "credit", "bank", "banking", "nse", "shares", "stock", "bond", "ipo",
    "forex", "exchange rate", "kes", "shilling", "usd", "fuel", "petrol",
    "diesel", "energy", "electricity tariff", "food prices", "cost of living",
    "trade", "exports", "imports", "manufacturing", "sme", "startup",
    "rent", "housing", "mortgage", "employment", "wages", "salary", "income"
]

# Exclusion keywords to block non-financial stories
NON_FINANCE_EXCLUDE_TERMS = [
    "death", "deaths", "dead", "dies", "killed", "murder", "homicide",
    "accident", "crash", "rape", "assault", "robbery", "kidnap", "abduction",
    "crime", "police", "court case", "funeral", "burial", "obituary",
    "celebrity", "entertainment", "gossip", "relationship", "wedding",
    "football", "soccer", "sports", "match", "politics", "campaign rally"
]


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _safe_parse_date(date_str: str | None) -> datetime:
    if not date_str:
        return datetime.now(timezone.utc)
    try:
        parsed = parsedate_to_datetime(date_str)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _try_parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _category_from_text(title: str, summary: str = "") -> str:
    haystack = f"{title} {summary}".lower()
    for category, keywords in MALI_FEED_CATEGORIES.items():
        if any(k in haystack for k in keywords):
            return category

    # Better fallback for financial-but-unclear items
    if _is_finance_business_relevant(title, summary):
        return "general_finance"

    return "other"


def _is_kenya_relevant(title: str, summary: str = "") -> bool:
    text = f"{title} {summary}".lower()
    kenya_terms = ["kenya", "nairobi", "cbk", "kra", "kes", "shilling", "epra", "east africa"]
    return any(term in text for term in kenya_terms)


def _is_finance_business_relevant(title: str, summary: str = "") -> bool:
    text = f"{title} {summary}".lower()

    # Drop obvious non-financial stories first
    if any(term in text for term in NON_FINANCE_EXCLUDE_TERMS):
        return False

    # Require at least one finance/econ signal
    return any(term in text for term in FINANCE_INCLUDE_TERMS)


def _hash_for_dedupe(title: str, source_url: str | None, published_at: datetime) -> str:
    raw = f"{title}|{source_url or ''}|{published_at.isoformat()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _clean_url(base_url: str, href: str | None) -> str | None:
    if not href:
        return None
    href = href.strip()
    if not href or href.startswith("#") or href.lower().startswith("javascript:"):
        return None
    return urljoin(base_url, href)


def _looks_like_article_link(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()
    bad_tokens = ["/tag/", "/tags/", "/category/", "/author/", "/video/", "/photos/"]
    if any(tok in path for tok in bad_tokens):
        return False
    return len(path.strip("/").split("/")) >= 2


def _extract_listing_candidates(html: str, source: dict[str, str]) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    base_url = source["url"]
    source_name = source["name"]
    candidates: list[dict[str, Any]] = []
    seen_links: set[str] = set()

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    headline_selectors = ["h1 a", "h2 a", "h3 a", "article a", "a.headline", "a.title"]

    anchors: list[Any] = []
    for sel in headline_selectors:
        anchors.extend(soup.select(sel))

    if len(anchors) < 10:
        anchors.extend(soup.find_all("a"))

    for a in anchors:
        title = _normalize_text(a.get_text(" ", strip=True))
        href = _clean_url(base_url, a.get("href"))
        if not title or not href:
            continue
        if len(title) < 18:
            continue
        if href in seen_links:
            continue
        if not _looks_like_article_link(href):
            continue

        # Early filter at listing stage to reduce bad candidates
        if not _is_finance_business_relevant(title):
            continue

        seen_links.add(href)
        candidates.append(
            {
                "title": title,
                "link": href,
                "description": "",
                "published_at": datetime.now(timezone.utc),
                "source_name": source_name,
            }
        )

        if len(candidates) >= MAX_ITEMS_PER_SOURCE * 3:
            break

    return candidates


def _extract_article_content(html: str, url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    title = ""
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = _normalize_text(og_title["content"])
    if not title and soup.title and soup.title.string:
        title = _normalize_text(soup.title.string)
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = _normalize_text(h1.get_text(" ", strip=True))

    description = ""
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        description = _normalize_text(meta_desc["content"])
    if not description:
        og_desc = soup.find("meta", property="og:description")
        if og_desc and og_desc.get("content"):
            description = _normalize_text(og_desc["content"])

    published_at = None
    time_tag = soup.find("time")
    if time_tag:
        published_at = _try_parse_iso_datetime(time_tag.get("datetime")) or _safe_parse_date(
            time_tag.get_text(" ", strip=True)
        )

    if not published_at:
        for attr in [
            ("property", "article:published_time"),
            ("name", "article:published_time"),
            ("name", "pubdate"),
            ("name", "publishdate"),
            ("name", "date"),
            ("itemprop", "datePublished"),
        ]:
            meta = soup.find("meta", attrs={attr[0]: attr[1]})
            if meta and meta.get("content"):
                published_at = _try_parse_iso_datetime(meta["content"]) or _safe_parse_date(meta["content"])
                if published_at:
                    break

    if not description:
        paragraphs = soup.find_all("p")
        joined = " ".join(_normalize_text(p.get_text(" ", strip=True)) for p in paragraphs[:4])
        description = _normalize_text(joined)[:450]

    return {
        "title": title,
        "description": description,
        "published_at": published_at or datetime.now(timezone.utc),
        "link": url,
    }


async def _fetch_article_details(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    candidate: dict[str, Any],
) -> dict[str, Any] | None:
    async with semaphore:
        try:
            resp = await client.get(candidate["link"], timeout=20.0, follow_redirects=True, headers=ARTICLE_HEADERS)
            resp.raise_for_status()
            extracted = _extract_article_content(resp.text, candidate["link"])
            title = extracted["title"] or candidate["title"]
            description = extracted["description"] or candidate.get("description", "")

            # Final strict filter using richer article text
            if not _is_finance_business_relevant(title, description):
                return None

            return {
                "title": _normalize_text(title),
                "link": candidate["link"],
                "description": _normalize_text(description),
                "published_at": extracted["published_at"],
                "source_name": candidate["source_name"],
            }
        except Exception as exc:
            logger.warning("Failed to fetch article details %s: %s", candidate.get("link"), exc)
            return None


async def _fetch_source(client: httpx.AsyncClient, source: dict[str, str]) -> list[dict[str, Any]]:
    source_url = source["url"]
    source_name = source["name"]

    try:
        resp = await client.get(source_url, timeout=20.0, follow_redirects=True, headers=LISTING_HEADERS)
        resp.raise_for_status()
        candidates = _extract_listing_candidates(resp.text, source)
        if not candidates:
            logger.warning("No listing candidates extracted for %s (%s)", source_name, source_url)
            return []

        semaphore = asyncio.Semaphore(MAX_ARTICLE_FETCH_CONCURRENCY)
        detail_tasks = [_fetch_article_details(client, semaphore, c) for c in candidates]
        detail_results = await asyncio.gather(*detail_tasks)

        items = [i for i in detail_results if i and i.get("title")]
        return items[:MAX_ITEMS_PER_SOURCE]
    except Exception as exc:
        logger.warning("Failed to fetch source %s (%s): %s", source_name, source_url, exc)
        return []


def _ai_enrich_item(raw_item: dict[str, Any], category: str) -> dict[str, str]:
    title = raw_item["title"]
    description = raw_item.get("description", "")

    system_prompt = """
You are Mali, a Kenyan financial intelligence assistant.
Return STRICT JSON ONLY with keys:
- what_happened (max 45 words)
- why_it_happened (max 55 words)
- what_it_means (max 60 words)

Rules:
- Focus only on economics/business impact in Kenya.
- Ignore politics/crime/celebrity framing unless directly tied to prices, income, taxes, FX, or business costs.
- Be concrete, plain language, and non-hyped.
- Do not include markdown or extra keys.
"""

    user_prompt = f"""
Category: {category}
Headline: {title}
Snippet: {description}

Create the three fields now.
"""

    try:
        ai_out = call_ai(user_prompt, system_prompt=system_prompt, max_tokens=350)

        what_happened = _normalize_text(str(ai_out.get("what_happened", "")))
        why_it_happened = _normalize_text(str(ai_out.get("why_it_happened", "")))
        what_it_means = _normalize_text(str(ai_out.get("what_it_means", "")))

        if what_happened and why_it_happened and what_it_means:
            return {
                "what_happened": what_happened,
                "why_it_happened": why_it_happened,
                "what_it_means": what_it_means,
            }
    except Exception as exc:
        logger.warning("AI enrichment failed for title '%s': %s", title, exc)

    fallback_base = _normalize_text(description or title)
    return {
        "what_happened": fallback_base[:220] or title,
        "why_it_happened": "Likely driven by market, policy, or supply-demand changes affecting Kenya's economy.",
        "what_it_means": "This may influence household budgets, business operating costs, or cash-flow planning.",
    }


def _db_insert_feed_items(items: list[dict[str, Any]]) -> int:
    if not items:
        return 0

    db = get_db()
    db.table("feed_items").delete().gt("id", 0).execute()

    inserted = 0
    for item in items:
        payload = {
            "title": item["title"],
            "category": item["category"],
            "what_happened": item["what_happened"],
            "why_it_happened": item["why_it_happened"],
            "what_it_means": item["what_it_means"],
            "source_url": item.get("source_url"),
            "published_at": item["published_at"].isoformat(),
        }
        db.table("feed_items").insert(payload).execute()
        inserted += 1

    return inserted


async def run_feed_fetcher() -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        tasks = [_fetch_source(client, source) for source in NEWS_SOURCES]
        source_results = await asyncio.gather(*tasks)

    raw_items = [item for batch in source_results for item in batch]

    seen_hashes: set[str] = set()
    filtered: list[dict[str, Any]] = []

    for item in raw_items:
        title = item["title"]
        desc = item.get("description", "")

        if not _is_kenya_relevant(title, desc):
            continue
        if not _is_finance_business_relevant(title, desc):
            continue

        dedupe_hash = _hash_for_dedupe(title, item.get("link"), item["published_at"])
        if dedupe_hash in seen_hashes:
            continue
        seen_hashes.add(dedupe_hash)

        category = _category_from_text(title, desc)

        # Hard guard: skip non-finance fallback classes
        if category == "other":
            continue

        enriched = _ai_enrich_item(item, category)

        filtered.append(
            {
                "title": title,
                "category": category,
                "what_happened": enriched["what_happened"],
                "why_it_happened": enriched["why_it_happened"],
                "what_it_means": enriched["what_it_means"],
                "source_url": item.get("link"),
                "published_at": item["published_at"],
            }
        )

        if len(filtered) >= TOTAL_ITEM_LIMIT:
            break

    inserted_count = _db_insert_feed_items(filtered)

    category_counts: dict[str, int] = {}
    for it in filtered:
        category_counts[it["category"]] = category_counts.get(it["category"], 0) + 1

    result = {
        "status": "ok",
        "fetched": len(raw_items),
        "processed": len(filtered),
        "inserted": inserted_count,
        "category_counts": category_counts,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    logger.info("Feed fetcher result: %s", json.dumps(result))
    return result