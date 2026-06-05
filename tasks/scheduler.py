"""
Background scheduler for monthly spending aggregation.
Runs at midnight on the 1st of each month to archive previous month's spending data.
"""
import logging
import asyncio
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from db.client import get_db
from api.services.impact import ImpactService

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


@scheduler.scheduled_job(CronTrigger(day=1, hour=0, minute=0))
def archive_previous_month_spending():
    """
    Runs at midnight on the 1st of each month.
    Archives the previous month's spending data for all users.
    """
    try:
        logger.info("🕐 Monthly spending archive job started...")
        db = get_db()
        
        # Get all active users
        users_res = db.table("user_impact_profiles").select("user_id").execute()
        users = users_res.data if users_res.data else []
        
        if not users:
            logger.warning("No users found in user_impact_profiles")
            return
        
        logger.info(f"Processing {len(users)} users...")
        archived_count = 0
        failed_users = []
        
        for user_record in users:
            try:
                user_id = user_record["user_id"]
                
                # Calculate current month's spending
                month_to_archive = datetime.utcnow().replace(day=1)
                                
                # Get full impact data (async call)
                impact_data = asyncio.run(ImpactService.get_full_impact_data(user_id))
                
                # Extract breakdown data
                transport_spending = 0
                food_spending = 0
                utilities_spending = 0
                other_spending = 0
                
                for category in impact_data.impact_breakdown:
                    if category.category == "Transport":
                        transport_spending = category.monthly_amount_kes
                    elif category.category == "Food & Groceries":
                        food_spending = category.monthly_amount_kes
                    elif category.category == "Utilities":
                        utilities_spending = category.monthly_amount_kes
                    elif category.category == "Other":
                        other_spending = category.monthly_amount_kes
                
                # Prepare monthly record
                monthly_record = {
                    "user_id": user_id,
                    "month": month_to_archive.isoformat(),
                    "total_spending": impact_data.current_month_spending,
                    "transport_spending": transport_spending,
                    "food_spending": food_spending,
                    "utilities_spending": utilities_spending,
                    "other_spending": other_spending,
                    "change_pct_from_prev": impact_data.spending_change_pct,                    
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat()
                }
                
                # Upsert (create or update) the monthly spending record
                db.table("monthly_spending").upsert(monthly_record).execute()
                
                archived_count += 1
                logger.info(
                    f"✓ Archived {user_id} - Month: {month_to_archive.strftime('%Y-%m')}, "
                    f"Total: KES {impact_data.current_month_spending:,.0f}"
                )
                
            except Exception as e:
                logger.error(f"✗ Failed to archive for user {user_record.get('user_id')}: {str(e)}")
                failed_users.append(str(user_record.get("user_id")))
                continue
        
        logger.info(
            f"📊 Archive job completed: {archived_count} successful, "
            f"{len(failed_users)} failed"
        )
        
        if failed_users:
            logger.warning(f"Failed users: {', '.join(failed_users)}")
        
    except Exception as e:
        logger.error(f"❌ Monthly archive job failed: {str(e)}", exc_info=True)


def start_scheduler():
    """
    Start the background scheduler.
    Call this once during app startup.
    """
    if not scheduler.running:
        scheduler.start()
        logger.info("✓ Background scheduler started")
    else:
        logger.info("⚠️  Background scheduler already running")


def stop_scheduler():
    """
    Stop the background scheduler.
    Call this during app shutdown.
    """
    if scheduler.running:
        scheduler.shutdown()
        logger.info("✓ Background scheduler stopped")
