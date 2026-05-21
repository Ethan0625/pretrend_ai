from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest
from sqlalchemy import Engine, text

from pretrend.observability.similarity.columns import (
    REGIME_SIMILARITY_FEATURE_COLUMNS,
)
from pretrend.observability.similarity.builder import (
    build_similarity_gold,
    build_similarity_regime,
    cosine_topn,
)
from tests.observability.db_test_utils import isolated_test_engine


REQUIRED_TABLES = {
    "similarity_regime",
    "similarity_gold",
    "gold_market_state_similarity_feature",
    "gold_eod_features",
    "gold_macro_features",
}


@pytest.fixture(scope="module")
def pg_engine() -> Engine:
    return isolated_test_engine(REQUIRED_TABLES)


@pytest.fixture()
def clean_tables(pg_engine: Engine) -> None:
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE similarity_regime"))
        conn.execute(text("TRUNCATE similarity_gold"))
        conn.execute(text("TRUNCATE gold_market_state_similarity_feature"))
        conn.execute(text("TRUNCATE gold_eod_features"))
        conn.execute(text("TRUNCATE gold_macro_features"))


def test_cosine_topn_basic() -> None:
    query_date = date(2026, 5, 1)
    rows = cosine_topn(
        np.array([1.0, 0.0]),
        np.array([[1.0, 0.0], [0.0, 1.0]]),
        [query_date - timedelta(days=40), query_date - timedelta(days=60)],
        query_date,
        n=2,
    )

    assert rows[0]["rank"] == 1
    assert rows[0]["score"] == 1.0
    assert rows[0]["gap_days"] == 40


def test_cosine_topn_min_gap_filter() -> None:
    query_date = date(2026, 5, 1)
    rows = cosine_topn(
        np.array([1.0, 0.0]),
        np.array([[1.0, 0.0], [1.0, 0.0]]),
        [query_date - timedelta(days=10), query_date - timedelta(days=40)],
        query_date,
    )

    assert len(rows) == 1
    assert rows[0]["gap_days"] == 40


def test_cosine_topn_skip_negative() -> None:
    query_date = date(2026, 5, 1)
    rows = cosine_topn(
        np.array([1.0, 0.0]),
        np.array([[-1.0, 0.0], [0.0, 0.0]]),
        [query_date - timedelta(days=40), query_date - timedelta(days=50)],
        query_date,
    )

    assert len(rows) == 1
    assert rows[0]["score"] == 0.0


def test_build_similarity_regime_idempotent(pg_engine: Engine, clean_tables: None) -> None:
    _insert_regime_history(pg_engine)

    first = build_similarity_regime(date(2026, 3, 1), date(2026, 3, 1), pg_engine)
    second = build_similarity_regime(date(2026, 3, 1), date(2026, 3, 1), pg_engine)

    assert first == {"rows_upserted": 1, "query_count": 1, "view": "regime"}
    assert second == first
    assert _count_rows(pg_engine, "similarity_regime") == 1


def test_build_similarity_gold_idempotent(pg_engine: Engine, clean_tables: None) -> None:
    _insert_gold_history(pg_engine)

    first = build_similarity_gold(date(2026, 3, 1), date(2026, 3, 1), pg_engine)
    second = build_similarity_gold(date(2026, 3, 1), date(2026, 3, 1), pg_engine)

    assert first == {"rows_upserted": 1, "query_count": 1, "view": "gold"}
    assert second == first
    assert _count_rows(pg_engine, "similarity_gold") == 1


