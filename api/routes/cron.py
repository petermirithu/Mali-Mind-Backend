from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException

from core.cron_auth import require_cron_secret
from tasks.scheduler import archive_previous_month_spending

router = APIRouter(
    prefix="/cron", tags=["cron"], dependencies=[Depends(require_cron_secret)]
)


@router.get("/monthly-spending", include_in_schema=False)
def archive_monthly_spending():
    # UTC cron cannot express the last day of every month; only run on Nairobi's 1st.
    if datetime.now(ZoneInfo("Africa/Nairobi")).day != 1:
        return {"status": "skipped", "reason": "Not the first day in Africa/Nairobi"}

    result = archive_previous_month_spending()
    if result["failed"]:
        raise HTTPException(status_code=500, detail="Monthly spending archive failed; check logs")
    return {"status": "ok", **result}
