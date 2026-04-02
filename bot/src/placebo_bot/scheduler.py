import logging
from datetime import time
from zoneinfo import ZoneInfo

from telegram.ext import Application

from placebo_bot import db
from placebo_bot.config import settings
from placebo_bot.telegram_handler import trigger_checkin

logger = logging.getLogger(__name__)

_app: Application | None = None


async def _daily_checkin_job(context) -> None:
    """Job callback: send daily check-in to the stored chat_id."""
    try:
        chat_id_str = await db.get_bot_setting("chat_id")
        if not chat_id_str:
            logger.warning("No chat_id configured — skipping check-in. Send /start to the bot first.")
            return

        chat_id = int(chat_id_str)

        async def send_fn(cid: int, text: str) -> None:
            await context.bot.send_message(chat_id=cid, text=text, parse_mode="Markdown")

        await trigger_checkin(chat_id, send_fn)
    except Exception:
        logger.exception("Daily check-in job failed")


def schedule_checkin(app: Application, hour: int, minute: int, timezone: str = "UTC") -> None:
    """Schedule the daily check-in job."""
    global _app
    _app = app
    job_queue = app.job_queue

    # Remove existing check-in jobs
    existing = job_queue.get_jobs_by_name("daily_checkin")
    for job in existing:
        job.schedule_removal()

    job_queue.run_daily(
        _daily_checkin_job,
        time=time(hour=hour, minute=minute, tzinfo=ZoneInfo(timezone)),
        name="daily_checkin",
    )
    logger.info("Scheduled daily check-in at %02d:%02d %s", hour, minute, timezone)


async def reschedule_from_db() -> None:
    """Read schedule from DB (falling back to env defaults) and reschedule."""
    hour = int(await db.get_bot_setting("checkin_hour") or settings.checkin_hour)
    minute = int(await db.get_bot_setting("checkin_minute") or settings.checkin_minute)
    timezone = await db.get_bot_setting("checkin_timezone") or settings.checkin_timezone
    schedule_checkin(_app, hour, minute, timezone)