def test_build_similarity_regime_replaces_existing(
    pg_engine: Engine,
    clean_tables: None,
) -> None:
    _insert_regime_history(pg_engine)
    query_date = date(2026, 3, 1)
    with pg_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO similarity_regime
                  (query_date, neighbor_date, rank, score, gap_days, built_at)
                VALUES
                  (:query_date, :neighbor_date, 1, 0.1, 59, '2026-05-14T00:00:00+00:00')
                """
            ),
            {
                "query_date": query_date,
                "neighbor_date": date(2026, 1, 1),
            },
        )

    result = build_similarity_regime(query_date, query_date, pg_engine)

    assert result["rows_upserted"] == 1
    with pg_engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT COUNT(*), MIN(score)
                FROM similarity_regime
                WHERE query_date = :query_date
                """
            ),
            {"query_date": query_date},
        ).one()
    assert row[0] == 1
    assert row[1] > 0.1


def _count_rows(engine: Engine, table_name: str) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one())


def _insert_regime_history(engine: Engine) -> None:
    columns = ["trade_date", *REGIME_SIMILARITY_FEATURE_COLUMNS, "built_at"]
    value_columns = ", ".join(f":{column}" for column in columns)
    sql = text(
        f"""
        INSERT INTO gold_market_state_similarity_feature
          ({", ".join(columns)})
        VALUES ({value_columns})
        """
    )
    rows = []
    for idx, trade_date in enumerate(
        [date(2026, 1, 1), date(2026, 1, 20), date(2026, 3, 1)]
    ):
        row = {
            column: _regime_value(column_index, idx)
            for column_index, column in enumerate(REGIME_SIMILARITY_FEATURE_COLUMNS)
        }
        row.update({"trade_date": trade_date, "built_at": "2026-05-14T00:00:00+00:00"})
        rows.append(row)
    with engine.begin() as conn:
        conn.execute(sql, rows)


def _regime_value(column_index: int, row_index: int) -> float:
    if row_index == 0:
        return float(column_index + 1)
    if row_index == 1:
        return float(column_index + 2)
    return float(column_index + 1.5)


def _insert_gold_history(engine: Engine) -> None:
    with engine.begin() as conn:
        for idx, trade_date in enumerate(
            [date(2026, 1, 1), date(2026, 1, 20), date(2026, 3, 1)]
        ):
            conn.execute(
                text(
                    """
                    INSERT INTO gold_eod_features
                      (symbol, trade_date, ret_5d, ret_20d, vol_20d, vol_60d,
                       ma_ratio_5_20, rsi_14, volume_zscore_20d,
                       is_trading_day, is_missing_imputed, is_outlier, is_partial_day,
                       asset_group, asset_name, run_id_gold, ingestion_ts_gold)
                    VALUES
                      (:symbol, :trade_date, :ret_5d, :ret_20d, :vol_20d, :vol_60d,
                       :ma_ratio_5_20, :rsi_14, :volume_zscore_20d,
                       true, false, false, false,
                       'EQUITY_INDEX', 'SP500', 'test', '2026-05-14T00:00:00+00:00')
                    """
                ),
                {
                    "symbol": f"SPY{idx}",
                    "trade_date": trade_date,
                    "ret_5d": idx + 1.0,
                    "ret_20d": idx + 1.1,
                    "vol_20d": idx + 1.2,
                    "vol_60d": idx + 1.3,
                    "ma_ratio_5_20": idx + 1.4,
                    "rsi_14": idx + 1.5,
                    "volume_zscore_20d": idx + 1.6,
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO gold_macro_features
                      (indicator_id, trade_date, selected_release_date,
                       delta_1m, delta_3m, delta_6m, zscore_12m,
                       direction, regime, release_source, is_assumption_based)
                    VALUES
                      ('CPI_US_ALL_ITEMS_SA', :trade_date, :selected_release_date,
                       :delta_1m, :delta_3m, :delta_6m, :zscore_12m,
                       'up', 'easing', 'econ_events', false)
                    """
                ),
                {
                    "trade_date": trade_date,
                    "selected_release_date": date(2025, 12, 31),
                    "delta_1m": idx + 2.0,
                    "delta_3m": idx + 2.1,
                    "delta_6m": idx + 2.2,
                    "zscore_12m": idx + 2.3,
                },
            )
