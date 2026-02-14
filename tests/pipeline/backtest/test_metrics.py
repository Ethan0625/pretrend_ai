"""Metrics 단위 테스트."""
import math

import pandas as pd
import pytest

from pretrend.pipeline.backtest.metrics import compute_metrics, compute_period_metrics


def _make_nav(values, start="2020-01-01"):
    """Helper: 일별 NAV 시리즈 생성."""
    dates = pd.bdate_range(start, periods=len(values))
    return pd.Series(values, index=dates)


class TestComputeMetrics:
    def test_flat_nav(self):
        nav = _make_nav([1000.0] * 100)
        bm = _make_nav([1000.0] * 100)
        m = compute_metrics(nav, bm)
        assert m["total_return"] == pytest.approx(0.0)
        assert m["cagr"] == pytest.approx(0.0, abs=1e-6)
        assert m["max_drawdown"] == pytest.approx(0.0)

    def test_growing_nav(self):
        # 1000 → 1100 over ~100 days
        values = [1000.0 + i for i in range(101)]
        nav = _make_nav(values)
        bm = _make_nav([1000.0] * 101)
        m = compute_metrics(nav, bm)
        assert m["total_return"] == pytest.approx(0.10)
        assert m["cagr"] > 0
        assert m["max_drawdown"] == pytest.approx(0.0)  # monotonically increasing
        assert m["sharpe_ratio"] > 0
        assert m["excess_return"] > 0

    def test_drawdown(self):
        nav = _make_nav([1000.0, 1100.0, 900.0, 950.0])
        bm = _make_nav([1000.0, 1000.0, 1000.0, 1000.0])
        m = compute_metrics(nav, bm)
        # MDD: peak=1100, trough=900 → -18.18%
        assert m["max_drawdown"] == pytest.approx(-200.0 / 1100.0, abs=0.001)

    def test_empty_nav(self):
        nav = pd.Series(dtype=float)
        bm = pd.Series(dtype=float)
        m = compute_metrics(nav, bm)
        assert m["total_return"] == 0.0

    def test_single_point(self):
        nav = _make_nav([1000.0])
        bm = _make_nav([1000.0])
        m = compute_metrics(nav, bm)
        assert m["total_return"] == 0.0

    def test_benchmark_comparison(self):
        nav = _make_nav([1000.0, 1050.0, 1100.0, 1150.0, 1200.0])
        bm = _make_nav([1000.0, 1010.0, 1020.0, 1030.0, 1040.0])
        m = compute_metrics(nav, bm)
        assert m["excess_return"] == pytest.approx(0.20 - 0.04)
        assert m["excess_cagr"] > 0


class TestComputePeriodMetrics:
    def test_period_slice(self):
        values = [1000.0 + i * 10 for i in range(252)]
        dates = pd.bdate_range("2020-01-01", periods=252)
        nav = pd.Series(values, index=dates)
        bm = pd.Series([1000.0] * 252, index=dates)

        pm = compute_period_metrics(nav, bm, "2020-01-01", "2020-06-30")
        assert pm["total_return"] > 0

    def test_empty_period(self):
        nav = _make_nav([1000.0, 1100.0])
        bm = _make_nav([1000.0, 1000.0])
        pm = compute_period_metrics(nav, bm, "2025-01-01", "2025-12-31")
        assert pm["total_return"] == 0.0
