"""gold schema

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-13 00:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gold_macro_features",
        sa.Column("indicator_id", sa.Text(), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("selected_observation_date", sa.Date(), nullable=True),
        sa.Column("selected_value", sa.Float(), nullable=True),
        sa.Column("selected_release_date", sa.Date(), nullable=True),
        sa.Column("delta_1m", sa.Float(), nullable=True),
        sa.Column("delta_3m", sa.Float(), nullable=True),
        sa.Column("delta_6m", sa.Float(), nullable=True),
        sa.Column("direction", sa.Text(), nullable=True),
        sa.Column("regime", sa.Text(), nullable=True),
        sa.Column("zscore_12m", sa.Float(), nullable=True),
        sa.Column("release_source", sa.Text(), nullable=True),
        sa.Column("is_assumption_based", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint(
            "indicator_id",
            "trade_date",
            name="pk_gold_macro_features",
        ),
        sa.CheckConstraint(
            "selected_release_date < trade_date",
            name="ck_gold_macro_features_pit",
        ),
        sa.CheckConstraint(
            "direction IN ('up','down','flat')",
            name="ck_gold_macro_features_direction",
        ),
        sa.CheckConstraint(
            "regime IN ('tightening','easing','neutral')",
            name="ck_gold_macro_features_regime",
        ),
        sa.CheckConstraint(
            "release_source IN ('econ_events','fred_vintages','assumed_t_plus_1')",
            name="ck_gold_macro_features_release_source",
        ),
    )
    op.execute(
        "SELECT create_hypertable("
        "'gold_macro_features', "
        "'trade_date', "
        "chunk_time_interval => INTERVAL '1 month'"
        ");"
    )
    op.create_index(
        "ix_gold_macro_features_trade_date_brin",
        "gold_macro_features",
        ["trade_date"],
        postgresql_using="brin",
    )
    op.create_index(
        "ix_gold_macro_features_indicator_id",
        "gold_macro_features",
        ["indicator_id"],
    )

    op.create_table(
        "gold_eod_features",
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("open", sa.Float(), nullable=True),
        sa.Column("high", sa.Float(), nullable=True),
        sa.Column("low", sa.Float(), nullable=True),
        sa.Column("close", sa.Float(), nullable=True),
        sa.Column("adj_close", sa.Float(), nullable=True),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.Text(), nullable=True),
        sa.Column("prev_adj_close", sa.Float(), nullable=True),
        sa.Column("ret_1d", sa.Float(), nullable=True),
        sa.Column("log_ret_1d", sa.Float(), nullable=True),
        sa.Column("ret_5d", sa.Float(), nullable=True),
        sa.Column("ret_20d", sa.Float(), nullable=True),
        sa.Column("vol_20d", sa.Float(), nullable=True),
        sa.Column("vol_60d", sa.Float(), nullable=True),
        sa.Column("ma_5", sa.Float(), nullable=True),
        sa.Column("ma_20", sa.Float(), nullable=True),
        sa.Column("ma_60", sa.Float(), nullable=True),
        sa.Column("ma_120", sa.Float(), nullable=True),
        sa.Column("ma_ratio_5_20", sa.Float(), nullable=True),
        sa.Column("atr_14", sa.Float(), nullable=True),
        sa.Column("rsi_14", sa.Float(), nullable=True),
        sa.Column("intraday_range", sa.Float(), nullable=True),
        sa.Column("gap_open", sa.Float(), nullable=True),
        sa.Column("volume_zscore_20d", sa.Float(), nullable=True),
        sa.Column("is_trading_day", sa.Boolean(), nullable=False),
        sa.Column("is_missing_imputed", sa.Boolean(), nullable=False),
        sa.Column("is_outlier", sa.Boolean(), nullable=False),
        sa.Column("is_partial_day", sa.Boolean(), nullable=False),
        sa.Column("asset_group", sa.Text(), nullable=False),
        sa.Column("asset_name", sa.Text(), nullable=False),
        sa.Column("asset_subtype", sa.Text(), nullable=True),
        sa.Column("run_id_gold", sa.Text(), nullable=False),
        sa.Column("ingestion_ts_gold", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "symbol",
            "trade_date",
            name="pk_gold_eod_features",
        ),
    )
    op.execute(
        "SELECT create_hypertable("
        "'gold_eod_features', "
        "'trade_date', "
        "chunk_time_interval => INTERVAL '1 month'"
        ");"
    )
    op.create_index(
        "ix_gold_eod_features_trade_date_brin",
        "gold_eod_features",
        ["trade_date"],
        postgresql_using="brin",
    )
    op.create_index(
        "ix_gold_eod_features_symbol",
        "gold_eod_features",
        ["symbol"],
    )


def downgrade() -> None:
    op.drop_index("ix_gold_eod_features_symbol", table_name="gold_eod_features")
    op.drop_index(
        "ix_gold_eod_features_trade_date_brin",
        table_name="gold_eod_features",
    )
    op.drop_table("gold_eod_features")

    op.drop_index(
        "ix_gold_macro_features_indicator_id",
        table_name="gold_macro_features",
    )
    op.drop_index(
        "ix_gold_macro_features_trade_date_brin",
        table_name="gold_macro_features",
    )
    op.drop_table("gold_macro_features")
