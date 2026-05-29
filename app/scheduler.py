import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from app.db import repository as repo

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def start_scheduler() -> None:
    scheduler.add_job(
        _daily_sync,
        "cron",
        hour=settings.sync_cron_hour,
        minute=0,
        id="daily_sync",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started — daily sync at %02d:00 UTC", settings.sync_cron_hour)


async def _daily_sync() -> None:
    from app.services.sync import sync_branch

    branches = repo.list_branches()
    logger.info("Daily sync starting for %d branches", len(branches))
    for row in branches:
        try:
            await sync_branch(row["branch"])
        except Exception:
            logger.exception("Daily sync failed for branch %s", row["branch"])
