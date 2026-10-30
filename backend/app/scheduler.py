"""Background scheduling: one APScheduler job per active monitor.

How it fits together:
- `scheduler` is an AsyncIOScheduler. It runs INSIDE uvicorn's event loop, so our async
  `run_check_for_monitor` coroutine is awaited directly, like any other async code.
  (A BackgroundScheduler would use threads instead, and couldn't await coroutines.)
- Jobs live only in memory. That is fine because the database is the source of truth:
  on startup `schedule_all_active_monitors()` rebuilds every job from the `monitors`
  table. No separate "job store" to keep in sync.
- The API calls `schedule_monitor` / `unschedule_monitor` when monitors are created,
  paused, resumed or deleted.

Caveat: if you ran several uvicorn worker processes, EACH would start its own scheduler
and every check would run several times. Run a single worker (the default).
"""

import logging
from datetime import UTC, datetime

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Monitor
from app.services import run_check_for_monitor

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(
    timezone=UTC,
    job_defaults={
        # max_instances=1: never run two checks of the SAME monitor at once. If a check
        # is still waiting on a slow site when the next one is due, the new run is skipped.
        "max_instances": 1,
        # coalesce=True: if several runs were missed (e.g. the laptop slept), run ONE
        # catch-up check instead of a burst of them.
        "coalesce": True,
        # A run may start up to 30 s late (busy event loop) and still count as on time.
        "misfire_grace_time": 30,
    },
)


def _job_id(monitor_id: int) -> str:
    return f"monitor-{monitor_id}"


async def _scheduled_check(monitor_id: int) -> None:
    """What each job runs. Never let an exception escape into the scheduler."""
    try:
        check = await run_check_for_monitor(monitor_id)
    except Exception:
        # A bug in one check must not kill the job; log it with the traceback.
        logger.exception("Scheduled check for monitor %s crashed", monitor_id)
        return
    if check is None:
        # The monitor no longer exists (deleted mid-check); stop scheduling it.
        unschedule_monitor(monitor_id)
        return
    logger.info(
        "Checked monitor %s: %s (%s, %s ms)",
        monitor_id,
        "UP" if check.is_up else "DOWN",
        check.status_code if check.status_code is not None else check.error,
        check.response_ms,
    )


def schedule_monitor(monitor_id: int, interval_seconds: int) -> None:
    """Create (or replace) the job for one monitor. Its first check runs immediately."""
    scheduler.add_job(
        _scheduled_check,
        trigger=IntervalTrigger(seconds=interval_seconds, timezone=UTC),
        args=[monitor_id],
        id=_job_id(monitor_id),
        name=f"check monitor {monitor_id}",
        # Calling this again for the same monitor (e.g. resume) replaces the old job
        # instead of raising ConflictingIdError.
        replace_existing=True,
        # Without this, the first run would be one full interval from now.
        next_run_time=datetime.now(UTC),
    )


def unschedule_monitor(monitor_id: int) -> None:
    try:
        scheduler.remove_job(_job_id(monitor_id))
    except JobLookupError:
        pass  # already gone (paused monitor, or deleted twice): nothing to do


def schedule_all_active_monitors() -> int:
    """Rebuild jobs from the database. Called once at startup. Returns the job count."""
    with SessionLocal() as db:
        rows = db.execute(
            select(Monitor.id, Monitor.interval_seconds).where(Monitor.is_active.is_(True))
        ).all()
    for monitor_id, interval_seconds in rows:
        schedule_monitor(monitor_id, interval_seconds)
    return len(rows)
