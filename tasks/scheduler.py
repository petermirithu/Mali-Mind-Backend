"""
Background scheduler for monthly spending aggregation.
Runs at midnight on the 1st of each month to archive previous month's spending data.
"""
import logging
import asyncio
from datetime import datetime, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from db.client import get_db
from api.services.impact import ImpactService

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


@scheduler.scheduled_job(CronTrigger(day=1, hour=0, minute=0))
def archive_previous_month_spending(specific_user_id: int | None = None):
    """
    Runs at midnight on the 1st of each month (via scheduler), or can be called manually.
    - If specific_user_id is provided, archive only that user.
    - Otherwise archive all users in user_impact_profiles.
    """
    try:
        logger.info("Monthly spending archive job started...")
        db = get_db()

        # Normalize to month key used in monthly_spending.month (DATE)
        month_to_archive = datetime.now(timezone.utc).date().replace(day=1).isoformat()

        if specific_user_id is not None:
            users = [{"user_id": int(specific_user_id)}]
            logger.info(f"Processing specific user: {specific_user_id}")
        else:
            users_res = db.table("user_impact_profiles").select("user_id").execute()
            users = users_res.data if users_res.data else []

        if not users:
            logger.warning("No users found to archive.")
            return

        logger.info(f"Processing {len(users)} user(s) for month {month_to_archive}...")
        archived_count = 0
        skipped_count = 0
        failed_users: list[str] = []

        for user_record in users:
            user_id = user_record.get("user_id")
            if user_id is None:
                continue

            try:
                # 1) Skip if already archived for this user/month
                existing = (
                    db.table("monthly_spending")
                    .select("id")
                    .eq("user_id", user_id)
                    .eq("month", month_to_archive)
                    .limit(1)
                    .execute()
                )
                if existing.data:
                    skipped_count += 1
                    logger.info(f"Skipped user {user_id}: month {month_to_archive} already archived.")
                    continue

                # 2) Compute impact snapshot
                impact_data = asyncio.run(ImpactService.get_full_impact_data(str(user_id)))

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

                now_iso = datetime.now(timezone.utc).isoformat()
                monthly_record = {
                    "user_id": user_id,
                    "month": month_to_archive,
                    "total_spending": impact_data.current_month_spending,
                    "transport_spending": transport_spending,
                    "food_spending": food_spending,
                    "utilities_spending": utilities_spending,
                    "other_spending": other_spending,
                    "change_pct_from_prev": impact_data.spending_change_pct,
                    "created_at": now_iso,
                    "updated_at": now_iso,
                }

                # 3) Upsert with explicit conflict target
                (
                    db.table("monthly_spending")
                    .upsert(monthly_record, on_conflict="user_id,month")
                    .execute()
                )

                archived_count += 1
                logger.info(
                    f"Archived user {user_id} - Month: {month_to_archive}, "
                    f"Total: KES {impact_data.current_month_spending:,.0f}"
                )

            except Exception as e:
                logger.error(f"Failed to archive for user {user_id}: {str(e)}")
                failed_users.append(str(user_id))
                continue

        logger.info(
            f"Archive job completed: {archived_count} archived, "
            f"{skipped_count} skipped, {len(failed_users)} failed"
        )
        if failed_users:
            logger.warning(f"Failed users: {', '.join(failed_users)}")

    except Exception as e:
        logger.error(f"Monthly archive job failed: {str(e)}", exc_info=True)


def start_scheduler():
    """
    Start the background scheduler.
    Call this once during app startup.
    """
    if not scheduler.running:
        scheduler.start()
        logger.info("Background scheduler started")
    else:
        logger.info("Background scheduler already running")


def stop_scheduler():
    """
    Stop the background scheduler.
    Call this during app shutdown.
    """
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Background scheduler stopped")