from fastapi import APIRouter, HTTPException
from api.services.dashboard import DashboardResponse, DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/", response_model=DashboardResponse)
async def get_dashboard():
    """
    Returns a full snapshot: latest fuel with trends, forex with trends, 
    food basket with trends, AI insight, and overall metrics including 
    high impact drivers and weekly chart data.
    This is the main endpoint powering the mobile Home screen.
    """
    try:
        results = DashboardService.get_dashboard_data()

        return DashboardResponse(
            fuel=results["fuel"],
            forex=results["forex"],
            food_basket=results["food_basket"],
            latest_insight=results["latest_insight"],
            overall_metrics=results["overall_metrics"],
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))