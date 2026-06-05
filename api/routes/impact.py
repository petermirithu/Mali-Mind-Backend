from fastapi import APIRouter, HTTPException, BackgroundTasks
from datetime import datetime, timedelta
from api.services.impact import ImpactService
from db.client import get_db
from schemas.models import ImpactResponse, ImpactItem, ImpactProfileRequest, FullImpactResponse
from tasks.scheduler import archive_previous_month_spending

router = APIRouter(prefix="/impact", tags=["impact"])

@router.get("/", response_model=ImpactResponse)
async def get_impact():    
    try:
        results = ImpactService.get_impact_data()

        return ImpactResponse(
            items=results["items"],
            overall_score=results["overall_score"],
            ai_summary=results["ai_summary"],
            computed_at=datetime.utcnow(),
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{user_id}", response_model=FullImpactResponse)
async def get_full_impact(user_id: str, background_tasks: BackgroundTasks):
    """
    Comprehensive impact page endpoint for mobile app.
    Returns all impact metrics, breakdown, predictions, and recommendations.
    
    Args:
        user_id: The user's unique identifier
        background_tasks: FastAPI background tasks
    
    Returns:
        FullImpactResponse with complete impact data
    """
    try:
        db = get_db()                
        month_to_archive = datetime.utcnow().replace(day=1)
        
        # Check if monthly record exists for the user for the previous month
        record = db.table("monthly_spending").select("user_id").eq("user_id", user_id).eq("month", month_to_archive.isoformat()).execute()
        
        if not record.data:
            background_tasks.add_task(archive_previous_month_spending)

        result = await ImpactService.get_full_impact_data(user_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/profiles")
async def save_impact_profile(profile: ImpactProfileRequest):
    try:                        
        await ImpactService.save_impact_profile_items(profile)        
        return {"status": "ok", "message": "Impact profile saved successfully."}
    except Exception as e:
        print("Error saving impact profile:", str(e))  # Debug log
        raise HTTPException(status_code=400, detail=str(e))