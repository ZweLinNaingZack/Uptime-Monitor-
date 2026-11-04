"""Glue between the checker (network) and the database.

Both the "Check now" endpoint and the scheduler call `run_check_for_monitor`, so the
rules for running a check live in exactly one place.
"""

import logging
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.alerts import build_message, decide_alert, dispatch_alert
from app.checker import CheckResult, perform_check
from app.database import SessionLocal, utcnow
from app.models import AlertEvent, Check, Monitor

logger = logging.getLogger(__name__)


def _update_alert_state(
    monitor: Monitor, result: CheckResult, checked_at: datetime
) -> AlertEvent | None:
    """Compare a result to the monitor's alert state. Returns an event if it changed.

    A paused or in-maintenance monitor leaves `alert_state` completely untouched. That one
    rule gives the right behaviour when the period ends: the next check compares against
    the state from BEFORE it. If the site is now broken, you get a DOWN alert; if it broke
    and was fixed during maintenance, you hear nothing, because nothing changed for you.
    """
    if not monitor.is_active or monitor.in_maintenance:
        return None

    kind = decide_alert(monitor.alert_state, result.is_up)
    monitor.alert_state = "up" if result.is_up else "down"
    if kind is None:
        return None
    return AlertEvent(
        monitor_id=monitor.id,
        kind=kind,
        message=build_message(
            kind,
            monitor.name,
            monitor.url,
            checked_at,
            error=result.error,
            response_ms=result.response_ms,
        ),
    )


async def run_check_for_monitor(monitor_id: int) -> Check | None:
    """Check one monitor and store the result. Returns None if the monitor is gone.

    Notice the THREE separate steps. We deliberately do NOT keep a database session open
    while waiting for the network:
    - A check can take up to 10 s. Holding a session (and, with SQLite, possibly a lock)
      that long would block other writers for no reason.
    - Many checks run at the same time; each open session ties up a pooled connection.
    """
    # 1) Read what we need, then close the session (the `with` block closes it).
    with SessionLocal() as db:
        monitor = db.get(Monitor, monitor_id)
        if monitor is None:
            return None
        url = monitor.url

    # 2) The slow part: no database session is open here.
    checked_at = utcnow()
    result = await perform_check(url)

    # 3) Open a fresh session to save the result.
    with SessionLocal() as db:
        # The monitor may have been deleted while we were waiting on the network.
        monitor = db.get(Monitor, monitor_id)
        if monitor is None:
            logger.info("Monitor %s was deleted during its check; discarding result", monitor_id)
            return None
        check = Check(
            monitor_id=monitor_id,
            status_code=result.status_code,
            response_ms=result.response_ms,
            is_up=result.is_up,
            error=result.error,
            checked_at=checked_at,
            during_maintenance=monitor.in_maintenance,
        )
        db.add(check)
        # Saved in the same commit as the check: either all of it happens or none of it.
        alert_event = _update_alert_state(monitor, result, checked_at)
        if alert_event is not None:
            db.add(alert_event)
        try:
            db.commit()
        except IntegrityError:
            # Even after the check above, a DELETE can sneak in between the SELECT and
            # our INSERT. Because foreign keys are enforced (PRAGMA foreign_keys=ON), the
            # database refuses a check pointing at a missing monitor instead of storing
            # an orphan row. We treat that as "monitor deleted".
            db.rollback()
            logger.info("Monitor %s was deleted before its check was saved", monitor_id)
            return None

    # Only after the commit, and with the session closed: never hold a database session
    # during a network call, and never announce something that failed to save.
    if alert_event is not None:
        dispatch_alert(alert_event.id)
    return check


def latest_checks_by_monitor(db: Session, monitor_ids: list[int]) -> dict[int, Check]:
    """Return {monitor_id: newest Check} for the given monitors, in ONE query.

    The naive approach runs one query per monitor (the "N+1 queries" problem). Instead we
    use a window function: ROW_NUMBER() numbers each monitor's checks 1, 2, 3... from
    newest to oldest, and we keep only the rows numbered 1. Roughly this SQL:

        SELECT * FROM (
            SELECT checks.*, ROW_NUMBER() OVER (
                PARTITION BY monitor_id ORDER BY checked_at DESC, id DESC) AS rn
            FROM checks WHERE monitor_id IN (...)
        ) WHERE rn = 1
    """
    if not monitor_ids:
        return {}
    row_number = (
        func.row_number()
        .over(partition_by=Check.monitor_id, order_by=(Check.checked_at.desc(), Check.id.desc()))
        .label("rn")
    )
    ranked = (
        select(Check.id, row_number).where(Check.monitor_id.in_(monitor_ids)).subquery()
    )
    stmt = select(Check).join(ranked, Check.id == ranked.c.id).where(ranked.c.rn == 1)
    return {check.monitor_id: check for check in db.scalars(stmt)}
