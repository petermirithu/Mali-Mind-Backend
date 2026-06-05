from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional


# ── Database Models ──────────────────────────────────────────────────────────────────────
class User(BaseModel):
    id: Optional[int] = None
    name: str
    email: str   
    uid: str
    is_verified: bool
    verification_code_hash: str
    verification_expires: datetime
    verification_attempts: int
    reset_password_token: str
    reset_password_expires: datetime
    updated_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    
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

class FeedItem(BaseModel):
    id: Optional[int] = None
    title: str
    what_happened: str
    why_it_happened: str
    what_it_means: str
    source_url: Optional[str] = None
    published_at: datetime
    created_at: Optional[datetime] = None

class UserImpactProfile(BaseModel):
    id: Optional[int] = None
    user_id: str
    income: int
    rent: int
    food_budget: int
    transport: str
    commute: int
    electricity: int
    water: int
    savings: int
    custom_categories: Optional[list[dict]] = None
    updated_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

class MonthlySpending(BaseModel):
    id: Optional[int] = None
    user_id: str
    month: str                     # ISO format date (2026-06-01)
    total_spending: float          # Total spending for the month
    transport_spending: float      # Transport category
    food_spending: float           # Food & groceries category
    utilities_spending: float      # Utilities category
    other_spending: Optional[float] = None  # Other categories
    change_pct_from_prev: float    # % change from previous month    
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

# ── Response Models ────────────────────────────────────────────────────────────────────
class ImpactResponse(BaseModel):
    items: list[ImpactItem]
    overall_score: float
    ai_summary: str
    computed_at: datetime

class ImpactCustomCategory(BaseModel):
    label: str
    value: str

class ImpactProfileRequest(BaseModel):
    user_id: int
    income: Optional[str] = None
    rent: Optional[str] = None
    food_budget: Optional[str] = None
    transport: Optional[str] = None
    commute: Optional[str] = None
    electricity: Optional[str] = None
    water: Optional[str] = None
    savings: Optional[str] = None
    custom_categories: Optional[list[ImpactCustomCategory]] = None

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


# ── Impact Page Response Models ─────────────────────────────────────────────────────────

class Recommendation(BaseModel):
    icon: str                      # e.g., "car", "shopping_cart", "lightning_bolt"
    text: str                      # recommendation text

class ComparisonBracket(BaseModel):
    label: str                     # e.g., "Low Impact", "Moderate Impact", "High Impact"
    range: str                     # e.g., "0 - 10%", "10 - 20%", "20% and above"
    color: str                     # e.g., "green", "orange", "red"

class ImpactCategoryBreakdown(BaseModel):
    category: str                  # "Transport", "Food & Groceries", "Utilities", "Other"
    icon: str                      # emoji or icon identifier
    monthly_amount_kes: float      # e.g., 1080
    change_pct: float              # e.g., 18.2
    direction: str                 # "up" | "down" | "stable"

class CustomCategoryAnalysis(BaseModel):
    """AI analysis of custom spending categories"""
    custom_item_name: str          # e.g., "WiFi", "Subscriptions"
    classified_category: str       # "Transport" | "Food & Groceries" | "Utilities" | "Other"
    monthly_cost: float            # Monthly cost in KES
    affected_by_fuel: bool         # True if fuel price changes impact this
    affected_by_forex: bool        # True if USD/KES changes impact this
    affected_by_food: bool         # True if food basket changes impact this
    estimated_impact_pct: float    # Estimated % impact from economic factors
    reasoning: str                 # AI explanation of categorization
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class CustomSpendingTracker(BaseModel):
    """Database model for tracking custom spending items and their impact"""
    id: Optional[int] = None
    user_id: str
    custom_item_name: str          # e.g., "WiFi", "Cooking Gas"
    classified_category: str       # Category determined by AI
    monthly_cost: float
    affected_by_fuel: bool
    affected_by_forex: bool
    affected_by_food: bool
    estimated_impact_pct: float
    ai_classification_reasoning: str
    current_month_impact_kes: Optional[float] = None  # Actual impact this month
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class UserProfileData(BaseModel):
    income: int                    # monthly income in KES
    rent: int                      # monthly rent in KES
    food_budget: int               # monthly food budget in KES
    transport: str                 # e.g., "Matatu", "Personal Car", "Bike"
    commute: int                   # daily commute distance in km
    electricity: int               # monthly electricity bill in KES
    water: int                     # monthly water bill in KES
    savings: Optional[int] = None  # monthly savings in KES
    custom_categories: Optional[list[CustomCategoryAnalysis]] = None  # AI-analyzed custom items

class MonthlySpendingChartData(BaseModel):
    month: str                     # ISO format date
    total_spending: float          # Total spending for the month

class FullImpactResponse(BaseModel):
    """Complete response for the impact page on mobile app"""
    
    # Current spending overview
    current_month_spending: float  # Total spending this month in KES
    spending_change_pct: float     # % change from last month (can be negative)
    spending_trend: str            # "up" | "down" | "stable"
    
    # User profile
    user_profile: UserProfileData
    
    # Impact breakdown by category
    impact_breakdown: list[ImpactCategoryBreakdown]
    
    # AI-generated insight
    ai_insight: str               # 2-sentence Mali Insight summary
    ai_insight_detail: str        # Longer explanation
    
    # Expected costs and recommendations
    expected_extra_cost_kes: float # Expected cost next month
    cost_range_min: float         # Range minimum
    cost_range_max: float         # Range maximum
    recommendations: list[Recommendation]
    
    # Past spending for chart
    past_6_months_spending: list[MonthlySpendingChartData] = []
                
    # Metadata
    computed_at: datetime    