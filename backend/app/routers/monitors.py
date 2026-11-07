"""HTTP endpoints for monitors and their checks.

`def` vs `async def` endpoints in FastAPI (a common point of confusion):
- `async def` runs ON the event loop. Use it when the endpoint awaits something slow
  (our HTTP check). Never call slow *blocking* code in it, or every request stalls.
- Plain `def` runs in a worker thread pool, so blocking code there is fine.
Our database driver (sqlite3) is blocking, but SQLite queries on a small local file take
well under a millisecond, so we accept brief blocking inside the async endpoints below.
A larger app would use an async driver (e.g. aiosqlite / asyncpg) instead.
"""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db, utcnow
from app.models import Check, Monitor
from app.rate_limit import RateLimit
from app.scheduler import schedule_monitor, unschedule_monitor
from app.schemas import (
    CheckOut,
    MonitorCreate,
    MonitorOut,
    MonitorStatsOut,
    MonitorUpdate,
    StatsBucketOut,
)
from app.services import latest_checks_by_monitor, run_check_for_monitor
from app.stats import CheckPoint, compute_stats
from app.url_safety import UnsafeUrlError, assert_url_is_safe

MAX_STATS_HOURS = 24 * 30

router = APIRouter(prefix="/monitors", tags=["monitors"])

# `Annotated[Session, Depends(get_db)]` tells FastAPI: "call get_db() and pass the
# result in". Giving it a name avoids repeating the Depends(...) in every signature.
DbSession = Annotated[Session, Depends(get_db)]

# Tighter limits on the two endpoints that make this server send requests to other websites.
_limit_new_monitors = RateLimit(limit=30, window_seconds=60)
_limit_check_now = RateLimit(limit=30, window_seconds=60)


def _get_monitor_or_404(db: Session, monitor_id: int) -> Monitor:
    monitor = db.get(Monitor, monitor_id)
    if monitor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found.")
    return monitor


def _to_out(monitor: Monitor, latest: Check | None) -> MonitorOut:
    out = MonitorOut.model_validate(monitor)
    out.latest_check = CheckOut.model_validate(latest) if latest else None
    return out


@router.get("", response_model=list[MonitorOut])
def list_monitors(db: DbSession) -> list[MonitorOut]:
    monitors = list(db.scalars(select(Monitor).order_by(Monitor.created_at, Monitor.id)))
    latest = latest_checks_by_monitor(db, [m.id for m in monitors])
    return [_to_out(m, latest.get(m.id)) for m in monitors]


@router.get("/{monitor_id}", response_model=MonitorOut)
def get_monitor(monitor_id: int, db: DbSession) -> MonitorOut:
    monitor = _get_monitor_or_404(db, monitor_id)
    latest = latest_checks_by_monitor(db, [monitor.id]).get(monitor.id)
    return _to_out(monitor, latest)


@router.post(
    "",
    response_model=MonitorOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_limit_new_monitors)],
)
async def create_monitor(payload: MonitorCreate, db: DbSession) -> MonitorOut:
    # By the time we get here, Pydantic has already validated the body (name length,
    # URL format, interval range) and FastAPI answered 422 if anything was wrong.
    url = str(payload.url)
    try:
        await assert_url_is_safe(url)
    except UnsafeUrlError as exc:
        # 400 rather than 422: the URL is well-formed, we just refuse to fetch it.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    monitor = Monitor(name=payload.name, url=url, interval_seconds=payload.interval_seconds)
    db.add(monitor)
    db.commit()

    # The job's first run is scheduled for "now", so the first check starts right away
    # in the background. We don't wait for it: the response returns immediately with
    # latestCheck = null, which the dashboard shows as "Pending" until the result lands.
    schedule_monitor(monitor.id, monitor.interval_seconds)
    return _to_out(monitor, None)


