"""Add job progress, cancellation, and event history.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE job_status ADD VALUE IF NOT EXISTS 'CANCELLED'")
    op.add_column(
        "jobs", sa.Column("progress_percent", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "jobs",
        sa.Column("progress_message", sa.String(255), server_default="Queued", nullable=False),
    )
    op.add_column(
        "jobs", sa.Column("current_stage", sa.String(100), server_default="queued", nullable=False)
    )
    op.add_column("jobs", sa.Column("cancel_requested_at", sa.DateTime(timezone=True)))
    op.add_column("jobs", sa.Column("cancelled_at", sa.DateTime(timezone=True)))
    op.create_table(
        "job_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_events_job_id", "job_events", ["job_id"])


def downgrade() -> None:
    op.drop_table("job_events")
    op.drop_column("jobs", "cancelled_at")
    op.drop_column("jobs", "cancel_requested_at")
    op.drop_column("jobs", "current_stage")
    op.drop_column("jobs", "progress_message")
    op.drop_column("jobs", "progress_percent")
