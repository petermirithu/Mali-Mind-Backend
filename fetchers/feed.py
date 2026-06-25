from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from collections import Counter
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
        "headline inflation", "core inflation", "ppi", "consumer prices"
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
        "industry", "supply chain", "port", "logistics", "eac trade",
        "exporters", "importers", "shipping", "freight", "logistics cost", "logistics costs"
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
        "logistics costs", "commute cost", "fares", "matatu fares", "bus fare"
    ],
    "utilities": [
        "water tariff", "electricity bill", "utility cost", "power bill",
        "public service fee", "internet cost", "broadband cost"
    ],
}

CATEGORY_ALIASES = {
    "fuel": "fuel",
    "energy": "fuel",
    "forex": "forex",
    "fx": "forex",
    "currency": "forex",
    "food": "food",
    "agriculture": "food",
    "inflation": "inflation",
    "tax": "tax",
    "taxes": "tax",
    "cbk": "cbk",
    "banking": "banking",
    "banks": "banking",
    "capital markets": "capital_markets",
    "markets": "capital_markets",
    "trade": "trade_industry",
    "industry": "trade_industry",
    "real estate": "real_estate",
    "housing": "real_estate",
    "employment": "employment",
    "jobs": "employment",
    "salary": "employment",
    "sme": "smes_business",
    "business": "smes_business",
    "transport": "transport",
    "utilities": "utilities",
}

CATEGORY_PRIORITY_TERMS = {
    "fuel": ["fuel", "petrol", "diesel", "kerosene", "epra"],
    "forex": ["forex", "exchange rate", "shilling", "usd", "currency"],
    "food": ["food", "maize", "rice", "sugar", "fertilizer"],
    "inflation": ["inflation", "cpi", "cost of living", "consumer prices"],
    "tax": ["tax", "vat", "levy", "excise", "finance bill"],
    "cbk": ["cbk", "central bank", "interest rate", "mpr", "repo"],
    "banking": ["bank", "loan", "credit", "mortgage", "sacco"],
    "capital_markets": ["nse", "shares", "stock market", "bond market", "ipo"],
    "trade_industry": ["exports", "exporters", "imports", "shipping", "freight", "logistics", "port"],
    "real_estate": ["housing", "rent", "real estate", "construction", "property market"],
    "employment": ["employment", "unemployment", "jobs", "wages", "salary"],
    "smes_business": ["sme", "small business", "startup", "enterprise", "operating costs"],
    "transport": ["matatu", "fare", "fares", "transport cost", "commute cost"],
    "utilities": ["electricity bill", "water tariff", "power bill", "internet cost", "utility cost"],
}

MACRO_PRIORITY_CATEGORIES = ("inflation", "cbk", "tax", "forex")

NEWS_SOURCES: list[dict[str, str]] = [
    # {"name": "Kenyan Wall Street", "url": "https://kenyanwallstreet.com/"},
    # {"name": "Tuko Kenya", "url": "https://www.tuko.co.ke/kenya/"},
    # {"name": "Capital FM Business", "url": "https://www.capitalfm.co.ke/business"},
    # {"name": "Capital FM News", "url": "https://www.capitalfm.co.ke/news"},
    {"name": "Nation Africa", "url": "https://nation.africa/"},
    {"name": "The Standard", "url": "https://www.standardmedia.co.ke/"},
    {"name": "The Star", "url": "https://www.the-star.co.ke/"},
    {"name": "Citizen Digital", "url": "https://www.citizen.digital/"},
    {"name": "NTV Kenya", "url": "https://ntvkenya.co.ke/"},
    {"name": "K24 Digital", "url": "https://www.k24tv.co.ke/"},
    {"name": "KBC Digital", "url": "https://www.kbc.co.ke/"},
    {"name": "Kenyans.co.ke", "url": "https://www.kenyans.co.ke/"},
    {"name": "Tuko Kenya", "url": "https://www.tuko.co.ke/"},
    {"name": "People Daily", "url": "https://www.pd.co.ke/"},
    {"name": "Business Daily Africa", "url": "https://www.businessdailyafrica.com/"},
    {"name": "Kenyan Wall Street", "url": "https://kenyanwallstreet.com/"},
    {"name": "Capital FM Business", "url": "https://www.capitalfm.co.ke/business/"},
    {"name": "The Exchange Africa", "url": "https://theexchange.africa/"},
    {"name": "Tech-ish Kenya", "url": "https://tech-ish.com/"},
    {"name": "Techweez", "url": "https://techweez.com/"},
    {"name": "MyGov", "url": "https://mygov.go.ke/"},
    {"name": "Parliament of Kenya", "url": "https://www.parliament.go.ke/"},
    {"name": "Central Bank of Kenya", "url": "https://www.centralbank.go.ke/"},
    {"name": "Treasury Kenya", "url": "https://www.treasury.go.ke/"},
    {"name": "The Elephant", "url": "https://www.theelephant.info/"},
    {"name": "Africa Uncensored", "url": "https://africauncensored.online/"},
    {"name": "The Continent", "url": "https://thecontinent.org/"},
    {"name": "Mpasho", "url": "https://mpasho.co.ke/"},
    {"name": "Pulse Kenya", "url": "https://www.pulselive.co.ke/"},
    {"name": "Ghafla Kenya", "url": "https://www.ghafla.com/ke/"}

]

