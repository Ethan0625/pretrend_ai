"""Metrics 단위 테스트."""
import math
from datetime import date

import pandas as pd
import pytest

from pretrend.pipeline.backtest.metrics import (
    compute_metrics,
    compute_period_metrics,
    compute_phase_distribution,
)


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


# ── Phase 분포 집계 테스트 ──────────────────────────────────────


def _make_policy_df(rows):
    """Helper: policy_selection DataFrame 생성."""
    df = pd.DataFrame(rows)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    return df


class TestComputePhaseDistribution:
    def test_yearly_aggregation(self):
        """연도별 집계 — 각 연도의 long_phase 비율이 정확히 집계되어야 한다."""
        rows = []
        # 2020: 200일 LATE_CYCLE, 52일 SLOWDOWN
        for i in range(200):
            rows.append({"trade_date": f"2020-{(i % 12 + 1):02d}-01", "long_phase": "LATE_CYCLE"})
        for i in range(52):
            rows.append({"trade_date": f"2020-{(i % 12 + 1):02d}-15", "long_phase": "SLOWDOWN"})
        # 2021: 252일 전부 EXPANSION
        for i in range(252):
            rows.append({"trade_date": f"2021-{(i % 12 + 1):02d}-01", "long_phase": "EXPANSION"})

        df = _make_policy_df(rows)
        dist = compute_phase_distribution(df, group_by="year")

        assert not dist.empty
        assert set(dist["period"].astype(str)) >= {"2020", "2021"}

        row_2021 = dist[dist["period"].astype(str) == "2021"].iloc[0]
        assert row_2021["EXPANSION_pct"] == pytest.approx(1.0, abs=0.01)
        assert row_2021["LATE_CYCLE_pct"] == pytest.approx(0.0, abs=0.01)

        row_2020 = dist[dist["period"].astype(str) == "2020"].iloc[0]
        total_2020 = 200 + 52
        assert row_2020["LATE_CYCLE_pct"] == pytest.approx(200 / total_2020, abs=0.01)
        assert row_2020["SLOWDOWN_pct"] == pytest.approx(52 / total_2020, abs=0.01)

    def test_sr_combined_pct(self):
        """SR_combined_pct = SLOWDOWN_pct + RECESSION_pct."""
        rows = [
            {"trade_date": "2020-01-02", "long_phase": "SLOWDOWN"},
            {"trade_date": "2020-01-03", "long_phase": "RECESSION"},
            {"trade_date": "2020-01-06", "long_phase": "LATE_CYCLE"},
            {"trade_date": "2020-01-07", "long_phase": "LATE_CYCLE"},
        ]
        df = _make_policy_df(rows)
        dist = compute_phase_distribution(df, group_by="year")
        row = dist.iloc[0]
        # 4행 중 SLOWDOWN 1 + RECESSION 1 = 0.25 + 0.25 = 0.50
        assert row["SLOWDOWN_pct"] == pytest.approx(0.25)
        assert row["RECESSION_pct"] == pytest.approx(0.25)
        assert row["SR_combined_pct"] == pytest.approx(0.50)
        assert row["SR_combined_pct"] == pytest.approx(
            row["SLOWDOWN_pct"] + row["RECESSION_pct"]
        )

    def test_empty_dataframe(self):
        """빈 DataFrame → 빈 결과 반환."""
        dist = compute_phase_distribution(pd.DataFrame(), group_by="year")
        assert dist.empty

    def test_half_groupby(self):
        """half 집계 — H1/H2 기간 레이블 생성."""
        rows = [
            {"trade_date": "2020-01-10", "long_phase": "EXPANSION"},
            {"trade_date": "2020-07-10", "long_phase": "SLOWDOWN"},
        ]
        df = _make_policy_df(rows)
        dist = compute_phase_distribution(df, group_by="half")
        periods = dist["period"].tolist()
        assert "2020-H1" in periods
        assert "2020-H2" in periods
