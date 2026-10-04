"""Scheduled jobs: daily broadcast and periodic cache refresh."""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.bot.container import Services
from app.utils.dates import tomorrow_in

logger = logging.getLogger(__name__)

DAILY_JOB_ID = "daily_schedule_broadcast"
REFRESH_JOB_ID = "periodic_schedule_refresh"


async def run_daily_broadcast(services: Services) -> None:
    """Refresh tomorrow's month and send each user their schedule for tomorrow."""
    day = tomorrow_in(services.settings.timezone)
    logger.info("Notification started for %s", day)
    try:
        report = await services.schedule.refresh_month(day.year, day.month)
        logger.info(
            "Pre-broadcast refresh %04d-%02d groups=%s entries=%s errors=%s",
            day.year, day.month, report.groups, report.entries, len(report.errors),
        )
    except Exception:  # noqa: BLE001 - fall back to cached data
        logger.exception("Pre-broadcast refresh failed, using cached data")
    await services.notifications.send_tomorrow(day=day)


async def run_periodic_refresh(services: Services) -> None:
    day = tomorrow_in(services.settings.timezone)
    try:
        await services.schedule.refresh_month(day.year, day.month)
    except Exception:  # noqa: BLE001
        logger.exception("Periodic refresh failed")


def setup_scheduler(services: Services) -> AsyncIOScheduler:
    settings = services.settings
    scheduler = AsyncIOScheduler(timezone=settings.timezone)

    scheduler.add_job(
        run_daily_broadcast,
        trigger=CronTrigger(
            hour=settings.send_hour,
            minute=settings.send_minute,
            timezone=settings.timezone,
        ),
        args=[services],
        id=DAILY_JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    scheduler.add_job(
        run_periodic_refresh,
        trigger=IntervalTrigger(hours=6),
        args=[services],
        id=REFRESH_JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    return scheduler
