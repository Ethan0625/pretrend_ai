import pandas as pd

from pretrend.pipeline.features.macro_features import (
    MacroFeatureConfig,
    MacroFeatureRunContext,
    write_silver_macro_features,
)


def _make_ctx(silver_root, run_id: str) -> MacroFeatureRunContext:
    return MacroFeatureRunContext(
        feature_start_date=pd.to_datetime("2024-01-01").date(),
        feature_end_date=pd.to_datetime("2024-03-31").date(),
        run_id=run_id,
        ingestion_ts=pd.Timestamp("2024-04-01"),
        cfg=MacroFeatureConfig(silver_root=silver_root),
        lookback_months=12,
    )


def _make_df(dates, values):
    return pd.DataFrame(
        {
            "indicator_id": ["TEST"] * len(dates),
            "date": dates,
            "value": values,
            "unit": ["UNIT"] * len(dates),
            "source": ["TEST"] * len(dates),
        }
    )


def test_macro_write_overwrites_existing_partition(tmp_path):
    silver_root = tmp_path / "silver_macro"
    ctx_first = _make_ctx(silver_root, "run_first")
    ctx_second = _make_ctx(silver_root, "run_second")

    first_df = _make_df([pd.Timestamp("2024-01-15")], [1.0])
    write_silver_macro_features(first_df, ctx_first)

    updated_df = _make_df([pd.Timestamp("2024-01-15")], [99.0])
    write_silver_macro_features(updated_df, ctx_second)

    final_file = (
        silver_root / "year=2024" / "month=01" / "macro_features_202401.parquet"
    )
    loaded = pd.read_parquet(final_file)

    assert len(loaded) == 1
    assert loaded["value"].iloc[0] == 99.0  # overwrite instead of append


def test_macro_write_is_idempotent_and_cleans_tmp(tmp_path):
    silver_root = tmp_path / "silver_macro"
    ctx_first = _make_ctx(silver_root, "run_first")
    ctx_second = _make_ctx(silver_root, "run_second")

    dates = [pd.Timestamp("2024-01-15"), pd.Timestamp("2024-02-15")]
    df = _make_df(dates, [1.0, 2.0])

    write_silver_macro_features(df, ctx_first)
    first_files = sorted(silver_root.rglob("*.parquet"))
    assert len(first_files) == 2  # two monthly partitions

    write_silver_macro_features(df, ctx_second)
    second_files = sorted(silver_root.rglob("*.parquet"))

    assert set(second_files) == set(first_files)  # no extra artifacts
    total_rows = sum(pd.read_parquet(f).shape[0] for f in second_files)
    assert total_rows == len(df)  # no duplication across repeated writes

    assert not list(silver_root.glob("_tmp_run=*"))  # tmp dirs cleaned each run
