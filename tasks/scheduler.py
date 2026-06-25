"""
Background scheduler for:
- Monthly spending aggregation (1st day midnight)
- Forex fetch (daily 7AM)
- Fuel prices fetch (15th monthly 7AM)
- Food basket seed (weekly Monday 7AM)
- Feed seed (daily 7AM)

Fetcher jobs call internal HTTP endpoints in api/routes/fetchers.py.
"""
import asyncio
import logging
from datetime import datetime, timezone

import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from api.services.impact import ImpactService
from core.config import settings
from db.client import get_db

logger = logging.getLogger(__name__)

# Ensure all cron jobs run in Kenya time.
scheduler = BackgroundScheduler(timezone="Africa/Nairobi")


def _trigger_fetcher(path: str):
    """
    Trigger internal fetcher endpoint with cron secret.
    Example paths: /fetch/forex, /fetch/fuel, /fetch/food, /fetch/feed
    """
    base_url = str(settings.api_base_url).rstrip("/")
    url = f"{base_url}{path}"

    headers = {"x-cron-secret": settings.cron_secret}
    timeout = httpx.Timeout(60.0)

    logger.info(f"Triggering fetcher: {url}")
    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, headers=headers)
        response.raise_for_status()
        try:
            return response.json()
        except Exception:
            # In case endpoint returns non-JSON
            return {"status_code": response.status_code, "text": response.text}


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
                    logger.info(
                        f"Skipped user {user_id}: month {month_to_archive} already archived."
                    )
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


@scheduler.scheduled_job(CronTrigger(hour=7, minute=0))
def run_daily_forex_fetch():
    """Trigger forex fetch endpoint daily at 7:00 AM (Africa/Nairobi)."""
    try:
        logger.info("Daily forex fetch job started...")
        result = _trigger_fetcher("/fetch/forex")
        logger.info(f"Daily forex fetch job completed: {result}")
    except Exception as e:
        logger.error(f"Daily forex fetch job failed: {str(e)}", exc_info=True)


@scheduler.scheduled_job(CronTrigger(day=15, hour=7, minute=0))
def run_monthly_fuel_fetch():
    """Trigger fuel fetch endpoint on the 15th of every month at 7:00 AM."""
    try:
        logger.info("Monthly fuel fetch job started...")
        result = _trigger_fetcher("/fetch/fuel")
        logger.info(f"Monthly fuel fetch job completed: {result}")
    except Exception as e:
        logger.error(f"Monthly fuel fetch job failed: {str(e)}", exc_info=True)


@scheduler.scheduled_job(CronTrigger(day_of_week="mon", hour=7, minute=0))
def run_weekly_food_seed():
    """Trigger food seed endpoint weekly on Monday at 7:00 AM."""
    try:
        logger.info("Weekly food basket seed job started...")
        result = _trigger_fetcher("/fetch/food")
        logger.info(f"Weekly food basket seed job completed: {result}")
    except Exception as e:
        logger.error(f"Weekly food basket seed job failed: {str(e)}", exc_info=True)


@scheduler.scheduled_job(CronTrigger(hour=7, minute=0))
def run_daily_feed_seed():
    """Trigger feed seed endpoint daily at 7:00 AM."""
    try:
        logger.info("Daily feed seed job started...")
        result = _trigger_fetcher("/fetch/feed")
        logger.info(f"Daily feed seed job completed: {result}")
    except Exception as e:
        logger.error(f"Daily feed seed job failed: {str(e)}", exc_info=True)


def start_scheduler():
    """
    Start the background scheduler.
    Call this once during app startup.
    """
    if not scheduler.running:
        scheduler.start()
        logger.info("Background scheduler started (timezone=Africa/Nairobi)")
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