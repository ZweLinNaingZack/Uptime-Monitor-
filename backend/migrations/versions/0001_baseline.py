"""The schema as it was at the end of Phase 4.

Unlike a normal migration, this one looks before it acts, because databases made before
Alembic arrived already have some or all of these tables. It creates what is missing and
leaves the rest alone, so an old database and an empty one both end up the same.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())

    if "monitors" not in tables:
        op.create_table(
            "monitors",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("url", sa.String(2048), nullable=False),
            sa.Column("interval_seconds", sa.Integer(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("in_maintenance", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("alert_state", sa.String(10), nullable=True),
            sa.CheckConstraint(
                "interval_seconds BETWEEN 30 AND 86400", name="ck_monitors_interval_range"
            ),
        )
    else:
        existing = {column["name"] for column in inspector.get_columns("monitors")}
        if "in_maintenance" not in existing:
            op.add_column(
                "monitors",
                sa.Column("in_maintenance", sa.Boolean(), server_default=sa.false(), nullable=False),
            )
        if "alert_state" not in existing:
            op.add_column("monitors", sa.Column("alert_state", sa.String(10), nullable=True))

    if "checks" not in tables:
        op.create_table(
            "checks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "monitor_id",
                sa.Integer(),
                sa.ForeignKey("monitors.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("status_code", sa.Integer(), nullable=True),
            sa.Column("response_ms", sa.Integer(), nullable=True),
            sa.Column("is_up", sa.Boolean(), nullable=False),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("checked_at", sa.DateTime(), nullable=False),
            sa.Column(
                "during_maintenance", sa.Boolean(), server_default=sa.false(), nullable=False
            ),
        )
        op.create_index(
            "ix_checks_monitor_id_checked_at", "checks", ["monitor_id", "checked_at"]
        )
    elif "during_maintenance" not in {c["name"] for c in inspector.get_columns("checks")}:
        op.add_column(
            "checks",
            sa.Column(
                "during_maintenance", sa.Boolean(), server_default=sa.false(), nullable=False
            ),
        )

    if "alert_events" not in tables:
        op.create_table(
            "alert_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "monitor_id",
                sa.Integer(),
                sa.ForeignKey("monitors.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("kind", sa.String(10), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_alert_events_created_at", "alert_events", ["created_at"])
        op.create_index("ix_alert_events_monitor_id", "alert_events", ["monitor_id"])


def downgrade() -> None:
    op.drop_table("alert_events")
    op.drop_table("checks")
    op.drop_table("monitors")
