from datetime import date

import pandas as pd

from pretrend.pipeline.features.eod_features import (
    EodFeatureConfig,
    EodFeatureRunContext,
    write_silver_eod_features,
)

from pathlib import Path

def _partition_dir(ctx: EodFeatureRunContext) -> Path:
    return (
        ctx.cfg.silver_root
        / "symbol=SPY"
        / "year=2024"
        / "month=01"
    )


def _load_all_parquets_under(path: Path) -> pd.DataFrame:
    files = sorted(path.rglob("*.parquet"))
    assert files, f"no parquet files found under {path}"
    return pd.concat([pd.read_parquet(p) for p in files], ignore_index=True)


def _make_ctx(tmp_path, run_id: str) -> EodFeatureRunContext:
    cfg = EodFeatureConfig(data_root=tmp_path)
    return EodFeatureRunContext(
        feature_start_date=date(2024, 1, 1),
        feature_end_date=date(2024, 1, 31),
        run_id=run_id,
        ingestion_ts=pd.Timestamp("2024-02-01"),
        cfg=cfg,
    )


def _make_df(price: float) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["SPY"],
            "trade_date": [pd.Timestamp("2024-01-05")],
            "source": ["YF"],
            "theme": ["GENERIC"],
            "open": [price],
            "high": [price + 1],
            "low": [price - 1],
            "close": [price + 0.5],
            "adj_close": [price + 0.5],
            "volume": [1_000],
            "currency": ["USD"],
            "run_id": ["bronze_run"],
            "ingestion_ts": [pd.Timestamp("2024-02-01")],
        }
    )


def test_eod_write_overwrites_partition(tmp_path):
    """
    Second write to the same (symbol, year, month) partition replaces rows instead of appending.
    """
    ctx_first = _make_ctx(tmp_path, "run_first")
    ctx_second = _make_ctx(tmp_path, "run_second")

    df_v1 = _make_df(100.0)
    df_v2 = _make_df(999.0)  # distinguishable value to detect overwrite

    write_silver_eod_features(df_v1, ctx_first)
    write_silver_eod_features(df_v2, ctx_second)

    part_dir = _partition_dir(ctx_second)
    loaded = _load_all_parquets_under(part_dir)

    assert loaded.duplicated(subset=["symbol", "trade_date"]).sum() == 0
    assert len(loaded) == 1

    row = loaded.iloc[0]
    assert row["open"] == 999.0
    assert row["close"] == 999.5


def test_eod_write_is_idempotent(tmp_path):
    """
    Repeated writes with identical input keep artifact count stable and avoid duplicated rows.
    """
    ctx_first = _make_ctx(tmp_path, "run_first")
    ctx_second = _make_ctx(tmp_path, "run_second")

    df = _make_df(123.0)

    write_silver_eod_features(df, ctx_first)
    part_dir = _partition_dir(ctx_first)

    first_files = sorted(part_dir.rglob("*.parquet"))
    assert first_files, f"no parquet files found under {part_dir}"

    write_silver_eod_features(df, ctx_second)
    second_files = sorted(part_dir.rglob("*.parquet"))

    assert set(first_files) == set(second_files)

    loaded = _load_all_parquets_under(part_dir)

    assert loaded.duplicated(subset=["symbol", "trade_date"]).sum() == 0
    assert len(loaded) == len(df)

    assert loaded["open"].iloc[0] == df["open"].iloc[0]
    assert loaded["close"].iloc[0] == df["close"].iloc[0]
