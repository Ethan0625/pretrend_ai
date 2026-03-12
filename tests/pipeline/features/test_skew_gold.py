from pathlib import Path

import pandas as pd

from pretrend.pipeline.features.skew_gold import (
    build_skew_gold_features,
    run_skew_gold_pipeline,
)


def _sample_skew_df(n: int = 300) -> pd.DataFrame:
    dates = pd.bdate_range("2020-01-01", periods=n).date
    values = []
    for i in range(n):
        base = 120.0 + (i % 17) * 0.2
        if i in (120, 180, 240, 260, 280, 295):
            base += 18.0
        values.append(base)
    return pd.DataFrame({"trade_date": dates, "adj_close": values})


def test_skew_extreme_flag_is_binary():
    df = build_skew_gold_features(_sample_skew_df(), run_id="test")
    assert set(df["skew_extreme_flag"].dropna().unique()).issubset({0, 1})


def test_skew_zscore_not_all_nan():
    df = build_skew_gold_features(_sample_skew_df(), run_id="test")
    assert df["skew_zscore_252"].notna().sum() > 0


def test_skew_extreme_flag_nonzero_ratio():
    df = build_skew_gold_features(_sample_skew_df(), run_id="test")
    ratio = float(df["skew_extreme_flag"].mean())
    assert 0.0 < ratio < 0.30


def test_run_pipeline_writes_partitioned_outputs(tmp_path: Path):
    eod_root = tmp_path / "eod"
    gold_root = tmp_path / "gold"
    skew_dir = eod_root / "symbol=^SKEW" / "year=2020" / "month=01"
    skew_dir.mkdir(parents=True, exist_ok=True)
    _sample_skew_df(80).to_parquet(skew_dir / "gold_eod_features_202001.parquet", index=False)

    out = run_skew_gold_pipeline(
        eod_root=eod_root,
        gold_root=gold_root,
        run_id="unit_test_run",
    )

    assert len(out) == 80
    files = sorted(gold_root.rglob("*.parquet"))
    assert files
    sample = pd.read_parquet(files[0])
    assert list(sample.columns) == [
        "trade_date",
        "skew_close",
        "skew_zscore_252",
        "skew_extreme_flag",
        "run_id",
        "ingestion_ts",
    ]
