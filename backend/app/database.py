"""Database engine, session factory and the declarative Base class.

SQLAlchemy has two layers worth knowing:
- The *engine* owns the connection pool. Create it once per process.
- A *session* is a short-lived "unit of work": you load/add objects, then commit.
  Create one per request (or per background job) and close it when done.
"""

from collections.abc import Iterator
from datetime import UTC, datetime

from sqlalchemy import DateTime, create_engine, event, inspect, text
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from app.config import settings

engine = create_engine(
    settings.database_url,
    # SQLite's Python driver refuses by default to use a connection from a thread other
    # than the one that created it. FastAPI runs plain `def` endpoints in a thread pool,
    # so we turn that check off; SQLAlchemy's pool hands each connection to one user at a time.
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
    """Turn on foreign-key enforcement for every new SQLite connection.

    Surprise: SQLite ignores FOREIGN KEY constraints (including ON DELETE CASCADE)
    unless you run this PRAGMA, and the setting is per connection, not per database
    file. That is why it lives in a "connect" event instead of running once.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# expire_on_commit=False: after commit(), keep the loaded attribute values on our objects.
# Otherwise touching `monitor.name` after commit would trigger a new SELECT, which fails
# if the session has been closed by then.
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """All ORM models inherit from this, so `Base.metadata` knows every table."""


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """A DateTime column that always stores and returns UTC.

    SQLite has no real timezone-aware datetime type, so a plain DateTime column gives
    back "naive" datetimes (no tzinfo) and you can no longer tell if 12:00 meant UTC or
    local time. This type converts to naive UTC on the way in and re-attaches UTC on the
    way out, so the rest of the code only ever sees timezone-aware UTC values.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Refusing to store a naive datetime; use datetime.now(UTC).")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC)


# Columns added after the first release: (table, column, SQL definition).
_ADDED_COLUMNS = (
    ("monitors", "in_maintenance", "BOOLEAN NOT NULL DEFAULT 0"),
    ("monitors", "alert_state", "VARCHAR(10)"),
    ("checks", "during_maintenance", "BOOLEAN NOT NULL DEFAULT 0"),
)


def ensure_schema() -> None:
    """Create missing tables, then add any columns that an older database doesn't have.

    `create_all` only creates tables that don't exist; it never changes existing ones.
    Without the second step, a database from an earlier version would crash on the first
    query with "no such column". Adding a column keeps all existing rows, so this is safe
    to run on every startup. Real projects use a migration tool (Alembic), which also
    handles renames and removals. It is on the roadmap.
    """
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    missing = [
        (table, column, definition)
        for table, column, definition in _ADDED_COLUMNS
        if column not in {c["name"] for c in inspector.get_columns(table)}
    ]
    with engine.begin() as connection:
        for table, column, definition in missing:
            # The names come from the constant above, never from user input, so building
            # this SQL string is safe here.
            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed afterwards.

    The `yield` makes this a generator dependency. FastAPI runs the code before `yield`
    before your endpoint, injects the session, and runs the `finally` block after the
    response, even if the endpoint raised an exception.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
