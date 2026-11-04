"""ORM models: Python classes that map to database tables (SQLAlchemy 2.0 style).

`Mapped[int]` is a type hint that SQLAlchemy reads to build the column, and that your
editor/mypy read to know `monitor.id` is an int. `Mapped[int | None]` means nullable.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UTCDateTime, utcnow

MIN_INTERVAL_SECONDS = 30
MAX_INTERVAL_SECONDS = 86_400  # one day
DEFAULT_INTERVAL_SECONDS = 60


class Monitor(Base):
    __tablename__ = "monitors"
    # Validation also happens in the Pydantic schema; this constraint is the last line of
    # defence if some other code (or a manual SQL session) writes a bad value.
    __table_args__ = (
        CheckConstraint(
            f"interval_seconds BETWEEN {MIN_INTERVAL_SECONDS} AND {MAX_INTERVAL_SECONDS}",
            name="ck_monitors_interval_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    url: Mapped[str] = mapped_column(String(2048))
    interval_seconds: Mapped[int] = mapped_column(default=DEFAULT_INTERVAL_SECONDS)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    # Planned downtime: checks keep running, but alerts are silenced and the results
    # don't count towards the uptime statistics.
    in_maintenance: Mapped[bool] = mapped_column(default=False, server_default=false())
    # The state the alert system last accepted: "up", "down", or None before the first
    # check. It lives in the database so a restart can't cause a repeated alert.
    alert_state: Mapped[str | None] = mapped_column(String(10))

    # passive_deletes=True: "the database will delete the child rows (ON DELETE CASCADE),
    # so don't load every check into memory just to delete them one by one."
    checks: Mapped[list["Check"]] = relationship(
        back_populates="monitor",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    alert_events: Mapped[list["AlertEvent"]] = relationship(
        back_populates="monitor",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Check(Base):
    __tablename__ = "checks"
    # The history query is "checks of monitor X, newest first". A composite index on
    # (monitor_id, checked_at) lets SQLite jump straight to those rows already sorted.
    __table_args__ = (Index("ix_checks_monitor_id_checked_at", "monitor_id", "checked_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    monitor_id: Mapped[int] = mapped_column(ForeignKey("monitors.id", ondelete="CASCADE"))
    status_code: Mapped[int | None]  # None when we never got a response (timeout, DNS...)
    response_ms: Mapped[int | None]
    is_up: Mapped[bool]
    error: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    # True if the monitor was in maintenance when this check was saved. Stored per check
    # because the monitor's flag changes later, but this check's history must not.
    during_maintenance: Mapped[bool] = mapped_column(default=False, server_default=false())

    monitor: Mapped[Monitor] = relationship(back_populates="checks")


class AlertEvent(Base):
    """One state change worth telling someone about, and whether we managed to tell them.

    Why a table instead of just sending a message? This row is saved in the SAME database
    transaction as the check and the state change, and only then do we call Discord or
    Telegram. If the server crashes between those two steps, the "pending" row is still
    here and gets sent at the next startup, and if delivery fails, the failure is visible
    in the dashboard rather than lost. This is known as the "transactional outbox" pattern.
    """

    __tablename__ = "alert_events"
    __table_args__ = (Index("ix_alert_events_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    monitor_id: Mapped[int] = mapped_column(
        ForeignKey("monitors.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(10))  # "down" or "recovered"
    message: Mapped[str] = mapped_column(Text)
    # pending -> sent | partial | failed | no_channels (see AlertStatus in alerts.py)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    monitor: Mapped[Monitor] = relationship(back_populates="alert_events")
