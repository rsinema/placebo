from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from placebo_backup.config import settings
from placebo_backup.operations import run_backup

logger = logging.getLogger(__name__)


def _seconds_until_next_run(hour_utc: int, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    target = now.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def daily_loop() -> None:
    """Sleep until the configured UTC hour, run a daily backup, repeat.

    Drift over the lifetime of the process is acceptable for a personal tool.
    If a backup fails, log it and keep the loop alive — next day will retry.
    """
    while True:
        delay = _seconds_until_next_run(settings.backup_hour_utc)
        logger.info("next daily backup in %.0f seconds (~%.1f hours)", delay, delay / 3600)
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            logger.info("daily loop cancelled")
            return
        try:
            await run_backup(kind="daily")
        except Exception:
            logger.exception("daily backup failed; will retry tomorrow")
