"""Add Phase 4 validation rules, results, score, and HTML report key.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    rule_type = sa.Enum(
        "NOT_NULL",
        "UNIQUE",
        "MIN_VALUE",
        "MAX_VALUE",
        "RANGE",
        "ALLOWED_VALUES",
        "REGEX",
        "EXPECTED_TYPE",
        "DATE_PARSEABLE",
        "MINIMUM_ROW_COUNT",
        "MAXIMUM_MISSING_PERCENTAGE",
        "MAXIMUM_DUPLICATE_PERCENTAGE",
        name="validation_rule_type",
    )
    severity = sa.Enum("INFO", "WARNING", "CRITICAL", name="validation_severity")
    result_severity = sa.Enum(
        "INFO", "WARNING", "CRITICAL", name="validation_result_severity"
    )
    op.add_column("dataset_versions", sa.Column("quality_score", sa.Float()))
    op.add_column(
        "dataset_versions", sa.Column("html_report_object_key", sa.String(500))
    )
    op.create_unique_constraint(
        "uq_dataset_versions_html_report_key",
        "dataset_versions",
        ["html_report_object_key"],
    )
    op.create_table(
        "validation_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("column_name", sa.String(255)),
        sa.Column("rule_type", rule_type, nullable=False),
        sa.Column("parameters_json", sa.JSON(), nullable=False),
        sa.Column("severity", severity, nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_validation_rules_dataset_id", "validation_rules", ["dataset_id"])
    op.create_table(
        "validation_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version_id", sa.Uuid(), nullable=False),
        sa.Column("validation_rule_id", sa.Uuid()),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("check_name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("severity", result_severity, nullable=False),
        sa.Column("affected_count", sa.BigInteger(), nullable=False),
        sa.Column("affected_percentage", sa.Float(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"], ["dataset_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["validation_rule_id"], ["validation_rules.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_validation_results_dataset_version_id",
        "validation_results",
        ["dataset_version_id"],
    )
    op.create_index(
        "ix_validation_results_validation_rule_id",
        "validation_results",
        ["validation_rule_id"],
    )


def downgrade() -> None:
    op.drop_table("validation_results")
    op.drop_table("validation_rules")
    op.drop_constraint(
        "uq_dataset_versions_html_report_key", "dataset_versions", type_="unique"
    )
    op.drop_column("dataset_versions", "html_report_object_key")
    op.drop_column("dataset_versions", "quality_score")
    sa.Enum(name="validation_result_severity").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="validation_severity").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="validation_rule_type").drop(op.get_bind(), checkfirst=True)
