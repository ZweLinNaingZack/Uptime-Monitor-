"""Glue between the checker (network) and the database.

Both the "Check now" endpoint and the scheduler call `run_check_for_monitor`, so the
rules for running a check live in exactly one place.
"""

import logging

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.checker import perform_check
from app.database import SessionLocal, utcnow
from app.models import Check, Monitor

logger = logging.getLogger(__name__)


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
        if db.get(Monitor, monitor_id) is None:
            logger.info("Monitor %s was deleted during its check; discarding result", monitor_id)
            return None
        check = Check(
            monitor_id=monitor_id,
            status_code=result.status_code,
            response_ms=result.response_ms,
            is_up=result.is_up,
            error=result.error,
            checked_at=checked_at,
        )
        db.add(check)
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