MAX_ITEMS_PER_SOURCE = 20
TOTAL_ITEM_LIMIT = 35
MAX_ARTICLE_FETCH_CONCURRENCY = 15

LISTING_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MaliBot/1.0; +https://example.com/bot)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

ARTICLE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MaliBot/1.0; +https://example.com/bot)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Strong signals can pass relevance by themselves; weak signals must appear in combination.
FINANCE_STRONG_TERMS = [
    "inflation", "cpi", "cbk", "central bank", "tax", "taxes", "vat", "levy",
    "finance bill", "treasury", "budget", "fiscal", "interest rate", "repo",
    "loan", "credit", "bank", "banking", "nse", "shares", "stock", "bond",
    "ipo", "forex", "exchange rate", "fx", "kes", "shilling", "usd", "fuel",
    "petrol", "diesel", "kerosene", "epra", "electricity tariff", "food prices",
    "cost of living", "exports", "imports", "trade balance", "manufacturing",
    "mortgage", "rent", "salary", "wages", "income", "employment", "unemployment",
    "public debt", "revenue", "excise", "duty", "treasury bill", "bond auction",
]

FINANCE_CONTEXT_TERMS = [
    "economy", "economic", "price", "prices", "pricing", "consumer", "household",
    "business", "market", "markets", "industry", "enterprise", "sme", "startup",
    "supply", "demand", "logistics", "transport cost", "utility cost", "power bill",
    "electricity", "water tariff", "internet cost", "broadband cost", "construction",
    "property", "housing", "agriculture", "fertilizer", "maize", "wheat", "rice",
    "sugar", "cash flow", "operating costs", "working capital",
]

LOW_SIGNAL_TERMS = [
    "business", "market", "markets", "price", "prices", "economic", "economy",
]

# Exclusion keywords to block non-financial stories
NON_FINANCE_EXCLUDE_TERMS = [
    "death", "deaths", "dead", "dies", "killed", "murder", "homicide",
    "accident", "crash", "rape", "assault", "robbery", "kidnap", "abduction",
    "crime", "police", "court case", "funeral", "burial", "obituary",
    "celebrity", "entertainment", "gossip", "relationship", "wedding",
    "football", "soccer", "sports", "match", "politics", "campaign rally",
    "concert", "musician", "actor", "actress", "movie", "series", "church",
    "sermon", "pastor", "student", "exam", "school", "university", "hospital",
    "weather", "flood", "rainfall", "accused", "arrested", "governor", "mp",
]

NON_FINANCE_PATTERNS = [
    re.compile(r"\b(man|woman|boy|girl|student|teacher|pastor|actor|musician)\b"),
    re.compile(r"\b(dies|killed|arrested|charged|weds|wedding|buried|funeral)\b"),
]

KENYA_PRIORITY_TERMS = [
    "kenya", "nairobi", "mombasa", "kisumu", "nakuru", "eldoret", "cbk", "kra",
    "kes", "shilling", "epra", "east africa", "kenyan",
]

