"""Migrations, data retention and scheduling: the parts that work with the database."""

import sqlite3
from datetime import timedelta

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app import scheduler
from app.database import MIGRATIONS_DIR, Base, SessionLocal, engine, utcnow
from app.models import AlertEvent, AuthSession, Check, Monitor
from app.retention import prune_old_data


def migrate(db_path, revision="head", direction="upgrade"):
    """Run Alembic against a separate database file, not the one the app uses."""
    other_engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    with other_engine.begin() as connection:
        config.attributes["connection"] = connection
        getattr(command, direction)(config, revision)
    return other_engine


def test_the_models_match_the_migrations():
    # If someone changes models.py without writing a migration, this lists the difference.
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []


def test_a_database_from_before_alembic_keeps_its_rows(tmp_path):
    db = tmp_path / "phase3.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE monitors (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL,
            url VARCHAR(2048) NOT NULL, interval_seconds INTEGER NOT NULL,
            is_active BOOLEAN NOT NULL, created_at DATETIME NOT NULL);
        CREATE TABLE checks (id INTEGER PRIMARY KEY, monitor_id INTEGER NOT NULL
            REFERENCES monitors(id) ON DELETE CASCADE, status_code INTEGER, response_ms INTEGER,
            is_up BOOLEAN NOT NULL, error TEXT, checked_at DATETIME NOT NULL);
        INSERT INTO monitors VALUES (1, 'old', 'https://old.example', 60, 1, '2026-01-01 00:00:00');
        INSERT INTO checks VALUES (1, 1, 200, 50, 1, NULL, '2026-01-01 00:01:00');
        """
    )
    conn.close()

    inspector = inspect(migrate(db))
    assert {"alert_events", "auth_sessions", "alert_channel_settings", "alembic_version"} <= set(inspector.get_table_names())
    monitor_columns = {c["name"] for c in inspector.get_columns("monitors")}
    assert {"in_maintenance", "alert_state", "consecutive_failures"} <= monitor_columns

    conn = sqlite3.connect(db)
    assert conn.execute("select name, in_maintenance, consecutive_failures from monitors").fetchall() == [("old", 0, 0)]
    assert conn.execute("select count(*) from checks").fetchone() == (1,)
    conn.close()


def test_migrations_go_down_and_up_again(tmp_path):
    db = tmp_path / "fresh.db"
    migrate(db)
    migrate(db, "base", "downgrade")
    assert set(inspect(create_engine(f"sqlite:///{db.as_posix()}")).get_table_names()) == {"alembic_version"}
    migrate(db)


def test_retention_deletes_only_what_is_old_and_finished():
    old = utcnow() - timedelta(days=100)
    with SessionLocal() as db:
        monitor = Monitor(name="m", url="https://e.example", interval_seconds=60)
        db.add(monitor)
        db.flush()
        db.add_all([
            Check(monitor_id=monitor.id, is_up=True, checked_at=old),
            Check(monitor_id=monitor.id, is_up=True, checked_at=utcnow()),
            AlertEvent(monitor_id=monitor.id, kind="down", message="x", status="sent", created_at=old),
            AlertEvent(monitor_id=monitor.id, kind="down", message="x", status="pending", created_at=old),
            AuthSession(token_hash="a" * 64, expires_at=utcnow() - timedelta(minutes=1)),
            AuthSession(token_hash="b" * 64, expires_at=utcnow() + timedelta(days=1)),
        ])
        db.commit()

    result = prune_old_data()
    assert (result.checks, result.alert_events, result.sessions) == (1, 1, 1)
    with SessionLocal() as db:
        assert db.query(Check).count() == 1
        assert [e.status for e in db.query(AlertEvent)] == ["pending"]
        assert [s.token_hash[0] for s in db.query(AuthSession)] == ["b"]


def test_retention_zero_keeps_everything(override_settings):
    override_settings(retention_days=0)
    with SessionLocal() as db:
        monitor = Monitor(name="m", url="https://e.example", interval_seconds=60)
        db.add(monitor)
        db.flush()
        db.add(Check(monitor_id=monitor.id, is_up=True, checked_at=utcnow() - timedelta(days=3000)))
        db.commit()
    assert prune_old_data().checks == 0


def test_scheduler_has_one_job_per_monitor_plus_housekeeping(client):
    scheduler.schedule_monitor(41, 60)
    scheduler.schedule_monitor(41, 120)  # rescheduling replaces, never duplicates
    jobs = {job.id for job in scheduler.scheduler.get_jobs()}
    assert {"monitor-41", "housekeeping"} <= jobs
    scheduler.unschedule_monitor(41)
    scheduler.unschedule_monitor(41)  # a second time is harmless
    assert "monitor-41" not in {job.id for job in scheduler.scheduler.get_jobs()}
