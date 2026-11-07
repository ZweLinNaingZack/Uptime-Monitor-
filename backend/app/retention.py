"""Housekeeping: delete data we no longer need, so the database can't grow forever.

A monitor checking every 30 seconds adds about 2,880 rows a day, or a million a year.

The file on disk won't shrink after a delete. SQLite keeps the freed space and reuses it
for new rows, which is what we want here: the file simply stops growing.
"""

import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete

from app.config import settings
from app.database import SessionLocal, utcnow
from app.models import AlertEvent, AuthSession, Check

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PruneResult:
    checks: int
    alert_events: int
    sessions: int


def prune_old_data() -> PruneResult:
    """Delete expired logins, plus old checks and alerts if retention is switched on."""
    now = utcnow()
    with SessionLocal() as db:
        sessions = db.execute(delete(AuthSession).where(AuthSession.expires_at <= now)).rowcount
        checks = alert_events = 0
        if settings.retention_days > 0:
            cutoff = now - timedelta(days=settings.retention_days)
            checks = db.execute(delete(Check).where(Check.checked_at < cutoff)).rowcount
            # Keep "pending" alerts: they haven't been delivered yet.
            alert_events = db.execute(
                delete(AlertEvent).where(
                    AlertEvent.created_at < cutoff, AlertEvent.status != "pending"
                )
            ).rowcount
        db.commit()
    result = PruneResult(checks=checks, alert_events=alert_events, sessions=sessions)
    logger.info(
        "Housekeeping deleted %d check(s), %d alert(s), %d expired login(s)",
        result.checks,
        result.alert_events,
        result.sessions,
    )
    return result