GENERIC_FINANCE_FALLBACK = "general_finance"


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _contains_term(text: str, term: str) -> bool:
    if " " in term:
        return term in text
    return re.search(rf"\b{re.escape(term)}\b", text) is not None


def _count_keyword_hits(text: str, terms: list[str]) -> int:
    return sum(1 for term in terms if _contains_term(text, term))


def _weighted_keyword_score(text: str, terms: list[str]) -> int:
    score = 0
    for term in terms:
        if not _contains_term(text, term):
            continue
        score += 3 if " " in term else 2
    return score


def _category_keyword_score(category: str, title_text: str, summary_text: str = "") -> int:
    score = (_weighted_keyword_score(title_text, MALI_FEED_CATEGORIES[category]) * 2) + _weighted_keyword_score(
        summary_text, MALI_FEED_CATEGORIES[category]
    )

    for alias, mapped_category in CATEGORY_ALIASES.items():
        if mapped_category == category and (_contains_term(title_text, alias) or _contains_term(summary_text, alias)):
            score += 2

    priority_terms = CATEGORY_PRIORITY_TERMS.get(category, [])
    score += _weighted_keyword_score(title_text, priority_terms) * 2
    score += _weighted_keyword_score(summary_text, priority_terms)

    return score


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
    title_text = _normalize_text(title).lower()
    summary_text = _normalize_text(summary).lower()
    haystack = _normalize_text(f"{title} {summary}").lower()

    if not _is_finance_business_relevant(title, summary):
        return "other"

    category_scores = {
        category: _category_keyword_score(category, title_text, summary_text)
        for category in MALI_FEED_CATEGORIES
    }

    strongest_category, strongest_score = max(
        category_scores.items(), key=lambda item: item[1])

    for category in MACRO_PRIORITY_CATEGORIES:
        macro_score = category_scores[category]
        if macro_score < 4:
            continue

        has_title_anchor = any(
            _contains_term(title_text, term) for term in CATEGORY_PRIORITY_TERMS.get(category, [])
        )
        if has_title_anchor and macro_score >= strongest_score - 2:
            return category

    if strongest_score >= 4:
        return strongest_category

    positive_hits = _count_keyword_hits(
        haystack, FINANCE_STRONG_TERMS + FINANCE_CONTEXT_TERMS)
    if strongest_score >= 2 and positive_hits >= 2:
        return strongest_category

    if _is_finance_business_relevant(title, summary):
        return GENERIC_FINANCE_FALLBACK

    return "other"


def _is_kenya_relevant(title: str, summary: str = "") -> bool:
    text = _normalize_text(f"{title} {summary}").lower()
    return any(_contains_term(text, term) for term in KENYA_PRIORITY_TERMS)


def _is_finance_business_relevant(title: str, summary: str = "") -> bool:
    text = _normalize_text(f"{title} {summary}").lower()

    # Drop obvious non-financial stories first
    if any(_contains_term(text, term) for term in NON_FINANCE_EXCLUDE_TERMS):
        return False
    if any(pattern.search(text) for pattern in NON_FINANCE_PATTERNS):
        return False

    category_signal = max(
        _weighted_keyword_score(text, keywords) for keywords in MALI_FEED_CATEGORIES.values()
    )
    if category_signal >= 4:
        return True

    strong_hits = _count_keyword_hits(text, FINANCE_STRONG_TERMS)
    context_hits = _count_keyword_hits(text, FINANCE_CONTEXT_TERMS)
    low_signal_hits = _count_keyword_hits(text, LOW_SIGNAL_TERMS)

    if strong_hits >= 1:
        return True
    if context_hits >= 2:
        return True
    if context_hits >= 1 and low_signal_hits >= 2:
        return True

    return False


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
    bad_tokens = ["/tag/", "/tags/", "/category/",
                  "/author/", "/video/", "/photos/"]
    if any(tok in path for tok in bad_tokens):
        return False
    return len(path.strip("/").split("/")) >= 2


