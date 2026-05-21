from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from sqlalchemy import Engine, text

from pretrend.observability.similarity.columns import (
    REGIME_SIMILARITY_FEATURE_COLUMNS,
)
from pretrend.observability.similarity.features import (
    GOLD_VIEW_COLUMNS,
    build_gold_view_features,
    build_regime_view_features,
    normalize_zscore,
)
from tests.observability.db_test_utils import isolated_test_engine


REQUIRED_TABLES = {
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
        conn.execute(text("TRUNCATE gold_market_state_similarity_feature"))
        conn.execute(text("TRUNCATE gold_eod_features"))
        conn.execute(text("TRUNCATE gold_macro_features"))


def test_regime_view_dim(pg_engine: Engine, clean_tables: None) -> None:
    _insert_regime_feature_rows(pg_engine)

    features = build_regime_view_features(
        pg_engine,
        [date(2026, 1, 1), date(2026, 2, 15)],
    )

    assert features.shape == (2, 61)
    assert list(features.columns) == list(REGIME_SIMILARITY_FEATURE_COLUMNS)


def test_gold_view_dim(pg_engine: Engine, clean_tables: None) -> None:
    _insert_gold_rows(pg_engine)

    features = build_gold_view_features(
        pg_engine,
        [date(2026, 1, 1), date(2026, 2, 15)],
    )

    assert features.shape == (2, 294)
    assert list(features.columns) == GOLD_VIEW_COLUMNS
    assert not any("cboe" in column for column in features.columns)


def test_zscore_null_to_zero() -> None:
    df = pd.DataFrame({"a": [1.0, None], "b": [None, None]})
    normalized = normalize_zscore(
        df,
        pd.Series({"a": 1.0, "b": 0.0}),
        pd.Series({"a": 2.0, "b": 1.0}),
    )

    assert normalized.loc[1, "a"] == 0.0
    assert normalized["b"].tolist() == [0.0, 0.0]


def test_zscore_mean_std() -> None:
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [2.0, 4.0, 6.0]})
    normalized = normalize_zscore(df, df.mean(), df.std(ddof=0))

    assert normalized.mean().abs().max() < 1e-12
    assert (normalized.std(ddof=0) - 1.0).abs().max() < 1e-12


def _insert_regime_feature_rows(engine: Engine) -> None:
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
    for idx, trade_date in enumerate([date(2026, 1, 1), date(2026, 2, 15)]):
        row = {column: float(idx + 1) for column in REGIME_SIMILARITY_FEATURE_COLUMNS}
        row.update({"trade_date": trade_date, "built_at": "2026-05-14T00:00:00+00:00"})
        rows.append(row)
    with engine.begin() as conn:
        conn.execute(sql, rows)


def _insert_gold_rows(engine: Engine) -> None:
    with engine.begin() as conn:
        for idx, trade_date in enumerate([date(2026, 1, 1), date(2026, 2, 15)]):
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
                       :asset_group, :asset_name, 'test', '2026-05-14T00:00:00+00:00')
                    """
                ),
                [
                    {
                        "symbol": f"SPY{idx}",
                        "trade_date": trade_date,
                        "ret_5d": idx + 0.1,
                        "ret_20d": idx + 0.2,
                        "vol_20d": idx + 0.3,
                        "vol_60d": idx + 0.4,
                        "ma_ratio_5_20": idx + 0.5,
                        "rsi_14": idx + 0.6,
                        "volume_zscore_20d": idx + 0.7,
                        "asset_group": "EQUITY_INDEX",
                        "asset_name": "SP500",
                    },
                    {
                        "symbol": f"VIX{idx}",
                        "trade_date": trade_date,
                        "ret_5d": 99.0,
                        "ret_20d": 99.0,
                        "vol_20d": 99.0,
                        "vol_60d": 99.0,
                        "ma_ratio_5_20": 99.0,
                        "rsi_14": 99.0,
                        "volume_zscore_20d": 99.0,
                        "asset_group": "VOLATILITY_INDEX",
                        "asset_name": "CBOE_VOLATILITY_INDEX",
                    },
                ],
            )
            conn.execute(
                text(
                    """
                    INSERT INTO gold_macro_features
                      (indicator_id, trade_date, selected_release_date,
                       delta_1m, delta_3m, delta_6m, zscore_12m,
                       direction, regime, release_source, is_assumption_based)
                    VALUES
                      (:indicator_id, :trade_date, :selected_release_date,
                       :delta_1m, :delta_3m, :delta_6m, :zscore_12m,
                       'up', 'easing', 'econ_events', false)
                    """
                ),
                {
                    "indicator_id": "CPI_US_ALL_ITEMS_SA",
                    "trade_date": trade_date,
                    "selected_release_date": date(2025, 12, 31),
                    "delta_1m": idx + 1.1,
                    "delta_3m": idx + 1.3,
                    "delta_6m": idx + 1.6,
                    "zscore_12m": idx + 1.2,
                },
            )
