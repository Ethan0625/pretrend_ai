from __future__ import annotations

import pandas as pd

from pretrend.pipeline.backtest.slice_analysis import (
    compute_slice_metrics,
    define_slice_masks,
    extract_windows,
    run_slice_comparison,
)


def _make_gold_df() -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=8, freq="B")
    return pd.DataFrame(
        {
            "uso_ret_20d": [0.10, 0.16, 0.17, 0.18, 0.01, 0.00, 0.20, 0.21],
            "tlt_ret_20d": [-0.01, -0.06, -0.07, -0.02, -0.08, -0.09, -0.01, -0.02],
            "spy_ret_20d": [0.01, 0.02, 0.03, -0.01, 0.02, 0.03, 0.04, 0.05],
            "credit_spread_20d": [0.00, -0.01, -0.04, -0.05, -0.01, -0.02, -0.06, -0.01],
            "spy_vol_20d": [0.01, 0.02, 0.03, 0.031, 0.015, 0.012, 0.028, 0.011],
        },
        index=idx,
    )


def _make_mid_df() -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=8, freq="B")
    return pd.DataFrame(
        {
            "mid_regime": ["NEUTRAL", "RISK_OFF", "RISK_OFF", "RISK_ON", "RISK_OFF", "NEUTRAL", "RISK_OFF", "RISK_ON"],
            "breadth_iwm_spy_spread": [0.01, -0.02, -0.03, 0.01, -0.04, 0.02, -0.05, -0.01],
        },
        index=idx,
    )


def _make_next_step_df() -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=8, freq="B")
    return pd.DataFrame(
        {"transition_hazard_10d": [0.40, 0.96, 0.97, 0.70, 0.98, 0.20, 0.99, 0.30]},
        index=idx,
    )


def _make_daily_log() -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=90, freq="B")
    nav = 1000 + pd.Series(range(len(idx)), index=idx).astype(float) * 10.0
    return pd.DataFrame(
        {
            "nav": nav,
            "cash": 200.0,
            "invested": nav - 200.0,
            "invested_ratio": 0.80,
            "schd_weight": 0.30,
            "n_positions": 4,
        },
        index=idx,
    )


def test_define_slices_oil_shock_mask():
    masks = define_slice_masks(_make_gold_df(), _make_mid_df(), _make_next_step_df())
    assert bool(masks["oil_shock"].iloc[1]) is True
    assert bool(masks["oil_shock"].iloc[0]) is False


def test_define_slices_rate_shock_mask():
    masks = define_slice_masks(_make_gold_df(), _make_mid_df(), _make_next_step_df())
    assert bool(masks["rate_shock"].iloc[1]) is True
    assert bool(masks["rate_shock"].iloc[0]) is False


def test_define_slices_credit_stress_mask():
    gold = _make_gold_df().drop(columns=["credit_spread_20d"])
    masks = define_slice_masks(gold, _make_mid_df(), _make_next_step_df())
    assert bool(masks["credit_stress"].iloc[2]) is True
    assert bool(masks["credit_stress"].iloc[0]) is False


def test_extract_windows_contiguous():
    idx = pd.date_range("2025-01-01", periods=6, freq="B")
    mask = pd.Series([False, True, True, True, False, True], index=idx)
    windows = extract_windows(mask, min_days=3)
    assert windows == [(idx[1], idx[3])]


def test_extract_windows_min_days_filter():
    idx = pd.date_range("2025-01-01", periods=5, freq="B")
    mask = pd.Series([True, True, False, True, True], index=idx)
    assert extract_windows(mask, min_days=3) == []


def test_compute_slice_metrics_nav_return():
    daily_log = _make_daily_log()
    windows = [(daily_log.index[0], daily_log.index[4])]
    metrics = compute_slice_metrics(daily_log, windows)
    expected = daily_log.iloc[4]["nav"] / daily_log.iloc[0]["nav"] - 1.0
    assert metrics["slice_nav_return"] == expected
    assert metrics["avg_schd_weight"] == 0.30


def test_compute_slice_metrics_post_return_oob():
    daily_log = _make_daily_log().iloc[:10]
    windows = [(daily_log.index[5], daily_log.index[9])]
    metrics = compute_slice_metrics(daily_log, windows)
    assert pd.isna(metrics["post_20d_return"])
    assert pd.isna(metrics["post_60d_return"])
    assert pd.isna(metrics["hit_rate"])


def test_run_slice_comparison_table_structure():
    daily_log = _make_daily_log()
    idx = daily_log.index[:8]
    masks = {
        "oil_shock": pd.Series([False, True, True, True, False, True, True, True], index=idx),
        "rate_shock": pd.Series([False, False, True, True, True, False, False, False], index=idx),
    }
    report = run_slice_comparison(daily_log, daily_log.copy(), masks)

    assert list(report.strategy_table.columns) == [
        "slice", "strategy", "obs_days", "nav_return", "mdd", "post_20d", "post_60d", "hit_rate", "avg_schd_weight", "avg_invested_ratio"
    ]
    assert list(report.delta_table.columns) == [
        "slice", "delta_nav_return", "delta_mdd", "delta_post_20d", "delta_post_60d", "delta_avg_schd_weight"
    ]
    assert list(report.sample_table.columns) == ["slice", "n_windows", "n_days", "date_from", "date_to"]
    assert report.strategy_table["slice"].str.contains(r"\*").any()
