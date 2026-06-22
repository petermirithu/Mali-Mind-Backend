from pydantic import BaseModel
from realtime import Optional
from db.client import get_db
from ai.insights import generate_insight
from ai.categorization import CustomCategoryClassifier
from datetime import datetime, timedelta


class ImpactItem(BaseModel):
    category: str
    change_pct: float
    direction: str                 # "up" | "down" | "stable"
    monthly_estimate_kes: Optional[float]
    explanation: str


class ImpactCustomCategory(BaseModel):
    label: str
    value: str


class ImpactResponse(BaseModel):
    items: list[ImpactItem]
    overall_score: float
    ai_summary: str
    computed_at: datetime


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


class CustomCategoryAnalysis(BaseModel):
    """AI analysis of custom spending categories"""
    custom_item_name: str          # e.g., "WiFi", "Subscriptions"
    # "Transport" | "Food & Groceries" | "Utilities" | "Other"
    classified_category: str
    monthly_cost: float            # Monthly cost in KES
    affected_by_fuel: bool         # True if fuel price changes impact this
    affected_by_forex: bool        # True if USD/KES changes impact this
    affected_by_food: bool         # True if food basket changes impact this
    estimated_impact_pct: float    # Estimated % impact from economic factors
    reasoning: str                 # AI explanation of categorization
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class UserImpactProfileData(BaseModel):
    income: int                    # monthly income in KES
    rent: int                      # monthly rent in KES
    food_budget: int               # monthly food budget in KES
    transport: str                 # e.g., "Matatu", "Personal Car", "Bike"
    commute: int                   # daily commute distance in km
    electricity: int               # monthly electricity bill in KES
    water: int                     # monthly water bill in KES
    savings: Optional[int] = None  # monthly savings in KES
    # AI-analyzed custom items
    custom_categories: Optional[list[CustomCategoryAnalysis]] = None


class MonthlySpendingChartData(BaseModel):
    month: str                     # ISO format date
    total_spending: float          # Total spending for the month


class ImpactCategoryBreakdown(BaseModel):
    category: str                  # "Transport", "Food & Groceries", "Utilities", "Other"
    icon: str                      # emoji or icon identifier
    monthly_amount_kes: float      # e.g., 1080
    change_pct: float              # e.g., 18.2
    direction: str                 # "up" | "down" | "stable"


class Recommendation(BaseModel):
    icon: str                      # e.g., "car", "shopping_cart", "lightning_bolt"
    text: str                      # recommendation text


class FullImpactResponse(BaseModel):
    """Complete response for the impact page on mobile app"""

    # Current spending overview
    current_month_spending: float  # Total spending this month in KES
    spending_change_pct: float     # % change from last month (can be negative)
    spending_trend: str            # "up" | "down" | "stable"
    total_monthly_deductions: float  # Spending + savings set aside this month
    money_left_this_month: float   # Income minus deductions (can be negative)
    savings_utilization_pct: float  # How much of income is allocated to savings

    # User profile
    user_impact_profile: UserImpactProfileData

    # Impact breakdown by category
    impact_breakdown: list[ImpactCategoryBreakdown]

    # AI-generated insight
    ai_insight: str               # 2-sentence Mali Insight summary
    ai_insight_detail: str        # Longer explanation

    # Expected costs and recommendations
    expected_extra_cost_kes: float  # Expected cost next month
    cost_range_min: float         # Range minimum
    cost_range_max: float         # Range maximum
    recommendations: list[Recommendation]

    # Past spending for chart
    past_6_months_spending: list[MonthlySpendingChartData] = []

    # Metadata
    computed_at: datetime