def _extract_listing_candidates(html: str, source: dict[str, str]) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    base_url = source["url"]
    source_name = source["name"]
    candidates: list[dict[str, Any]] = []
    seen_links: set[str] = set()
    category_histogram: Counter[str] = Counter()

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    headline_selectors = ["h1 a", "h2 a", "h3 a",
                          "article a", "a.headline", "a.title"]

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

        # Early filter at listing stage to reduce bad candidates.
        if not _is_finance_business_relevant(title):
            continue

        category = _category_from_text(title)
        if category == "other":
            continue

        seen_links.add(href)
        category_histogram[category] += 1
        candidates.append(
            {
                "title": title,
                "link": href,
                "description": "",
                "published_at": datetime.now(timezone.utc),
                "source_name": source_name,
                "category_hint": category,
            }
        )

        if len(candidates) >= MAX_ITEMS_PER_SOURCE * 3:
            break

    if not candidates:
        return []

    dominant_categories = {category for category,
                           _ in category_histogram.most_common(4)}
    curated_candidates = [
        candidate
        for candidate in candidates
        if candidate["category_hint"] in dominant_categories or candidate["category_hint"] == GENERIC_FINANCE_FALLBACK
    ]

    return curated_candidates[: MAX_ITEMS_PER_SOURCE * 3]


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
                published_at = _try_parse_iso_datetime(
                    meta["content"]) or _safe_parse_date(meta["content"])
                if published_at:
                    break

    if not description:
        paragraphs = soup.find_all("p")
        joined = " ".join(_normalize_text(p.get_text(" ", strip=True))
                          for p in paragraphs[:4])
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
            description = extracted["description"] or candidate.get(
                "description", "")

            # Final strict filter using richer article text
            if not _is_finance_business_relevant(title, description):
                return None

            return {
                "title": _normalize_text(title),
                "link": candidate["link"],
                "description": _normalize_text(description),
                "published_at": extracted["published_at"],
                "source_name": candidate["source_name"],
                "category_hint": candidate.get("category_hint"),
            }
        except Exception as exc:
            logger.warning("Failed to fetch article details %s: %s",
                           candidate.get("link"), exc)
            return None


async def _fetch_source(client: httpx.AsyncClient, source: dict[str, str]) -> list[dict[str, Any]]:
    source_url = source["url"]
    source_name = source["name"]

    try:
        resp = await client.get(source_url, timeout=20.0, follow_redirects=True, headers=LISTING_HEADERS)
        resp.raise_for_status()
        candidates = _extract_listing_candidates(resp.text, source)
        if not candidates:
            logger.warning(
                "No listing candidates extracted for %s (%s)", source_name, source_url)
            return []

        semaphore = asyncio.Semaphore(MAX_ARTICLE_FETCH_CONCURRENCY)
        detail_tasks = [_fetch_article_details(
            client, semaphore, c) for c in candidates]
        detail_results = await asyncio.gather(*detail_tasks)

        items = [i for i in detail_results if i and i.get("title")]
        return items[:MAX_ITEMS_PER_SOURCE]
    except Exception as exc:
        logger.warning("Failed to fetch source %s (%s): %s",
                       source_name, source_url, exc)
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
        ai_out = call_ai(
            user_prompt, system_prompt=system_prompt, max_tokens=350)

        what_happened = _normalize_text(str(ai_out.get("what_happened", "")))
        why_it_happened = _normalize_text(
            str(ai_out.get("why_it_happened", "")))
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

    categories_to_refresh = sorted(
        {
            str(item.get("category", "")).strip()
            for item in items
            if str(item.get("category", "")).strip()
        }
    )

    for category in categories_to_refresh:
        db.table("feed_items").delete().eq("category", category).execute()

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

        dedupe_hash = _hash_for_dedupe(
            title, item.get("link"), item["published_at"])
        if dedupe_hash in seen_hashes:
            continue
        seen_hashes.add(dedupe_hash)

        category = _category_from_text(title, desc)
        if category == GENERIC_FINANCE_FALLBACK and item.get("category_hint"):
            hinted_category = str(item["category_hint"])
            if hinted_category in MALI_FEED_CATEGORIES:
                category = hinted_category

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
        category_counts[it["category"]] = category_counts.get(
            it["category"], 0) + 1

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
