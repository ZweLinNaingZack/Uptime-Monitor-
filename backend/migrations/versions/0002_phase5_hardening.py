"""Phase 5: failure counting, login sessions, and alert channels set from the dashboard.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("monitors") as batch:
        batch.add_column(
            sa.Column("consecutive_failures", sa.Integer(), server_default="0", nullable=False)
        )

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_auth_sessions_token_hash", "auth_sessions", ["token_hash"], unique=True)
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])

    op.create_table(
        "alert_channel_settings",
        sa.Column("name", sa.String(20), primary_key=True),
        sa.Column("secret", sa.Text(), nullable=False),
        sa.Column("chat_id", sa.String(100), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("alert_channel_settings")
    op.drop_table("auth_sessions")
    with op.batch_alter_table("monitors") as batch:
        batch.drop_column("consecutive_failures")
