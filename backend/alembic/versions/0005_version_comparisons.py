"""Add persisted dataset-version comparisons.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    status = sa.Enum("PROCESSING", "SUCCEEDED", "FAILED", name="comparison_status")
    op.create_table(
        "comparisons",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("left_version_id", sa.Uuid(), nullable=False),
        sa.Column("right_version_id", sa.Uuid(), nullable=False),
        sa.Column("status", status, nullable=False),
        sa.Column("selected_key_columns", sa.JSON(), nullable=False),
        sa.Column("normalize_text", sa.Boolean(), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("result_object_key", sa.String(500)),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["left_version_id"], ["dataset_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["right_version_id"], ["dataset_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "left_version_id",
            "right_version_id",
            "request_fingerprint",
            name="uq_comparison_request",
        ),
        sa.UniqueConstraint("result_object_key"),
    )
    op.create_index("ix_comparisons_left_version_id", "comparisons", ["left_version_id"])
    op.create_index("ix_comparisons_right_version_id", "comparisons", ["right_version_id"])
    op.create_index("ix_comparisons_status", "comparisons", ["status"])


def downgrade() -> None:
    op.drop_table("comparisons")
    sa.Enum(name="comparison_status").drop(op.get_bind(), checkfirst=True)
