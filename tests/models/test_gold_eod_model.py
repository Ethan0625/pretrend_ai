from __future__ import annotations

from pretrend.models import Base, GoldEodFeature


EXPECTED_COLUMNS = [
    "symbol",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "currency",
    "prev_adj_close",
    "ret_1d",
    "log_ret_1d",
    "ret_5d",
    "ret_20d",
    "vol_20d",
    "vol_60d",
    "ma_5",
    "ma_20",
    "ma_60",
    "ma_120",
    "ma_ratio_5_20",
    "atr_14",
    "rsi_14",
    "intraday_range",
    "gap_open",
    "volume_zscore_20d",
    "is_trading_day",
    "is_missing_imputed",
    "is_outlier",
    "is_partial_day",
    "asset_group",
    "asset_name",
    "asset_subtype",
    "run_id_gold",
    "ingestion_ts_gold",
]

EXPECTED_NULLABILITY = {
    "symbol": False,
    "trade_date": False,
    "open": True,
    "high": True,
    "low": True,
    "close": True,
    "adj_close": True,
    "volume": True,
    "currency": True,
    "prev_adj_close": True,
    "ret_1d": True,
    "log_ret_1d": True,
    "ret_5d": True,
    "ret_20d": True,
    "vol_20d": True,
    "vol_60d": True,
    "ma_5": True,
    "ma_20": True,
    "ma_60": True,
    "ma_120": True,
    "ma_ratio_5_20": True,
    "atr_14": True,
    "rsi_14": True,
    "intraday_range": True,
    "gap_open": True,
    "volume_zscore_20d": True,
    "is_trading_day": False,
    "is_missing_imputed": False,
    "is_outlier": False,
    "is_partial_day": False,
    "asset_group": False,
    "asset_name": False,
    "asset_subtype": True,
    "run_id_gold": False,
    "ingestion_ts_gold": False,
}


def test_gold_eod_table_registered() -> None:
    assert "gold_eod_features" in Base.metadata.tables
    assert GoldEodFeature.__table__ is Base.metadata.tables["gold_eod_features"]


def test_gold_eod_columns_present() -> None:
    table = GoldEodFeature.__table__
    assert list(table.columns.keys()) == EXPECTED_COLUMNS


def test_gold_eod_pk() -> None:
    table = GoldEodFeature.__table__
    assert [column.name for column in table.primary_key.columns] == [
        "symbol",
        "trade_date",
    ]


def test_gold_eod_column_nullability() -> None:
    table = GoldEodFeature.__table__
    assert {
        column.name: column.nullable
        for column in table.columns
    } == EXPECTED_NULLABILITY
