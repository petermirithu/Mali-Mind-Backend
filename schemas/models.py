from pydantic import BaseModel
from datetime import datetime
from typing import Optional


# ── Fuel ──────────────────────────────────────────────────────────────────────
class FuelPrice(BaseModel):
    id: Optional[int] = None
    petrol_per_litre: float
    diesel_per_litre: float
    kerosene_per_litre: float    
    source: str = "EPRA"
    location: str = "Nairobi"
    created_at: Optional[datetime] = None


# ── Forex ─────────────────────────────────────────────────────────────────────
class ForexRate(BaseModel):
    id: Optional[int] = None
    usd_kes: float
    eur_kes: Optional[float] = None
    gbp_kes: Optional[float] = None    
    source: str = "open_exchange_rates"
    created_at: Optional[datetime] = None


# ── Food Basket ───────────────────────────────────────────────────────────────
class FoodItem(BaseModel):
    id: Optional[int] = None
    name: str                      # e.g. "maize_flour", "sugar"
    price_kes: float
    unit: str                      # e.g. "2kg", "1kg", "1L"
    retailer: Optional[str] = None    
    source: Optional[str] = None
    created_at: Optional[datetime] = None


# ── AI Insight ────────────────────────────────────────────────────────────────
class AIInsight(BaseModel):
    id: Optional[int] = None
    trigger: str                   # e.g. "fuel_update", "forex_update"
    summary: str                   # 2-sentence household impact
    impact_score: float            # -1.0 (very negative) to +1.0 (very positive)
    affected_areas: list[str]      # e.g. ["transport", "food", "electricity"]    
    created_at: Optional[datetime] = None


# ── Dashboard response ────────────────────────────────────────────────────────
class DashboardResponse(BaseModel):
    fuel: Optional[FuelPrice]
    forex: Optional[ForexRate]
    food_basket: list[FoodItem]
    latest_insight: Optional[AIInsight]
    updated_at: datetime


# ── Impact response ───────────────────────────────────────────────────────────
class ImpactItem(BaseModel):
    category: str
    change_pct: float
    direction: str                 # "up" | "down" | "stable"
    monthly_estimate_kes: Optional[float]
    explanation: str


class ImpactResponse(BaseModel):
    items: list[ImpactItem]
    overall_score: float
    ai_summary: str
    computed_at: datetime


# ── Feed response ─────────────────────────────────────────────────────────────
class FeedItem(BaseModel):
    id: Optional[int] = None
    title: str
    what_happened: str
    why_it_happened: str
    what_it_means: str
    source_url: Optional[str] = None
    published_at: datetime
    created_at: Optional[datetime] = None