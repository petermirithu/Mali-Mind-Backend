from typing import Optional
from pydantic import BaseModel
import json
from db.client import get_db
from datetime import datetime, timedelta

class AIInsight(BaseModel):
    id: Optional[int] = None
    trigger: str                   # e.g. "fuel_update", "forex_update"
    summary: str                   # 2-sentence household impact
    impact_score: float            # -1.0 (very negative) to +1.0 (very positive)
    affected_areas: list[str]      # e.g. ["transport", "food", "electricity"]    
    created_at: Optional[datetime] = None

class WeeklyDataPoint(BaseModel):
    week_start: datetime           # start date of the week
    avg_pct: float                 # average percentage change for that week
    
class HighImpactDriver(BaseModel):
    category: str                  # "fuel" | "forex" | "food"
    item: str                      # e.g., "petrol_per_litre", "usd_kes", "maize_flour"
    pct_change: float              # percentage change
    direction: str                 # "up" | "down" | "stable"

class TrendInfo(BaseModel):
    trend_str: str                 # e.g., "↑ 2.5%"
    direction: str                 # "up" | "down" | "stable"
    percent: float                 # percentage change
    
class OverallChangeMetrics(BaseModel):
    fuel_avg_pct: float            # average % change across all fuel types
    forex_avg_pct: float           # average % change across all forex rates
    food_avg_pct: float            # average % change across all food items
    overall_avg_pct: float         # combined average across all categories
    overall_trend: TrendInfo       # trend comparing this week to last week
    high_impact_drivers: list[HighImpactDriver]  # top drivers of change
    weekly_chart_data: list[WeeklyDataPoint]  # historical weekly averages

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

class ForexTrendResponse(BaseModel):
    usd_kes: float
    usd_kes_trend: TrendInfo
    eur_kes: Optional[float] = None
    eur_kes_trend: Optional[TrendInfo] = None
    gbp_kes: Optional[float] = None
    gbp_kes_trend: Optional[TrendInfo] = None
    source: str = "open_exchange_rates"
    created_at: Optional[datetime] = None

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

class DashboardResponse(BaseModel):
    fuel: Optional[FuelTrendResponse]
    forex: Optional[ForexTrendResponse]
    food_basket: Optional[FoodBasketTrendResponse]
    latest_insight: Optional[list[AIInsight]]
    overall_metrics: Optional[OverallChangeMetrics]

