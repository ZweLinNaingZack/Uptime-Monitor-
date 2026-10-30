"""HTTP endpoints for monitors and their checks.

`def` vs `async def` endpoints in FastAPI (a common point of confusion):
- `async def` runs ON the event loop. Use it when the endpoint awaits something slow
  (our HTTP check). Never call slow *blocking* code in it, or every request stalls.
- Plain `def` runs in a worker thread pool, so blocking code there is fine.
Our database driver (sqlite3) is blocking, but SQLite queries on a small local file take
well under a millisecond, so we accept brief blocking inside the async endpoints below.
A larger app would use an async driver (e.g. aiosqlite / asyncpg) instead.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Check, Monitor
from app.scheduler import schedule_monitor, unschedule_monitor
from app.schemas import CheckOut, MonitorCreate, MonitorOut, MonitorUpdate
from app.services import latest_checks_by_monitor, run_check_for_monitor
from app.url_safety import UnsafeUrlError, assert_url_is_safe

router = APIRouter(prefix="/monitors", tags=["monitors"])

# `Annotated[Session, Depends(get_db)]` tells FastAPI: "call get_db() and pass the
# result in". Giving it a name avoids repeating the Depends(...) in every signature.
DbSession = Annotated[Session, Depends(get_db)]


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


@router.post("", response_model=MonitorOut, status_code=status.HTTP_201_CREATED)
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
    monitor.is_active = payload.is_active
    db.commit()
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


@router.post("/{monitor_id}/check", response_model=CheckOut)
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
