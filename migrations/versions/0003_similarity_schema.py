"""similarity schema

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-14 00:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


INTEGER_FEATURE_COLUMNS = [
    "long_phase_expansion",
    "long_phase_late_cycle",
    "long_phase_slowdown",
    "long_phase_recession",
    "long_phase_recovery",
    "long_phase_unknown",
    "mid_regime_code",
    "short_signal_code",
    "run_universe_flag",
    "risk_gate_flag",
    "rot_sp500_state_code",
    "rot_nasdaq100_state_code",
    "rot_dow30_state_code",
    "rot_us_dividend_state_code",
    "rot_russell2000_state_code",
    "rot_us_dividend_select_state_code",
    "rot_us_dividend_appreciation_state_code",
    "rot_south_korea_state_code",
    "rot_china_state_code",
    "rot_japan_state_code",
    "rot_india_state_code",
    "rot_gold_state_code",
    "rot_gold_miners_state_code",
    "rot_silver_state_code",
    "rot_crude_oil_state_code",
    "rot_oil_producers_state_code",
    "rot_natural_gas_state_code",
    "rot_agriculture_state_code",
    "rot_us_treasury_20y_state_code",
    "rot_us_high_yield_state_code",
    "rot_us_investment_grade_state_code",
    "rot_us_treasury_1_3y_state_code",
    "rot_us_tips_state_code",
    "rot_health_care_state_code",
    "rot_energy_state_code",
    "rot_semiconductor_state_code",
    "rot_financials_state_code",
    "rot_regional_banks_state_code",
    "rot_nuclear_state_code",
    "rot_information_tech_state_code",
    "rot_materials_state_code",
    "rot_consumer_discretionary_state_code",
    "rot_consumer_staples_state_code",
    "rot_communication_services_state_code",
    "rot_real_estate_state_code",
    "rot_utilities_state_code",
    "rot_industrials_state_code",
]

FLOAT_FEATURE_COLUMNS = [
    "long_phase_confidence",
    "mid_regime_confidence",
    "short_signal_confidence",
    "state_age_days",
    "sojourn_prob_5d",
    "sojourn_prob_10d",
    "sojourn_prob_20d",
    "sojourn_prob_60d",
    "sojourn_prob_120d",
    "transition_hazard_5d",
    "transition_hazard_10d",
    "transition_hazard_20d",
    "transition_hazard_60d",
    "transition_hazard_120d",
]


def _create_similarity_result_table(table_name: str) -> None:
    op.create_table(
        table_name,
        sa.Column("query_date", sa.Date(), nullable=False),
        sa.Column("neighbor_date", sa.Date(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("gap_days", sa.Integer(), nullable=False),
        sa.Column("built_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "query_date",
            "neighbor_date",
            name=f"pk_{table_name}",
        ),
        sa.CheckConstraint(
            "rank >= 1 AND rank <= 1000",
            name=f"ck_{table_name}_rank",
        ),
        sa.CheckConstraint(
            "score >= 0.0 AND score <= 1.0",
            name=f"ck_{table_name}_score",
        ),
        sa.CheckConstraint(
            "gap_days >= 30",
            name=f"ck_{table_name}_min_gap",
        ),
        sa.UniqueConstraint(
            "query_date",
            "rank",
            name=f"uq_{table_name}_query_rank",
        ),
    )
    op.execute(
        "SELECT create_hypertable("
        f"'{table_name}', "
        "'query_date', "
        "chunk_time_interval => INTERVAL '1 year'"
        ");"
    )
    op.create_index(
        f"ix_{table_name}_query_date_brin",
        table_name,
        ["query_date"],
        postgresql_using="brin",
    )
    op.create_index(
        f"ix_{table_name}_query_date_rank",
        table_name,
        ["query_date", "rank"],
    )


def upgrade() -> None:
    op.create_table(
        "gold_market_state_similarity_feature",
        sa.Column("trade_date", sa.Date(), nullable=False),
        *[
            sa.Column(column, sa.Integer(), nullable=True)
            for column in INTEGER_FEATURE_COLUMNS
        ],
        *[
            sa.Column(column, sa.Float(), nullable=True)
            for column in FLOAT_FEATURE_COLUMNS
        ],
        sa.Column("built_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "trade_date",
            name="pk_gold_market_state_similarity_feature",
        ),
    )
    op.execute(
        "SELECT create_hypertable("
        "'gold_market_state_similarity_feature', "
        "'trade_date', "
        "chunk_time_interval => INTERVAL '1 year'"
        ");"
    )
    op.create_index(
        "ix_gold_market_state_similarity_feature_trade_date_brin",
        "gold_market_state_similarity_feature",
        ["trade_date"],
        postgresql_using="brin",
    )

    _create_similarity_result_table("similarity_regime")
    _create_similarity_result_table("similarity_gold")


def downgrade() -> None:
    op.drop_index(
        "ix_similarity_gold_query_date_rank",
        table_name="similarity_gold",
    )
    op.drop_index(
        "ix_similarity_gold_query_date_brin",
        table_name="similarity_gold",
    )
    op.drop_table("similarity_gold")

    op.drop_index(
        "ix_similarity_regime_query_date_rank",
        table_name="similarity_regime",
    )
    op.drop_index(
        "ix_similarity_regime_query_date_brin",
        table_name="similarity_regime",
    )
    op.drop_table("similarity_regime")

    op.drop_index(
        "ix_gold_market_state_similarity_feature_trade_date_brin",
        table_name="gold_market_state_similarity_feature",
    )
    op.drop_table("gold_market_state_similarity_feature")
