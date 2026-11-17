"""Persist request correlation on asynchronous jobs.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("correlation_id", sa.String(128)))
    op.create_index("ix_jobs_correlation_id", "jobs", ["correlation_id"])


def downgrade() -> None:
    op.drop_index("ix_jobs_correlation_id", table_name="jobs")
    op.drop_column("jobs", "correlation_id")
