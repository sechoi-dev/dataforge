"""Add durable scheduling and worker leases.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE job_status ADD VALUE IF NOT EXISTS 'SCHEDULED'")
    op.add_column("jobs", sa.Column("priority", sa.Integer(), server_default="0", nullable=False))
    op.add_column("jobs", sa.Column("scheduled_at", sa.DateTime(timezone=True)))
    op.add_column("jobs", sa.Column("queued_at", sa.DateTime(timezone=True)))
    op.add_column("jobs", sa.Column("worker_id", sa.String(255)))
    op.add_column("jobs", sa.Column("lease_expires_at", sa.DateTime(timezone=True)))
    op.create_index("ix_jobs_scheduled_at", "jobs", ["scheduled_at"])
    op.create_index("ix_jobs_lease_expires_at", "jobs", ["lease_expires_at"])
    op.add_column("job_attempts", sa.Column("worker_id", sa.String(255)))


def downgrade() -> None:
    op.drop_column("job_attempts", "worker_id")
    op.drop_index("ix_jobs_lease_expires_at", table_name="jobs")
    op.drop_index("ix_jobs_scheduled_at", table_name="jobs")
    op.drop_column("jobs", "lease_expires_at")
    op.drop_column("jobs", "worker_id")
    op.drop_column("jobs", "queued_at")
    op.drop_column("jobs", "scheduled_at")
    op.drop_column("jobs", "priority")
