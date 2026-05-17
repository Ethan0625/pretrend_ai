from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from pretrend.pipeline.sync.gold_postgres import (
    _get_watermark,
    sync_gold_eod,
    sync_gold_macro,
)


@pytest.fixture(scope="module")
def pg_engine() -> Engine:
    try:
        from pretrend.config import get_settings
    except ModuleNotFoundError as exc:
        pytest.skip(f"postgres settings dependency unavailable: {exc}")

    try:
        database_url = get_settings().database_url
    except ValidationError as exc:
        pytest.skip(f"postgres settings unavailable for sync tests: {exc}")

    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            tables = conn.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name IN (
                        'gold_macro_features',
                        'gold_eod_features'
                      )
                    """
                )
            ).scalars().all()
    except SQLAlchemyError as exc:
        pytest.skip(f"postgres unavailable for sync tests: {exc}")

    if set(tables) != {"gold_macro_features", "gold_eod_features"}:
        pytest.skip("gold postgres tables are not migrated")
    return engine


@pytest.fixture(autouse=True)
def clean_gold_tables(pg_engine: Engine) -> None:
    with pg_engine.begin() as conn:
        conn.execute(
            text("TRUNCATE gold_macro_features, gold_eod_features")
        )


def _write_macro(root: Path, rows: list[dict]) -> None:
    df = pd.DataFrame(rows)
    for (year, month), part in df.groupby(
        [
            pd.to_datetime(df["trade_date"]).dt.year,
            pd.to_datetime(df["trade_date"]).dt.month,
        ]
    ):
        out_dir = root / f"year={year:04d}" / f"month={month:02d}"
        out_dir.mkdir(parents=True, exist_ok=True)
        part.to_parquet(out_dir / f"gold_macro_features_{year:04d}{month:02d}.parquet", index=False)


def _write_eod(root: Path, rows: list[dict]) -> None:
    df = pd.DataFrame(rows)
    for (symbol, year, month), part in df.groupby(
        [
            df["symbol"],
            pd.to_datetime(df["trade_date"]).dt.year,
            pd.to_datetime(df["trade_date"]).dt.month,
        ]
    ):
        out_dir = root / f"symbol={symbol}" / f"year={year:04d}" / f"month={month:02d}"
        out_dir.mkdir(parents=True, exist_ok=True)
        part.to_parquet(out_dir / f"gold_eod_features_{year:04d}{month:02d}.parquet", index=False)


def _macro_rows(value: float = 301.0) -> list[dict]:
    return [
        {
            "indicator_id": "CPI_US_ALL_ITEMS_SA",
            "trade_date": date(2024, 6, 10),
            "selected_observation_date": date(2024, 5, 1),
            "selected_value": 300.0,
            "selected_release_date": date(2024, 6, 1),
            "delta_1m": 1.0,
            "delta_3m": None,
            "delta_6m": None,
            "direction": "up",
            "regime": "neutral",
            "zscore_12m": None,
            "release_source": "econ_events",
            "is_assumption_based": False,
        },
        {
            "indicator_id": "CPI_US_ALL_ITEMS_SA",
            "trade_date": date(2024, 6, 11),
            "selected_observation_date": date(2024, 5, 1),
            "selected_value": value,
            "selected_release_date": date(2024, 6, 1),
            "delta_1m": 2.0,
            "delta_3m": None,
            "delta_6m": None,
            "direction": "up",
            "regime": "neutral",
            "zscore_12m": None,
            "release_source": "econ_events",
            "is_assumption_based": False,
        },
    ]


def _eod_rows(price: float = 101.0) -> list[dict]:
    return [
        {
            "symbol": "SPY",
            "trade_date": date(2024, 6, 10),
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 101.0,
            "adj_close": 101.0,
            "volume": 1000000,
            "currency": "USD",
            "prev_adj_close": None,
            "ret_1d": None,
            "log_ret_1d": None,
            "ret_5d": None,
            "ret_20d": None,
            "vol_20d": None,
            "vol_60d": None,
            "ma_5": None,
            "ma_20": None,
            "ma_60": None,
            "ma_120": None,
            "ma_ratio_5_20": None,
            "atr_14": None,
            "rsi_14": None,
            "intraday_range": 0.03,
            "gap_open": 0.0,
            "volume_zscore_20d": None,
            "is_trading_day": True,
            "is_missing_imputed": False,
            "is_outlier": False,
            "is_partial_day": False,
            "asset_group": "INDEX",
            "asset_name": "SP500",
            "asset_subtype": "BROAD_MARKET",
            "run_id_gold": "run_a",
            "ingestion_ts_gold": pd.Timestamp("2024-06-11T00:00:00Z"),
        },
        {
            "symbol": "SPY",
            "trade_date": date(2024, 6, 11),
            "open": price - 1.0,
            "high": price + 1.0,
            "low": price - 2.0,
            "close": price,
            "adj_close": price,
            "volume": 1000100,
            "currency": "USD",
            "prev_adj_close": 101.0,
            "ret_1d": 0.01,
            "log_ret_1d": 0.01,
            "ret_5d": None,
            "ret_20d": None,
            "vol_20d": None,
            "vol_60d": None,
            "ma_5": None,
            "ma_20": None,
            "ma_60": None,
            "ma_120": None,
            "ma_ratio_5_20": None,
            "atr_14": None,
            "rsi_14": None,
            "intraday_range": 0.03,
            "gap_open": 0.0,
            "volume_zscore_20d": None,
            "is_trading_day": True,
            "is_missing_imputed": False,
            "is_outlier": False,
            "is_partial_day": False,
            "asset_group": "INDEX",
            "asset_name": "SP500",
            "asset_subtype": "BROAD_MARKET",
            "run_id_gold": "run_a",
            "ingestion_ts_gold": pd.Timestamp("2024-06-12T00:00:00Z"),
        },
    ]


def _count_rows(engine: Engine, table: str) -> int:
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()


def test_watermark_null_returns_none(pg_engine: Engine) -> None:
    assert _get_watermark(pg_engine, "gold_macro_features") is None


def test_watermark_after_insert(pg_engine: Engine, tmp_path: Path) -> None:
    root = tmp_path / "macro"
    _write_macro(root, _macro_rows())
    sync_gold_macro(gold_root=root, engine=pg_engine)
    assert _get_watermark(pg_engine, "gold_macro_features") == date(2024, 6, 11)


def test_sync_macro_full_backfill_empty_db(pg_engine: Engine, tmp_path: Path) -> None:
    root = tmp_path / "macro"
    _write_macro(root, _macro_rows())
    result = sync_gold_macro(gold_root=root, engine=pg_engine)
    assert result["rows_read"] == 2
    assert result["rows_upserted"] == 2
    assert _count_rows(pg_engine, "gold_macro_features") == 2


def test_sync_macro_incremental_after_watermark(pg_engine: Engine, tmp_path: Path) -> None:
    root = tmp_path / "macro"
    _write_macro(root, _macro_rows())
    sync_gold_macro(gold_root=root, engine=pg_engine)
    _write_macro(root, _macro_rows() + [
        {
            **_macro_rows()[1],
            "trade_date": date(2024, 7, 20),
            "selected_release_date": date(2024, 7, 1),
            "selected_value": 320.0,
        }
    ])
    result = sync_gold_macro(gold_root=root, engine=pg_engine)
    assert result["rows_upserted"] == 3
    assert _count_rows(pg_engine, "gold_macro_features") == 3


def test_sync_macro_idempotent(pg_engine: Engine, tmp_path: Path) -> None:
    root = tmp_path / "macro"
    _write_macro(root, _macro_rows())
    sync_gold_macro(gold_root=root, engine=pg_engine)
    before = _count_rows(pg_engine, "gold_macro_features")
    watermark_before = _get_watermark(pg_engine, "gold_macro_features")
    sync_gold_macro(gold_root=root, engine=pg_engine)
    assert _count_rows(pg_engine, "gold_macro_features") == before
    assert _get_watermark(pg_engine, "gold_macro_features") == watermark_before


def test_sync_macro_upsert_updates_existing_row(pg_engine: Engine, tmp_path: Path) -> None:
    root = tmp_path / "macro"
    _write_macro(root, _macro_rows(value=301.0))
    sync_gold_macro(gold_root=root, engine=pg_engine)
    _write_macro(root, _macro_rows(value=305.0))
    sync_gold_macro(gold_root=root, engine=pg_engine)
    with pg_engine.connect() as conn:
        value = conn.execute(
            text(
                """
                SELECT selected_value
                FROM gold_macro_features
                WHERE indicator_id = 'CPI_US_ALL_ITEMS_SA'
                  AND trade_date = '2024-06-11'
                """
            )
        ).scalar_one()
    assert value == 305.0


def test_sync_eod_full_backfill_empty_db(pg_engine: Engine, tmp_path: Path) -> None:
    root = tmp_path / "eod"
    _write_eod(root, _eod_rows())
    result = sync_gold_eod(gold_root=root, engine=pg_engine)
    assert result["rows_read"] == 2
    assert result["rows_upserted"] == 2
    assert _count_rows(pg_engine, "gold_eod_features") == 2


def test_sync_eod_incremental_after_watermark(pg_engine: Engine, tmp_path: Path) -> None:
    root = tmp_path / "eod"
    _write_eod(root, _eod_rows())
    sync_gold_eod(gold_root=root, engine=pg_engine)
    _write_eod(root, _eod_rows() + [
        {
            **_eod_rows()[1],
            "trade_date": date(2024, 6, 12),
            "close": 103.0,
            "adj_close": 103.0,
        }
    ])
    result = sync_gold_eod(gold_root=root, engine=pg_engine)
    assert result["rows_upserted"] == 1
    assert _count_rows(pg_engine, "gold_eod_features") == 3


def test_sync_eod_idempotent(pg_engine: Engine, tmp_path: Path) -> None:
    root = tmp_path / "eod"
    _write_eod(root, _eod_rows())
    sync_gold_eod(gold_root=root, engine=pg_engine)
    before = _count_rows(pg_engine, "gold_eod_features")
    watermark_before = _get_watermark(pg_engine, "gold_eod_features")
    sync_gold_eod(gold_root=root, engine=pg_engine)
    assert _count_rows(pg_engine, "gold_eod_features") == before
    assert _get_watermark(pg_engine, "gold_eod_features") == watermark_before