class DashboardService:    

    @staticmethod
    def get_dashboard_data() -> dict:
        """
        Fetches latest fuel, forex, and food basket data with trends, 
        plus an AI-generated insight. Used for the mobile Home screen.
        """
        db = get_db()

        try:
            # Latest fuel prices (get 2 records to calculate trends)
            fuel_res = db.table("fuel_prices").select("*").order("created_at", desc=True).limit(2).execute()
            fuel_data = fuel_res.data if fuel_res.data else []
            
            fuel_trend = None
            fuel_trends_list = []
            if fuel_data:
                latest_fuel = fuel_data[0]
                prev_fuel = fuel_data[1] if len(fuel_data) > 1 else fuel_data[0]
                
                fuel_petrol_trend = DashboardService.get_trend(latest_fuel["petrol_per_litre"], prev_fuel["petrol_per_litre"])
                fuel_diesel_trend = DashboardService.get_trend(latest_fuel["diesel_per_litre"], prev_fuel["diesel_per_litre"])
                fuel_kerosene_trend = DashboardService.get_trend(latest_fuel["kerosene_per_litre"], prev_fuel["kerosene_per_litre"])
                
                fuel_trends_list = [
                    {"item": "petrol_per_litre", "pct": fuel_petrol_trend.percent, "trend": fuel_petrol_trend},
                    {"item": "diesel_per_litre", "pct": fuel_diesel_trend.percent, "trend": fuel_diesel_trend},
                    {"item": "kerosene_per_litre", "pct": fuel_kerosene_trend.percent, "trend": fuel_kerosene_trend},
                ]
                
                fuel_trend = FuelTrendResponse(
                    petrol_per_litre=latest_fuel["petrol_per_litre"],
                    petrol_trend=fuel_petrol_trend,
                    diesel_per_litre=latest_fuel["diesel_per_litre"],
                    diesel_trend=fuel_diesel_trend,
                    kerosene_per_litre=latest_fuel["kerosene_per_litre"],
                    kerosene_trend=fuel_kerosene_trend,
                    source=latest_fuel.get("source", "EPRA"),
                    location=latest_fuel.get("location", "Nairobi"),
                    created_at=latest_fuel.get("created_at"),
                )

            # Latest forex rates (get 2 records to calculate trends)
            forex_res = db.table("forex_rates").select("*").order("created_at", desc=True).limit(2).execute()
            forex_data = forex_res.data if forex_res.data else []
            
            forex_trend = None
            forex_trends_list = []
            if forex_data:
                latest_forex = forex_data[0]
                prev_forex = forex_data[1] if len(forex_data) > 1 else forex_data[0]
                
                usd_kes_trend = DashboardService.get_trend(latest_forex["usd_kes"], prev_forex["usd_kes"])
                forex_trends_list.append({"item": "usd_kes", "pct": usd_kes_trend.percent, "trend": usd_kes_trend})
                
                eur_kes_trend = None
                if latest_forex.get("eur_kes") is not None:
                    eur_kes_trend = DashboardService.get_trend(latest_forex["eur_kes"], prev_forex.get("eur_kes", latest_forex["eur_kes"]))
                    forex_trends_list.append({"item": "eur_kes", "pct": eur_kes_trend.percent, "trend": eur_kes_trend})
                
                gbp_kes_trend = None
                if latest_forex.get("gbp_kes") is not None:
                    gbp_kes_trend = DashboardService.get_trend(latest_forex["gbp_kes"], prev_forex.get("gbp_kes", latest_forex["gbp_kes"]))
                    forex_trends_list.append({"item": "gbp_kes", "pct": gbp_kes_trend.percent, "trend": gbp_kes_trend})
                
                forex_trend = ForexTrendResponse(
                    usd_kes=latest_forex["usd_kes"],
                    usd_kes_trend=usd_kes_trend,
                    eur_kes=latest_forex.get("eur_kes"),
                    eur_kes_trend=eur_kes_trend,
                    gbp_kes=latest_forex.get("gbp_kes"),
                    gbp_kes_trend=gbp_kes_trend,
                    source=latest_forex.get("source", "open_exchange_rates"),
                    created_at=latest_forex.get("created_at"),
                )

            # Latest food basket (get 2 records to calculate trends)
            food_res = db.table("food_basket").select("*").order("created_at", desc=True).limit(2).execute()
            food_data = food_res.data if food_res.data else []
            
            food_trend = None
            food_trends_list = []
            if food_data:
                latest_food = food_data[0]
                prev_food = food_data[1] if len(food_data) > 1 else food_data[0]
                
                food_items = ["maize_flour", "wheat_flour", "rice", "sugar", "cooking_oil", "milk", "eggs", "bread", "tomatoes", "onions"]
                
                food_trend_kwargs = {}
                for item in food_items:
                    item_trend = DashboardService.get_trend(latest_food[item], prev_food[item])
                    food_trend_kwargs[item] = latest_food[item]
                    food_trend_kwargs[f"{item}_trend"] = item_trend
                    food_trends_list.append({"item": item, "pct": item_trend.percent, "trend": item_trend})
                
                food_trend_kwargs["created_at"] = latest_food.get("created_at")
                food_trend = FoodBasketTrendResponse(**food_trend_kwargs)

            # Latest AI insight
            insight_res = db.table("ai_insights").select("*").order("created_at", desc=True).limit(3).execute()
            insight = insight_res.data if insight_res.data else None
            for i in insight or []:
                if isinstance(i.get("affected_areas"), str):
                    i["affected_areas"] = json.loads(i["affected_areas"])

            # Calculate overall metrics
            overall_metrics = DashboardService.calculate_overall_metrics(
                fuel_trends_list, forex_trends_list, food_trends_list, db
            )

            return {
                "fuel": fuel_trend,
                "forex": forex_trend,
                "food_basket": food_trend,
                "latest_insight": insight,
                "overall_metrics": overall_metrics,
            }
        except Exception as e:
            raise Exception(e)

    @staticmethod
    def calculate_overall_metrics(
        fuel_trends: list, forex_trends: list, food_trends: list, db
    ) -> OverallChangeMetrics:
        """
        Calculate overall metrics including category averages, overall average,
        trend comparison with last week, high impact drivers, and weekly chart data.
        """
        # Calculate average % change for each category
        fuel_avg_pct = sum(t["pct"] for t in fuel_trends) / len(fuel_trends) if fuel_trends else 0.0
        forex_avg_pct = sum(t["pct"] for t in forex_trends) / len(forex_trends) if forex_trends else 0.0
        food_avg_pct = sum(t["pct"] for t in food_trends) / len(food_trends) if food_trends else 0.0
        
        # Calculate overall average across all categories
        all_trends = fuel_trends + forex_trends + food_trends
        overall_avg_pct = sum(t["pct"] for t in all_trends) / len(all_trends) if all_trends else 0.0
        
        # Get last week's overall average for trend comparison
        last_week_avg = DashboardService.get_last_week_avg_pct(db)
        overall_trend = DashboardService.get_trend(overall_avg_pct, last_week_avg)
        
        # Find high impact drivers (top 5 by absolute % change)
        impact_drivers = []
        for trend_item in fuel_trends:
            impact_drivers.append(HighImpactDriver(
                category="fuel",
                item=trend_item["item"],
                pct_change=trend_item["pct"],
                direction=trend_item["trend"].direction,
            ))
        for trend_item in forex_trends:
            impact_drivers.append(HighImpactDriver(
                category="forex",
                item=trend_item["item"],
                pct_change=trend_item["pct"],
                direction=trend_item["trend"].direction,
            ))
        for trend_item in food_trends:
            impact_drivers.append(HighImpactDriver(
                category="food",
                item=trend_item["item"],
                pct_change=trend_item["pct"],
                direction=trend_item["trend"].direction,
            ))
        
        # Sort by absolute % change and take top 5
        impact_drivers.sort(key=lambda x: abs(x.pct_change), reverse=True)
        impact_drivers = impact_drivers[:5]
        
        # Get weekly chart data
        weekly_chart_data = DashboardService.get_weekly_chart_data(db)
        
        return OverallChangeMetrics(
            fuel_avg_pct=fuel_avg_pct,
            forex_avg_pct=forex_avg_pct,
            food_avg_pct=food_avg_pct,
            overall_avg_pct=overall_avg_pct,
            overall_trend=overall_trend,
            high_impact_drivers=impact_drivers,
            weekly_chart_data=weekly_chart_data,
        )

    @staticmethod
    def get_last_week_avg_pct(db) -> float:
        """
        Calculate average % change for last week by comparing last week's data 
        with the week before that.
        """
        try:
            # Get data from 8-14 days ago (last week)
            fuel_res = db.table("fuel_prices").select("*").order("created_at", desc=True).limit(14).execute()
            fuel_data = fuel_res.data if fuel_res.data else []
            
            if len(fuel_data) < 2:
                return 0.0
            
            # Simple approach: compare oldest 2 records to estimate last week's trend
            if len(fuel_data) >= 14:
                week_ago_data = fuel_data[6:8]  # roughly a week ago
                if len(week_ago_data) == 2:
                    latest = week_ago_data[0]
                    prev = week_ago_data[1]
                    
                    fuel_pct = (((latest["petrol_per_litre"] - prev["petrol_per_litre"]) / prev["petrol_per_litre"]) * 100) if prev["petrol_per_litre"] != 0 else 0
                    return fuel_pct
            
            return 0.0
        except Exception:
            return 0.0

    @staticmethod
    def get_weekly_chart_data(db) -> list[WeeklyDataPoint]:
        """
        Fetch historical weekly data from fuel, forex, and food basket.
        Calculate average % change for each week across all categories.
        Returns the last 4 weeks of data for the chart.
        """
        try:
            weekly_aggregates = {}
            
            # Helper function to parse datetime
            def parse_datetime(dt_value):
                if isinstance(dt_value, str):
                    return datetime.fromisoformat(dt_value.replace('Z', '+00:00'))
                return dt_value
            
            # Helper function to get week start date
            def get_week_start(dt):
                dt = parse_datetime(dt)
                return (dt - timedelta(days=dt.weekday())).date()
            
            # Fetch fuel data (last 60 records)
            fuel_res = db.table("fuel_prices").select("*").order("created_at", desc=True).limit(60).execute()
            fuel_records = fuel_res.data if fuel_res.data else []
            
            # Process fuel data by week
            for i in range(len(fuel_records) - 1):
                current = fuel_records[i]
                next_record = fuel_records[i + 1]
                
                week_key = get_week_start(current["created_at"])
                
                # Calculate % changes for fuel items
                petrol_pct = DashboardService.calculate_pct_change(
                    current["petrol_per_litre"], 
                    next_record["petrol_per_litre"]
                )
                diesel_pct = DashboardService.calculate_pct_change(
                    current["diesel_per_litre"], 
                    next_record["diesel_per_litre"]
                )
                kerosene_pct = DashboardService.calculate_pct_change(
                    current["kerosene_per_litre"], 
                    next_record["kerosene_per_litre"]
                )
                
                fuel_avg = (petrol_pct + diesel_pct + kerosene_pct) / 3
                
                if week_key not in weekly_aggregates:
                    weekly_aggregates[week_key] = {"fuel": [], "forex": [], "food": [], "week_start": week_key}
                
                weekly_aggregates[week_key]["fuel"].append(fuel_avg)
            
            # Fetch forex data (last 60 records)
            forex_res = db.table("forex_rates").select("*").order("created_at", desc=True).limit(60).execute()
            forex_records = forex_res.data if forex_res.data else []
            
            # Process forex data by week
            for i in range(len(forex_records) - 1):
                current = forex_records[i]
                next_record = forex_records[i + 1]
                
                week_key = get_week_start(current["created_at"])
                
                # Calculate % changes for forex rates
                usd_pct = DashboardService.calculate_pct_change(
                    current["usd_kes"], 
                    next_record["usd_kes"]
                )
                
                forex_changes = [usd_pct]
                
                if current.get("eur_kes") is not None and next_record.get("eur_kes") is not None:
                    eur_pct = DashboardService.calculate_pct_change(
                        current["eur_kes"], 
                        next_record["eur_kes"]
                    )
                    forex_changes.append(eur_pct)
                
                if current.get("gbp_kes") is not None and next_record.get("gbp_kes") is not None:
                    gbp_pct = DashboardService.calculate_pct_change(
                        current["gbp_kes"], 
                        next_record["gbp_kes"]
                    )
                    forex_changes.append(gbp_pct)
                
                forex_avg = sum(forex_changes) / len(forex_changes) if forex_changes else 0.0
                
                if week_key not in weekly_aggregates:
                    weekly_aggregates[week_key] = {"fuel": [], "forex": [], "food": [], "week_start": week_key}
                
                weekly_aggregates[week_key]["forex"].append(forex_avg)
            
            # Fetch food basket data (last 60 records)
            food_res = db.table("food_basket").select("*").order("created_at", desc=True).limit(60).execute()
            food_records = food_res.data if food_res.data else []
            
            # Process food basket data by week
            food_items = ["maize_flour", "wheat_flour", "rice", "sugar", "cooking_oil", "milk", "eggs", "bread", "tomatoes", "onions"]
            
            for i in range(len(food_records) - 1):
                current = food_records[i]
                next_record = food_records[i + 1]
                
                week_key = get_week_start(current["created_at"])
                
                # Calculate % changes for food items
                food_changes = []
                for item in food_items:
                    item_pct = DashboardService.calculate_pct_change(
                        current[item], 
                        next_record[item]
                    )
                    food_changes.append(item_pct)
                
                food_avg = sum(food_changes) / len(food_changes) if food_changes else 0.0
                
                if week_key not in weekly_aggregates:
                    weekly_aggregates[week_key] = {"fuel": [], "forex": [], "food": [], "week_start": week_key}
                
                weekly_aggregates[week_key]["food"].append(food_avg)
            
            # Calculate overall average for each week and format response
            weekly_data = []
            sorted_weeks = sorted(weekly_aggregates.keys(), reverse=True)[:4]  # Last 4 weeks
            
            for week_key in sorted(sorted_weeks):
                week_data = weekly_aggregates[week_key]
                
                # Calculate average across all categories
                category_averages = []
                
                if week_data["fuel"]:
                    category_averages.append(sum(week_data["fuel"]) / len(week_data["fuel"]))
                if week_data["forex"]:
                    category_averages.append(sum(week_data["forex"]) / len(week_data["forex"]))
                if week_data["food"]:
                    category_averages.append(sum(week_data["food"]) / len(week_data["food"]))
                
                overall_avg = sum(category_averages) / len(category_averages) if category_averages else 0.0
                
                week_start_dt = datetime.combine(week_key, datetime.min.time())
                weekly_data.append(WeeklyDataPoint(
                    week_start=week_start_dt,
                    avg_pct=overall_avg,
                ))
            
            return weekly_data
        except Exception as e:
            print(f"Error in get_weekly_chart_data: {e}")
            return []

    @staticmethod
    def calculate_pct_change(current: float, previous: float) -> float:
        """
        Calculate percentage change between two values.
        Returns 0.0 if previous is 0 or values are invalid.
        """
        if previous is None or previous == 0:
            return 0.0
        try:
            return ((current - previous) / previous) * 100
        except (TypeError, ZeroDivisionError):
            return 0.0

    @staticmethod
    def get_trend(latest: float, prev: float | None = None) -> TrendInfo:
        """
        Calculate trend between two values.
        Returns trend string with direction, direction indicator, and percentage change.
        """
        if prev is None or prev == 0:
            return TrendInfo(trend_str="-", direction="stable", percent=0.0)
        
        diff = latest - prev
        pct = (diff / prev) * 100
        direction = "stable"
        trend_str = f"{'-'} {abs(pct):.1f}%"

        if pct < 0:   
            direction = "down"         
            trend_str = f"{'↓'} {abs(pct):.1f}%"
        elif pct > 0:  
            direction="up"          
            trend_str = f"{'↑'} {abs(pct):.1f}%"        
        
        return TrendInfo(trend_str=trend_str, direction=direction, percent=pct) 