"""similarity events explainability use case

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-21 00:00:00
"""
from __future__ import annotations

from alembic import op


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


NEW_USE_CASES = "'similarity_regime','similarity_gold','similarity_events','regime','macro'"
OLD_USE_CASES = "'similarity_regime','similarity_gold','regime','macro'"


def upgrade() -> None:
    op.drop_constraint(
        "ck_explainability_cache_use_case",
        "explainability_cache",
        type_="check",
    )
    op.create_check_constraint(
        "ck_explainability_cache_use_case",
        "explainability_cache",
        f"use_case IN ({NEW_USE_CASES})",
    )


def downgrade() -> None:
    op.execute("DELETE FROM explainability_cache WHERE use_case = 'similarity_events'")
    op.drop_constraint(
        "ck_explainability_cache_use_case",
        "explainability_cache",
        type_="check",
    )
    op.create_check_constraint(
        "ck_explainability_cache_use_case",
        "explainability_cache",
        f"use_case IN ({OLD_USE_CASES})",
    )
