"""Add Phase 3 idempotency, retries, and attempts.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE job_status ADD VALUE IF NOT EXISTS 'RETRYING'")
    op.execute("ALTER TYPE job_status ADD VALUE IF NOT EXISTS 'DEAD_LETTERED'")
    op.drop_constraint("dataset_versions_input_object_key_key", "dataset_versions", type_="unique")
    op.add_column("jobs", sa.Column("idempotency_key", sa.String(200), nullable=True))
    op.add_column("jobs", sa.Column("request_fingerprint", sa.String(64), nullable=True))
    op.add_column(
        "jobs", sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "jobs", sa.Column("max_retries", sa.Integer(), server_default="3", nullable=False)
    )
    op.add_column("jobs", sa.Column("next_retry_at", sa.DateTime(timezone=True)))
    op.add_column("jobs", sa.Column("error_code", sa.String(100)))
    op.create_unique_constraint("uq_jobs_idempotency_key", "jobs", ["idempotency_key"])
    op.create_table(
        "job_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("duration_ms", sa.BigInteger()),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "attempt_number", name="uq_job_attempt_number"),
    )
    op.create_index("ix_job_attempts_job_id", "job_attempts", ["job_id"])


def downgrade() -> None:
    op.drop_table("job_attempts")
    op.drop_constraint("uq_jobs_idempotency_key", "jobs", type_="unique")
    op.drop_column("jobs", "error_code")
    op.drop_column("jobs", "next_retry_at")
    op.drop_column("jobs", "max_retries")
    op.drop_column("jobs", "retry_count")
    op.drop_column("jobs", "request_fingerprint")
    op.drop_column("jobs", "idempotency_key")
    op.create_unique_constraint(
        "dataset_versions_input_object_key_key", "dataset_versions", ["input_object_key"]
    )
