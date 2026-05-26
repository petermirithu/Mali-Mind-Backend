from pydantic import BaseModel
from datetime import datetime
from typing import Optional


# ── Database Models ──────────────────────────────────────────────────────────────────────
class FuelPrice(BaseModel):
    id: Optional[int] = None
    petrol_per_litre: float
    diesel_per_litre: float
    kerosene_per_litre: float    
    source: str = "EPRA"
    location: str = "Nairobi"
    created_at: Optional[datetime] = None

class ForexRate(BaseModel):
    id: Optional[int] = None
    usd_kes: float
    eur_kes: Optional[float] = None
    gbp_kes: Optional[float] = None    
    source: str = "open_exchange_rates"
    created_at: Optional[datetime] = None

class FoodItem(BaseModel):
    id: Optional[int] = None
    maize_flour: float
    wheat_flour: float
    rice: float
    sugar: float
    cooking_oil: float
    milk: float
    eggs: float
    bread: float
    tomatoes: float
    onions: float
    created_at: Optional[datetime] = None

class AIInsight(BaseModel):
    id: Optional[int] = None
    trigger: str                   # e.g. "fuel_update", "forex_update"
    summary: str                   # 2-sentence household impact
    impact_score: float            # -1.0 (very negative) to +1.0 (very positive)
    affected_areas: list[str]      # e.g. ["transport", "food", "electricity"]    
    created_at: Optional[datetime] = None

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

class FeedItem(BaseModel):
    id: Optional[int] = None
    title: str
    what_happened: str
    why_it_happened: str
    what_it_means: str
    source_url: Optional[str] = None
    published_at: datetime
    created_at: Optional[datetime] = None

# ── Response Models ────────────────────────────────────────────────────────────────────
class TrendInfo(BaseModel):
    trend_str: str                 # e.g., "↑ 2.5%"
    direction: str                 # "up" | "down" | "stable"
    percent: float                 # percentage change


class FuelTrendResponse(BaseModel):
    petrol_per_litre: float
    petrol_trend: TrendInfo
    diesel_per_litre: float
    diesel_trend: TrendInfo
    kerosene_per_litre: float
    kerosene_trend: TrendInfo
    source: str = "EPRA"
    location: str = "Nairobi"
    created_at: Optional[datetime] = None

class ForexTrendResponse(BaseModel):
    usd_kes: float
    usd_kes_trend: TrendInfo
    eur_kes: Optional[float] = None
    eur_kes_trend: Optional[TrendInfo] = None
    gbp_kes: Optional[float] = None
    gbp_kes_trend: Optional[TrendInfo] = None
    source: str = "open_exchange_rates"
    created_at: Optional[datetime] = None

class FoodBasketTrendResponse(BaseModel):
    maize_flour: float
    maize_flour_trend: TrendInfo
    wheat_flour: float
    wheat_flour_trend: TrendInfo
    rice: float
    rice_trend: TrendInfo
    sugar: float
    sugar_trend: TrendInfo
    cooking_oil: float
    cooking_oil_trend: TrendInfo
    milk: float
    milk_trend: TrendInfo
    eggs: float
    eggs_trend: TrendInfo
    bread: float
    bread_trend: TrendInfo
    tomatoes: float
    tomatoes_trend: TrendInfo
    onions: float
    onions_trend: TrendInfo
    created_at: Optional[datetime] = None

class HighImpactDriver(BaseModel):
    category: str                  # "fuel" | "forex" | "food"
    item: str                      # e.g., "petrol_per_litre", "usd_kes", "maize_flour"
    pct_change: float              # percentage change
    direction: str                 # "up" | "down" | "stable"


class WeeklyDataPoint(BaseModel):
    week_start: datetime           # start date of the week
    avg_pct: float                 # average percentage change for that week


class OverallChangeMetrics(BaseModel):
    fuel_avg_pct: float            # average % change across all fuel types
    forex_avg_pct: float           # average % change across all forex rates
    food_avg_pct: float            # average % change across all food items
    overall_avg_pct: float         # combined average across all categories
    overall_trend: TrendInfo       # trend comparing this week to last week
    high_impact_drivers: list[HighImpactDriver]  # top drivers of change
    weekly_chart_data: list[WeeklyDataPoint]  # historical weekly averages


class DashboardResponse(BaseModel):
    fuel: Optional[FuelTrendResponse]
    forex: Optional[ForexTrendResponse]
    food_basket: Optional[FoodBasketTrendResponse]
    latest_insight: Optional[list[AIInsight]]
    overall_metrics: Optional[OverallChangeMetrics]    