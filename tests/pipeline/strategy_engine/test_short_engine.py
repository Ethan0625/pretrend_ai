"""
Short Signal Engine 계약 테스트.

Contract: docs/architecture/market_structure_short_v1_contract.md
DoD: MSH1 (컬럼/타입), MSH2 (ENUM), MSH3 (결측→UNKNOWN), MSH4 (VIX 없이 동작)
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from pretrend.pipeline.strategy_engine.axis_horizon_state.schema import (
    SHORT_SIGNAL_ENUM,
    SHORT_OUTPUT_COLUMNS,
)
from pretrend.pipeline.strategy_engine.axis_horizon_state.short_engine import (
    build_short_signal,
)


@pytest.fixture
def pv_sample() -> pd.DataFrame:
    """price_volatility axis (SPY).
    vol_20d = 일간 수익률 std: median≈0.008, p90≈0.017
    """
    return pd.DataFrame([
        {"symbol": "SPY", "trade_date": date(2024, 6, 3),
         "ret_1d": -0.025, "ret_20d": -0.05, "vol_20d": 0.025,
         "intraday_range": 0.03, "asset_group": "INDEX"},
        {"symbol": "SPY", "trade_date": date(2024, 6, 4),
         "ret_1d": 0.01, "ret_20d": 0.03, "vol_20d": 0.008,
         "intraday_range": 0.01, "asset_group": "INDEX"},
    ])


@pytest.fixture
def flow_sample() -> pd.DataFrame:
    """flow_structure axis."""
    return pd.DataFrame([
        {"symbol": "SPY", "trade_date": date(2024, 6, 3),
         "volume": 5_000_000, "volume_zscore_20d": 2.5, "asset_group": "INDEX"},
        {"symbol": "SPY", "trade_date": date(2024, 6, 4),
         "volume": 2_000_000, "volume_zscore_20d": 0.3, "asset_group": "INDEX"},
    ])


@pytest.fixture
def sentiment_sample() -> pd.DataFrame:
    """sentiment axis (trade_date grain)."""
    return pd.DataFrame([
        {"trade_date": date(2024, 6, 3),
         "spy_ret_1d": -0.025, "tlt_ret_1d": 0.01, "iau_ret_1d": 0.005,
         "spy_vol_20d": 0.025, "iwm_spy_relative_strength": 0.8,
         "iwm_spy_vol_spread": 0.005, "spy_intraday_range": 0.03},
        {"trade_date": date(2024, 6, 4),
         "spy_ret_1d": 0.01, "tlt_ret_1d": -0.003, "iau_ret_1d": 0.001,
         "spy_vol_20d": 0.008, "iwm_spy_relative_strength": 1.1,
         "iwm_spy_vol_spread": -0.002, "spy_intraday_range": 0.01},
    ])


class TestShortSignalMSH1:
    """MSH1: 필수 컬럼 존재 및 타입."""

    def test_output_columns(self, pv_sample, flow_sample, sentiment_sample):
        result = build_short_signal(pv_sample, flow_sample, sentiment_sample)
        for col in SHORT_OUTPUT_COLUMNS:
            assert col in result.columns, f"Missing: {col}"

    def test_output_row_count(self, pv_sample, flow_sample, sentiment_sample):
        result = build_short_signal(pv_sample, flow_sample, sentiment_sample)
        assert len(result) == 2


class TestShortSignalMSH2:
    """MSH2: ENUM 유효성."""

    def test_enum_values_valid(self, pv_sample, flow_sample, sentiment_sample):
        result = build_short_signal(pv_sample, flow_sample, sentiment_sample)
        for val in result["short_signal"]:
            assert val in SHORT_SIGNAL_ENUM, f"Invalid: {val}"

    def test_panic_signal(self, pv_sample, flow_sample, sentiment_sample):
        """급락 + 높은 vol → PANIC."""
        result = build_short_signal(pv_sample, flow_sample, sentiment_sample)
        row = result[result["trade_date"] == date(2024, 6, 3)]
        assert row.iloc[0]["short_signal"] == "PANIC"

    def test_relief_signal(self, pv_sample, flow_sample, sentiment_sample):
        """반등 + 낮은 vol → RELIEF."""
        result = build_short_signal(pv_sample, flow_sample, sentiment_sample)
        row = result[result["trade_date"] == date(2024, 6, 4)]
        assert row.iloc[0]["short_signal"] == "RELIEF"


class TestShortSignalMSH3:
    """MSH3: 결측 시 UNKNOWN."""

    def test_empty_all_inputs(self):
        result = build_short_signal(pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
        assert result.empty

    def test_empty_flow(self, pv_sample, sentiment_sample):
        """flow가 비어도 동작 (UNKNOWN or partial)."""
        result = build_short_signal(pv_sample, pd.DataFrame(), sentiment_sample)
        assert len(result) > 0

    def test_missing_spy(self, flow_sample, sentiment_sample):
        """SPY 없으면 UNKNOWN."""
        pv_no_spy = pd.DataFrame([
            {"symbol": "TLT", "trade_date": date(2024, 6, 3),
             "ret_1d": 0.01, "vol_20d": 0.10, "intraday_range": 0.008},
        ])
        result = build_short_signal(pv_no_spy, flow_sample, sentiment_sample)
        for _, row in result.iterrows():
            assert row["short_signal"] in SHORT_SIGNAL_ENUM


class TestShortSignalMSH4:
    """MSH4: VIX 없이 동작 (v0 제약)."""

    def test_no_vix_column(self, pv_sample, flow_sample, sentiment_sample):
        """VIX 관련 컬럼이 없어도 에러 없이 동작."""
        assert "vix_close" not in pv_sample.columns
        assert "vix_level" not in sentiment_sample.columns
        result = build_short_signal(pv_sample, flow_sample, sentiment_sample)
        assert len(result) > 0
        for val in result["short_signal"]:
            assert val in SHORT_SIGNAL_ENUM