class ImpactService:
    @staticmethod
    async def get_impact_data():
        """
        Computes impact of latest price changes on a Kenyan household.
        Powers the Impact Page on mobile.
        """
        db = get_db()

        try:
            # Get 2 latest fuel records to compute change
            fuel_res = db.table("fuel_prices").select(
                "*").order("created_at", desc=True).limit(2).execute()
            fuel_data = fuel_res.data

            # Get 2 latest forex records
            forex_res = db.table("forex_rates").select(
                "*").order("created_at", desc=True).limit(2).execute()
            forex_data = forex_res.data

            items: list[ImpactItem] = []
            data_for_ai = {}

            # ── Fuel Impact ───────────────────────────────────────────────────────
            if len(fuel_data) >= 2:
                curr_petrol = fuel_data[0]["petrol_per_litre"]
                prev_petrol = fuel_data[1]["petrol_per_litre"]
                pct = ImpactService.compute_change_pct(
                    curr_petrol, prev_petrol)
                direction = "up" if pct > 0 else (
                    "down" if pct < 0 else "stable")
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
                data_for_ai["fuel"] = {"current": curr_petrol,
                                       "previous": prev_petrol, "change_pct": pct}

            # ── Forex Impact ──────────────────────────────────────────────────────
            if len(forex_data) >= 2:
                curr_usd = forex_data[0]["usd_kes"]
                prev_usd = forex_data[1]["usd_kes"]
                pct = ImpactService.compute_change_pct(curr_usd, prev_usd)
                direction = "up" if pct > 0 else (
                    "down" if pct < 0 else "stable")

                items.append(ImpactItem(
                    category="Imports / USD Rate",
                    change_pct=pct,
                    direction=direction,
                    monthly_estimate_kes=None,
                    explanation=f"USD/KES is {curr_usd} ({'+' if pct > 0 else ''}{pct}%). "
                                f"Imported goods (electronics, fuel, medicine) will likely "
                                f"{'cost more' if pct > 0 else 'become cheaper'}.",
                ))
                data_for_ai["forex"] = {"current": curr_usd,
                                        "previous": prev_usd, "change_pct": pct}

            # ── AI Summary ────────────────────────────────────────────────────────
            ai_insight = await generate_insight("impact_request", data_for_ai)
            overall_score = ai_insight.get("impact_score", 0.0)

            return {
                "items": items,
                "overall_score": overall_score,
                "ai_summary": ai_insight["summary"],
                "computed_at": datetime.utcnow()
            }

        except Exception as e:
            raise Exception(f"Error computing impact data: {str(e)}")

    @staticmethod
    def compute_change_pct(current: float, previous: float) -> float:
        if previous == 0:
            return 0.0
        return round(((current - previous) / previous) * 100, 2)

    @staticmethod
    async def save_impact_profile_items(profile: ImpactProfileRequest):
        """
        Saves incoming user impact profile data.
        - Upserts user_impact_profiles (update first, insert if missing)
        - Classifies custom categories with AI
        - Persists custom categories into custom_spending_tracker
        """
        try:
            db = get_db()

            profile_dict = profile.model_dump()
            user_id = profile.user_id
            custom_categories = profile_dict.get("custom_categories") or []

            now_iso = datetime.utcnow().isoformat()

            # 1) Upsert profile (update-first strategy)
            profile_update_payload = {
                "income": profile_dict.get("income"),
                "rent": profile_dict.get("rent"),
                "food_budget": profile_dict.get("food_budget"),
                "transport": profile_dict.get("transport"),
                "commute": profile_dict.get("commute"),
                "electricity": profile_dict.get("electricity"),
                "water": profile_dict.get("water"),
                "savings": profile_dict.get("savings"),
                "custom_categories": custom_categories,
                "updated_at": now_iso,
            }
            profile_update_payload = {
                k: v for k, v in profile_update_payload.items() if v is not None}

            update_res = (
                db.table("user_impact_profiles")
                .update(profile_update_payload)
                .eq("user_id", user_id)
                .execute()
            )

            if not update_res.data:
                insert_payload = {
                    "user_id": user_id,
                    "income": profile_dict.get("income") or 0,
                    "rent": profile_dict.get("rent") or 0,
                    "food_budget": profile_dict.get("food_budget") or 0,
                    "transport": profile_dict.get("transport") or "N/A",
                    "commute": profile_dict.get("commute") or 0,
                    "electricity": profile_dict.get("electricity") or 0,
                    "water": profile_dict.get("water") or 0,
                    "savings": profile_dict.get("savings") or 0,
                    "custom_categories": custom_categories,
                    "created_at": now_iso,
                    "updated_at": now_iso,
                }
                db.table("user_impact_profiles").insert(
                    insert_payload).execute()

            # 2) Mark existing custom tracker rows inactive (soft refresh)
            db.table("custom_spending_tracker").update(
                {"is_active": False, "updated_at": now_iso}
            ).eq("user_id", user_id).execute()

            # 3) Classify + save incoming custom categories
            if custom_categories:
                classifier = CustomCategoryClassifier()

                for item in custom_categories:
                    label = ""
                    value = ""
                    if isinstance(item, dict):
                        label = (item.get("label") or "").strip()
                        value = (item.get("value") or "").strip()
                    else:
                        # Pydantic object fallback
                        label = str(getattr(item, "label", "") or "").strip()
                        value = str(getattr(item, "value", "") or "").strip()

                    if not label and not value:
                        continue

                    custom_item_name = label or value
                    monthly_cost = 0.0
                    try:
                        monthly_cost = float(value) if value else 0.0
                    except Exception:
                        monthly_cost = 0.0

                    # AI classification (fallback-safe)
                    classified_category = "Other"
                    affected_by_fuel = False
                    affected_by_forex = False
                    affected_by_food = False
                    estimated_impact_pct = 0.0
                    reasoning = "Fallback classification."

                    try:
                        # Assumes classifier returns dict-like response
                        classification = await classifier.classify_custom_item(custom_item_name, monthly_cost)
                        classified_category = classification.get(
                            "classified_category", "Other")
                        affected_by_fuel = bool(
                            classification.get("affected_by_fuel", False))
                        affected_by_forex = bool(
                            classification.get("affected_by_forex", False))
                        affected_by_food = bool(
                            classification.get("affected_by_food", False))
                        estimated_impact_pct = float(classification.get(
                            "estimated_impact_pct", 0.0) or 0.0)
                        reasoning = classification.get(
                            "reasoning", "AI classification applied.")
                    except Exception:
                        # keep fallback defaults
                        pass

                    tracker_payload = {
                        "user_id": user_id,
                        "custom_item_name": custom_item_name,
                        "classified_category": classified_category,
                        "monthly_cost": monthly_cost,
                        "affected_by_fuel": affected_by_fuel,
                        "affected_by_forex": affected_by_forex,
                        "affected_by_food": affected_by_food,
                        "estimated_impact_pct": estimated_impact_pct,
                        "ai_classification_reasoning": reasoning,
                        "current_month_impact_kes": round(monthly_cost * (estimated_impact_pct / 100.0), 2),
                        "is_active": True,
                        "updated_at": now_iso,
                    }

                    # Try update existing active/inactive row by (user_id + custom_item_name), else insert
                    existing = (
                        db.table("custom_spending_tracker")
                        .select("id")
                        .eq("user_id", user_id)
                        .eq("custom_item_name", custom_item_name)
                        .limit(1)
                        .execute()
                    )

                    if existing.data:
                        (
                            db.table("custom_spending_tracker")
                            .update(tracker_payload)
                            .eq("id", existing.data[0]["id"])
                            .execute()
                        )
                    else:
                        tracker_payload["created_at"] = now_iso
                        db.table("custom_spending_tracker").insert(
                            tracker_payload).execute()

            return {"message": "Impact profile saved successfully."}

        except Exception as e:
            raise Exception(f"Error saving impact profile: {str(e)}")

    @staticmethod
    async def get_full_impact_data(user_id: str):
        """
        Comprehensive impact calculation for the mobile app's impact page.
        Includes: spending overview, user profile, impact breakdown, AI insights,
        predictions, recommendations, and household comparison.
        """
        db = get_db()

        try:
            # ── Fetch user profile ─────────────────────────────────────────────────
            profile_res = (
                db.table("user_impact_profiles")
                .select("*")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )

            profile_data = profile_res.data[0] if profile_res.data else None

            # If no profile exists, build a safe fallback from monthly/custom data
            monthly_latest_res = (
                db.table("monthly_spending")
                .select("*")
                .eq("user_id", user_id)
                .order("month", desc=True)
                .limit(1)
                .execute()
            )
            monthly_latest = monthly_latest_res.data[0] if monthly_latest_res.data else {
            }

            custom_tracker_res = (
                db.table("custom_spending_tracker")
                .select("*")
                .eq("user_id", user_id)
                .eq("is_active", True)
                .execute()
            )
            custom_tracker_rows = custom_tracker_res.data or []

            if profile_data:
                # Normal path: use saved profile values
                user_impact_profile = UserImpactProfileData(
                    income=int(profile_data.get("income") or 0),
                    rent=int(profile_data.get("rent") or 0),
                    food_budget=int(profile_data.get("food_budget") or 0),
                    transport=profile_data.get("transport") or "N/A",
                    commute=int(profile_data.get("commute") or 0),
                    electricity=int(profile_data.get("electricity") or 0),
                    water=int(profile_data.get("water") or 0),
                    savings=int(profile_data.get("savings") or 0),
                )
            else:
                # Fallback path: infer what we can from existing data
                inferred_food = int(monthly_latest.get("food_spending") or 0)
                inferred_transport = int(
                    monthly_latest.get("transport_spending") or 0)
                inferred_utilities = int(
                    monthly_latest.get("utilities_spending") or 0)
                inferred_other = int(monthly_latest.get("other_spending") or 0)
                inferred_total = int(monthly_latest.get("total_spending") or 0)

                # Keep assumptions conservative when data is missing
                inferred_income = int(
                    inferred_total * 1.25) if inferred_total > 0 else 0
                inferred_savings = max(
                    inferred_income - inferred_total, 0) if inferred_income > 0 else 0

                user_impact_profile = UserImpactProfileData(
                    income=inferred_income,
                    rent=0,
                    food_budget=inferred_food,
                    transport="N/A",
                    commute=0,  # unknown without profile
                    electricity=inferred_utilities // 2 if inferred_utilities > 0 else 0,
                    water=inferred_utilities // 2 if inferred_utilities > 0 else 0,
                    savings=inferred_savings,
                )

            # Format custom categories
            custom_categories_analysis = []

            # Primary source: classified tracker rows
            if custom_tracker_rows:
                for row in custom_tracker_rows:
                    custom_categories_analysis.append(
                        CustomCategoryAnalysis(
                            custom_item_name=row.get("custom_item_name", ""),
                            classified_category=row.get(
                                "classified_category", "Other"),
                            monthly_cost=float(row.get("monthly_cost") or 0),
                            affected_by_fuel=bool(
                                row.get("affected_by_fuel", False)),
                            affected_by_forex=bool(
                                row.get("affected_by_forex", False)),
                            affected_by_food=bool(
                                row.get("affected_by_food", False)),
                            estimated_impact_pct=float(
                                row.get("estimated_impact_pct") or 0),
                            reasoning=row.get(
                                "ai_classification_reasoning", "") or "",
                            created_at=row.get("created_at"),
                            updated_at=row.get("updated_at"),
                        )
                    )

            # Fallback source: raw profile custom_categories JSON
            elif profile_data and profile_data.get("custom_categories"):
                for item in profile_data.get("custom_categories", []):
                    # item could be {"label": "...", "value": "..."} from request payload
                    label = item.get("label") if isinstance(item, dict) else ""
                    value = item.get("value") if isinstance(item, dict) else ""
                    custom_categories_analysis.append(
                        CustomCategoryAnalysis(
                            custom_item_name=label or value or "Custom item",
                            classified_category="Other",
                            monthly_cost=0.0,
                            affected_by_fuel=False,
                            affected_by_forex=False,
                            affected_by_food=False,
                            estimated_impact_pct=0.0,
                            reasoning="Raw profile category (not yet AI-classified).",
                        )
                    )

            user_impact_profile.custom_categories = custom_categories_analysis

            # ── Fetch latest price data (fuel, forex, food) ──────────────────────
            fuel_res = db.table("fuel_prices").select(
                "*").order("created_at", desc=True).limit(30).execute()
            fuel_data = fuel_res.data

            forex_res = db.table("forex_rates").select(
                "*").order("created_at", desc=True).limit(30).execute()
            forex_data = forex_res.data

            food_res = db.table("food_basket").select(
                "*").order("created_at", desc=True).limit(30).execute()
            food_data = food_res.data

            # Calculate base economic indicators for custom category impact
            fuel_change_pct = ImpactService._get_fuel_change_pct(fuel_data)
            forex_change_pct = ImpactService._get_forex_change_pct(forex_data)
            food_change_pct = ImpactService._get_food_change_pct(food_data)

            # ── Calculate transport (fuel) impact ───────────────────────────────
            transport_impact = ImpactService._calculate_transport_impact(
                fuel_data, user_impact_profile.commute
            )

            # ── Calculate food impact ──────────────────────────────────────────
            food_impact = ImpactService._calculate_food_impact(
                food_data, user_impact_profile.food_budget
            )

            # ── Calculate utilities impact (forex-driven electricity/water) ─────
            utilities_impact = ImpactService._calculate_utilities_impact(
                forex_data, user_impact_profile.electricity, user_impact_profile.water
            )

            # ── Calculate custom category impacts ──────────────────────────────
            custom_impact = ImpactService._calculate_custom_categories_impact(
                custom_categories_analysis, fuel_change_pct, forex_change_pct, food_change_pct
            )

            # ── Aggregate into breakdown ──────────────────────────────────────
            impact_breakdown = [
                ImpactCategoryBreakdown(
                    category="Transport",
                    icon="🚐",
                    monthly_amount_kes=transport_impact["monthly_kes"],
                    change_pct=transport_impact["change_pct"],
                    direction=transport_impact["direction"]
                ),
                ImpactCategoryBreakdown(
                    category="Food & Groceries",
                    icon="🛒",
                    monthly_amount_kes=food_impact["monthly_kes"],
                    change_pct=food_impact["change_pct"],
                    direction=food_impact["direction"]
                ),
                ImpactCategoryBreakdown(
                    category="Utilities",
                    icon="⚡",
                    monthly_amount_kes=utilities_impact["monthly_kes"],
                    change_pct=utilities_impact["change_pct"],
                    direction=utilities_impact["direction"]
                ),
                ImpactCategoryBreakdown(
                    category="Other",
                    icon="📌",
                    monthly_amount_kes=custom_impact["total_monthly_kes"],
                    change_pct=custom_impact["total_change_pct"],
                    direction=custom_impact["total_direction"]
                )
            ]

            # ── Calculate total current spending ─────────────────────────────
            total_current_spending = (
                transport_impact["monthly_kes"] +
                food_impact["monthly_kes"] +
                utilities_impact["monthly_kes"] +
                custom_impact["total_monthly_kes"] +
                user_impact_profile.rent +
                (user_impact_profile.savings or 0)
            )

            total_monthly_deductions = total_current_spending
            money_left_this_month = round(
                user_impact_profile.income - total_monthly_deductions, 2)
            savings_utilization_pct = 0.0
            if user_impact_profile.income > 0:
                savings_utilization_pct = round(
                    ((user_impact_profile.savings or 0) / user_impact_profile.income) * 100, 2
                )

            # ── Generate AI insight ──────────────────────────────────────────
            ai_data = {
                "transport": transport_impact,
                "food": food_impact,
                "utilities": utilities_impact,
                "user_impact_profile": user_impact_profile.model_dump()
            }
            ai_insight = ImpactService._generate_ai_summary(ai_data)

            # ── Calculate predictions ────────────────────────────────────────
            predictions = ImpactService._predict_next_month_costs(
                fuel_data, forex_data, food_data,
                transport_impact, food_impact, utilities_impact
            )

            # ── Generate recommendations ─────────────────────────────────────
            recommendations = ImpactService._generate_recommendations(
                transport_impact, food_impact, utilities_impact, user_impact_profile
            )

            # ── Fetch past 6 months spending for chart ───────────────────────
            past_spending_res = db.table("monthly_spending").select("month, total_spending").eq(
                "user_id", user_id).order("month", desc=True).limit(6).execute()
            past_6_months_spending = []
            if past_spending_res.data:
                # Reverse to have chronological order (oldest to newest)
                for row in reversed(past_spending_res.data):
                    past_6_months_spending.append({
                        "month": row["month"],
                        "total_spending": float(row["total_spending"])
                    })

            # ── Calculate spending change from last month ──────────────────────
            spending_change = ImpactService._calculate_spending_change(
                total_current_spending, past_6_months_spending
            )

            # ── Assemble full response ──────────────────────────────────────
            return FullImpactResponse(
                current_month_spending=round(total_current_spending, 2),
                spending_change_pct=spending_change["total_pct"],
                spending_trend=spending_change["direction"],
                total_monthly_deductions=round(total_monthly_deductions, 2),
                money_left_this_month=money_left_this_month,
                savings_utilization_pct=savings_utilization_pct,
                user_impact_profile=user_impact_profile,
                impact_breakdown=impact_breakdown,
                ai_insight=ai_insight["summary"],
                ai_insight_detail=ai_insight["detail"],
                expected_extra_cost_kes=predictions["expected_cost"],
                cost_range_min=predictions["range_min"],
                cost_range_max=predictions["range_max"],
                recommendations=recommendations,
                past_6_months_spending=past_6_months_spending,
                computed_at=datetime.utcnow()
            )

        except Exception as e:
            raise Exception(f"Error computing full impact data: {str(e)}")

    @staticmethod
    def _calculate_transport_impact(fuel_data, daily_commute_km):
        """
        Calculate transport costs based on fuel prices and user commute.
        Assumes ~8L/100km fuel consumption.
        """
        if len(fuel_data) < 2:
            return {"monthly_kes": 0, "change_pct": 0, "direction": "stable"}

        curr_petrol = fuel_data[0].get("petrol_per_litre", 0)
        prev_petrol = fuel_data[1].get("petrol_per_litre", 0)

        # Calculate monthly fuel consumption: daily_commute * 20 working days / 100 * 8L
        monthly_km = daily_commute_km * 20
        monthly_fuel_liters = (monthly_km / 100) * 8

        curr_monthly_cost = round(monthly_fuel_liters * curr_petrol, 2)
        prev_monthly_cost = round(monthly_fuel_liters * prev_petrol, 2)

        change_pct = ImpactService.compute_change_pct(
            curr_monthly_cost, prev_monthly_cost)
        direction = "up" if change_pct > 0 else (
            "down" if change_pct < 0 else "stable")

        return {
            "monthly_kes": curr_monthly_cost,
            "change_pct": change_pct,
            "direction": direction,
            "prev_monthly": prev_monthly_cost
        }

    @staticmethod
    def _calculate_food_impact(food_data, food_budget):
        """
        Calculate food cost changes based on basket prices.
        Determines percentage change in food prices and applies to user's budget.
        """
        if len(food_data) < 2:
            return {"monthly_kes": food_budget, "change_pct": 0, "direction": "stable", "prev_monthly": food_budget}

        curr_basket = ImpactService._calculate_food_basket_cost(food_data[0])
        prev_basket = ImpactService._calculate_food_basket_cost(food_data[1])

        # Calculate percentage change in food basket prices
        change_pct = ImpactService.compute_change_pct(curr_basket, prev_basket)

        # Current monthly cost is user's budgeted amount
        curr_monthly_cost = food_budget

        # Previous cost is adjusted based on the percentage change
        prev_monthly_cost = round(
            food_budget / (1 + change_pct / 100), 2) if change_pct != 0 else food_budget

        direction = "up" if change_pct > 0 else (
            "down" if change_pct < 0 else "stable")

        return {
            "monthly_kes": curr_monthly_cost,
            "change_pct": change_pct,
            "direction": direction,
            "prev_monthly": prev_monthly_cost
        }

    @staticmethod
    def _calculate_food_basket_cost(food_record):
        """
        Calculate total cost of food basket from food prices.
        Assumes average quantities: 10kg maize, 5kg wheat, etc.
        """
        quantities = {
            "maize_flour": 5,      # kg
            "wheat_flour": 2,       # kg
            "rice": 2,
            "sugar": 2,
            "cooking_oil": 1,       # liters
            "milk": 20,             # liters
            "eggs": 30,             # number
            "bread": 20,            # units
            "tomatoes": 10,         # kg
            "onions": 5             # kg
        }

        total = 0
        for item, qty in quantities.items():
            price = food_record.get(item, 0)
            total += price * qty

        return total

    @staticmethod
    def _calculate_utilities_impact(forex_data, electricity_budget, water_budget):
        """
        Calculate utilities impact based on forex rates.
        USD appreciation increases imported diesel/electricity costs.
        """
        if len(forex_data) < 2:
            return {"monthly_kes": 0, "change_pct": 0, "direction": "stable"}

        curr_usd_kes = forex_data[0].get("usd_kes", 0)
        prev_usd_kes = forex_data[1].get("usd_kes", 0)

        usd_change_pct = ImpactService.compute_change_pct(
            curr_usd_kes, prev_usd_kes)

        # Assume 40% of electricity cost is forex-driven (imported diesel)
        electricity_forex_portion = electricity_budget * 0.4
        curr_elec_cost = electricity_budget + \
            (electricity_forex_portion * (usd_change_pct / 100))

        # Assume 20% of water cost is forex-driven
        water_forex_portion = water_budget * 0.2
        curr_water_cost = water_budget + \
            (water_forex_portion * (usd_change_pct / 100))

        curr_total = round(curr_elec_cost + curr_water_cost, 2)
        prev_total = electricity_budget + water_budget

        change_pct = ImpactService.compute_change_pct(curr_total, prev_total)
        direction = "up" if change_pct > 0 else (
            "down" if change_pct < 0 else "stable")

        return {
            "monthly_kes": curr_total,
            "change_pct": change_pct,
            "direction": direction,
            "prev_monthly": prev_total
        }

    @staticmethod
    def _calculate_spending_change(current_spending: float, past_spendings: list[dict]):
        """
        Calculate total spending change percentage by explicitly finding the previous month's data.
        """
        if not past_spendings:
            return {"total_pct": 0.0, "direction": "stable"}

        today = datetime.utcnow()
        first_of_current = today.replace(day=1)
        last_of_prev = first_of_current - timedelta(days=1)
        prev_month_date = last_of_prev.replace(day=1)

        prev_month_prefix = prev_month_date.strftime("%Y-%m-%d")

        prev_spending = 0
        for p in past_spendings:
            if p.get("month", "").startswith(prev_month_prefix):
                prev_spending = p.get("total_spending", 0)
                break

        if prev_spending == 0:
            return {"total_pct": 0.0, "direction": "stable"}

        total_pct = ImpactService.compute_change_pct(
            current_spending, prev_spending)
        direction = "up" if total_pct > 0 else (
            "down" if total_pct < 0 else "stable")

        return {"total_pct": total_pct, "direction": direction}

    @staticmethod
    def _generate_ai_summary(ai_data):
        """
        Generate AI insight. Can be integrated with LLM later.
        """
        transport_pct = ai_data["transport"]["change_pct"]
        food_pct = ai_data["food"]["change_pct"]
        utilities_pct = ai_data["utilities"]["change_pct"]

        # Determine biggest driver
        impacts = {
            "transport": abs(transport_pct),
            "food": abs(food_pct),
            "utilities": abs(utilities_pct)
        }
        biggest = max(impacts, key=impacts.get)

        if biggest == "transport" and transport_pct > 0:
            summary = (
                f"Your transport costs are the biggest driver of your increased expenses. "
                f"Rising fuel prices and your {ai_data['user_impact_profile']['commute']}km daily commute "
                f"are the main reasons."
            )
        elif biggest == "food" and food_pct > 0:
            summary = (
                f"Food & grocery prices have risen significantly, impacting your budget most. "
                f"Consider buying staples in bulk to reduce costs."
            )
        elif biggest == "utilities" and utilities_pct > 0:
            summary = (
                f"Utility costs (electricity & water) are climbing due to forex pressure. "
                f"Look for energy-saving opportunities in your home."
            )
        else:
            summary = (
                f"Your overall expenses remain relatively stable. "
                f"Keep monitoring key spending areas like transport and food."
            )

        detail = (
            f"Transport: {transport_pct:+.1f}% | Food: {food_pct:+.1f}% | "
            f"Utilities: {utilities_pct:+.1f}%"
        )

        return {"summary": summary, "detail": detail}

    @staticmethod
    def _predict_next_month_costs(fuel_data, forex_data, food_data,
                                  transport, food, utilities):
        """
        Predict next month's costs based on trend.
        """
        if not (fuel_data and forex_data and food_data):
            return {"expected_cost": 0, "range_min": 0, "range_max": 0}

        # Simple trend: average of last 3 changes
        fuel_trend = []
        for i in range(min(3, len(fuel_data) - 1)):
            fuel_trend.append(
                ImpactService.compute_change_pct(
                    fuel_data[i].get("petrol_per_litre", 0),
                    fuel_data[i+1].get("petrol_per_litre", 0)
                )
            )
        avg_fuel_trend = sum(fuel_trend) / len(fuel_trend) if fuel_trend else 0

        predicted_transport = transport["monthly_kes"] * \
            (1 + avg_fuel_trend / 100)
        predicted_food = food["monthly_kes"] * 1.02  # Slight increase assumed
        predicted_utilities = utilities["monthly_kes"] * 1.01

        expected_cost = round(
            (predicted_transport + predicted_food + predicted_utilities) -
            (transport["monthly_kes"] +
             food["monthly_kes"] + utilities["monthly_kes"]),
            2
        )

        range_min = round(expected_cost * 0.7, 2)
        range_max = round(expected_cost * 1.3, 2)

        return {
            "expected_cost": max(0, expected_cost),
            "range_min": max(0, range_min),
            "range_max": max(0, range_max)
        }

    @staticmethod
    def _generate_recommendations(transport, food, utilities, user_impact_profile):
        """
        Generate actionable recommendations based on impact data.
        """
        recommendations = []

        if transport["change_pct"] > 10:
            recommendations.append(Recommendation(
                icon="🚗",
                text="Consider carpooling or flexible commute options"
            ))

        if food["change_pct"] > 5:
            recommendations.append(Recommendation(
                icon="🛒",
                text="Buy staples in bulk before prices rise further"
            ))

        if utilities["change_pct"] > 3:
            recommendations.append(Recommendation(
                icon="⚡",
                text="Monitor EPRA adjustments to plan your usage"
            ))

        if not recommendations:
            recommendations.append(Recommendation(
                icon="💡",
                text="Your spending is stable - maintain current habits"
            ))

        return recommendations

    @staticmethod
    def _get_fuel_change_pct(fuel_data):
        """Extract fuel price change percentage from data"""
        if len(fuel_data) < 2:
            return 0.0
        curr = fuel_data[0].get("petrol_per_litre", 0)
        prev = fuel_data[1].get("petrol_per_litre", 0)
        return ImpactService.compute_change_pct(curr, prev)

    @staticmethod
    def _get_forex_change_pct(forex_data):
        """Extract forex change percentage from data"""
        if len(forex_data) < 2:
            return 0.0
        curr = forex_data[0].get("usd_kes", 0)
        prev = forex_data[1].get("usd_kes", 0)
        return ImpactService.compute_change_pct(curr, prev)

    @staticmethod
    def _get_food_change_pct(food_data):
        """Extract food basket change percentage from data"""
        if len(food_data) < 2:
            return 0.0
        curr_basket = ImpactService._calculate_food_basket_cost(food_data[0])
        prev_basket = ImpactService._calculate_food_basket_cost(food_data[1])
        return ImpactService.compute_change_pct(curr_basket, prev_basket)

    @staticmethod
    def _calculate_custom_categories_impact(
        custom_categories: list[CustomCategoryAnalysis],
        fuel_change_pct: float,
        forex_change_pct: float,
        food_change_pct: float
    ):
        """
        Calculate aggregated impact from all custom categories.
        """
        total_monthly_kes = 0.0
        total_impact_kes = 0.0
        impacts_by_category = {}

        for custom_item in custom_categories:
            # Calculate impact using the classifier
            item_impact = CustomCategoryClassifier.calculate_custom_impact(
                custom_item, fuel_change_pct, forex_change_pct, food_change_pct
            )

            total_monthly_kes += item_impact["monthly_cost"]
            total_impact_kes += item_impact["monthly_impact_kes"]

            # Track by classified category
            category = custom_item.classified_category
            if category not in impacts_by_category:
                impacts_by_category[category] = {"amount": 0, "impact": 0}
            impacts_by_category[category]["amount"] += item_impact["monthly_cost"]
            impacts_by_category[category]["impact"] += item_impact["monthly_impact_kes"]

        # Calculate overall change percentage
        total_change_pct = 0.0
        if total_monthly_kes > 0:
            total_change_pct = (total_impact_kes / total_monthly_kes) * 100

        direction = "up" if total_change_pct > 0 else (
            "down" if total_change_pct < 0 else "stable")

        return {
            "total_monthly_kes": round(total_monthly_kes, 2),
            "total_impact_kes": round(total_impact_kes, 2),
            "total_change_pct": round(total_change_pct, 2),
            "total_direction": direction,
            "by_category": impacts_by_category
        }