@router.patch("/{monitor_id}", response_model=MonitorOut)
async def update_monitor(monitor_id: int, payload: MonitorUpdate, db: DbSession) -> MonitorOut:
    monitor = _get_monitor_or_404(db, monitor_id)
    maintenance_changed = (
        payload.in_maintenance is not None and payload.in_maintenance != monitor.in_maintenance
    )
    if payload.in_maintenance is not None:
        # Checks keep running during maintenance, so the scheduler is not involved.
        monitor.in_maintenance = payload.in_maintenance
    # Only touch the scheduler when the active flag really changes. Otherwise a repeated
    # {"isActive": true} would trigger an unnecessary extra check each time.
    active_changed = payload.is_active is not None and payload.is_active != monitor.is_active
    if payload.is_active is not None:
        monitor.is_active = payload.is_active
    if active_changed or maintenance_changed:
        # "In a row" ends here: a failure from before a pause must not add to one after it.
        monitor.consecutive_failures = 0
    db.commit()
    if active_changed:
        if monitor.is_active:
            schedule_monitor(monitor.id, monitor.interval_seconds)  # resume: checks right away
        else:
            unschedule_monitor(monitor.id)
    latest = latest_checks_by_monitor(db, [monitor.id]).get(monitor.id)
    return _to_out(monitor, latest)


@router.delete("/{monitor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_monitor(monitor_id: int, db: DbSession) -> Response:
    monitor = _get_monitor_or_404(db, monitor_id)
    unschedule_monitor(monitor_id)
    db.delete(monitor)  # the database deletes its checks via ON DELETE CASCADE
    db.commit()
    # If a check for this monitor is in flight right now, run_check_for_monitor notices
    # the monitor is gone when it tries to save, and discards the result.
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{monitor_id}/check", response_model=CheckOut, dependencies=[Depends(_limit_check_now)]
)
async def check_now(monitor_id: int, db: DbSession) -> CheckOut:
    _get_monitor_or_404(db, monitor_id)
    # Release the request's session before the slow network call (see services.py).
    db.close()
    check = await run_check_for_monitor(monitor_id)
    if check is None:  # deleted while we were checking
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found.")
    return CheckOut.model_validate(check)


@router.get("/{monitor_id}/checks", response_model=list[CheckOut])
def list_checks(
    monitor_id: int,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[CheckOut]:
    _get_monitor_or_404(db, monitor_id)
    stmt = (
        select(Check)
        .where(Check.monitor_id == monitor_id)
        .order_by(Check.checked_at.desc(), Check.id.desc())
        .limit(limit)
    )
    return [CheckOut.model_validate(c) for c in db.scalars(stmt)]


@router.get("/{monitor_id}/stats", response_model=MonitorStatsOut)
def get_monitor_stats(
    monitor_id: int,
    db: DbSession,
    # 1 hour up to 30 days. The frontend offers 24 h, 7 d and 30 d.
    hours: Annotated[int, Query(ge=1, le=MAX_STATS_HOURS)] = 24,
) -> MonitorStatsOut:
    _get_monitor_or_404(db, monitor_id)
    period_end = utcnow()
    period_start = period_end - timedelta(hours=hours)

    # Fetch only the three columns we need, not whole Check objects: for a 30-day window
    # that can be tens of thousands of rows, and building ORM objects for each is slow.
    # The (monitor_id, checked_at) index makes this WHERE clause fast.
    rows = db.execute(
        select(Check.checked_at, Check.is_up, Check.response_ms).where(
            Check.monitor_id == monitor_id,
            Check.checked_at >= period_start,
            # Planned downtime shouldn't count against uptime. These slices show as "no data".
            Check.during_maintenance.is_(False),
        )
    ).all()
    stats = compute_stats(
        [CheckPoint(checked_at=r.checked_at, is_up=r.is_up, response_ms=r.response_ms) for r in rows],
        period_end=period_end,
        hours=hours,
    )
    return MonitorStatsOut(
        monitor_id=monitor_id,
        period_hours=hours,
        period_start=stats.period_start,
        period_end=stats.period_end,
        bucket_seconds=stats.bucket_seconds,
        total_checks=stats.total_checks,
        up_checks=stats.up_checks,
        down_checks=stats.down_checks,
        uptime_percent=stats.uptime_percent,
        avg_response_ms=stats.avg_response_ms,
        p95_response_ms=stats.p95_response_ms,
        min_response_ms=stats.min_response_ms,
        max_response_ms=stats.max_response_ms,
        buckets=[
            StatsBucketOut(
                start=b.start,
                end=b.end,
                total_checks=b.total_checks,
                down_checks=b.down_checks,
                avg_response_ms=b.avg_response_ms,
                max_response_ms=b.max_response_ms,
            )
            for b in stats.buckets
        ],
    )
