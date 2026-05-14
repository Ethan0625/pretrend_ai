"""explainability cache

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-14 00:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "explainability_cache",
        sa.Column("use_case", sa.Text(), nullable=False),
        sa.Column("query_date", sa.Date(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("report_json", postgresql.JSONB(), nullable=False),
        sa.Column("output_hash", sa.Text(), nullable=False),
        sa.Column("built_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "use_case",
            "query_date",
            "model_id",
            "prompt_version",
            name="pk_explainability_cache",
        ),
        sa.CheckConstraint(
            "use_case IN ('similarity_regime','similarity_gold','regime','macro')",
            name="ck_explainability_cache_use_case",
        ),
    )
    op.execute(
        "SELECT create_hypertable("
        "'explainability_cache', "
        "'query_date', "
        "chunk_time_interval => INTERVAL '1 year'"
        ");"
    )
    op.create_index(
        "ix_explainability_cache_query_date_brin",
        "explainability_cache",
        ["query_date"],
        postgresql_using="brin",
    )
    op.create_index(
        "ix_explainability_cache_query_date_use_case",
        "explainability_cache",
        ["query_date", "use_case"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_explainability_cache_query_date_use_case",
        table_name="explainability_cache",
    )
    op.drop_index(
        "ix_explainability_cache_query_date_brin",
        table_name="explainability_cache",
    )
    op.drop_table("explainability_cache")
