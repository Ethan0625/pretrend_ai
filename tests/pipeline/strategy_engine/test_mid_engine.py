"""
Mid Regime Engine 계약 테스트.

Contract: docs/architecture/market_structure_mid_v1_contract.md
DoD: MM1 (컬럼/타입), MM2 (ENUM), MM3 (결측→UNKNOWN)
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from pretrend.pipeline.strategy_engine.axis_horizon_state.schema import (
    MID_REGIME_ENUM,
    MID_OUTPUT_COLUMNS,
)
from pretrend.pipeline.strategy_engine.axis_horizon_state.mid_engine import (
    build_mid_regime,
)


@pytest.fixture
def price_vol_sample() -> pd.DataFrame:
    """price_volatility axis 샘플 (SPY + TLT)."""
    # vol_20d = 일간 수익률 std: median≈0.008, p90≈0.017
    return pd.DataFrame([
        {"symbol": "SPY", "trade_date": date(2024, 6, 3),
         "ret_1d": 0.004, "ret_20d": 0.05, "vol_20d": 0.008, "intraday_range": 0.012},
        {"symbol": "TLT", "trade_date": date(2024, 6, 3),
         "ret_1d": -0.002, "ret_20d": -0.03, "vol_20d": 0.006, "intraday_range": 0.008},
        {"symbol": "SPY", "trade_date": date(2024, 6, 4),
         "ret_1d": -0.015, "ret_20d": -0.04, "vol_20d": 0.025, "intraday_range": 0.025},
        {"symbol": "TLT", "trade_date": date(2024, 6, 4),
         "ret_1d": 0.008, "ret_20d": 0.02, "vol_20d": 0.012, "intraday_range": 0.010},
    ])


class TestMidRegimeMM1:
    """MM1: 필수 컬럼 존재 및 타입."""

    def test_output_columns(self, price_vol_sample):
        result = build_mid_regime(price_vol_sample)
        for col in MID_OUTPUT_COLUMNS:
            assert col in result.columns, f"Missing: {col}"

    def test_output_row_count(self, price_vol_sample):
        result = build_mid_regime(price_vol_sample)
        assert len(result) == 2  # 2 trade_dates


class TestMidRegimeMM2:
    """MM2: ENUM 유효성."""

    def test_enum_values_valid(self, price_vol_sample):
        result = build_mid_regime(price_vol_sample)
        for val in result["mid_regime"]:
            assert val in MID_REGIME_ENUM, f"Invalid: {val}"

    def test_risk_on(self, price_vol_sample):
        """SPY ret_20d > 0 + vol_20d < 0.015 → RISK_ON."""
        result = build_mid_regime(price_vol_sample)
        row = result[result["trade_date"] == date(2024, 6, 3)]
        assert row.iloc[0]["mid_regime"] == "RISK_ON"

    def test_risk_off(self, price_vol_sample):
        """SPY ret_20d < 0 + vol_20d > 0.015 → RISK_OFF."""
        result = build_mid_regime(price_vol_sample)
        row = result[result["trade_date"] == date(2024, 6, 4)]
        assert row.iloc[0]["mid_regime"] == "RISK_OFF"


class TestMidRegimeMM3:
    """MM3: 결측 시 UNKNOWN."""

    def test_empty_input(self):
        result = build_mid_regime(pd.DataFrame())
        assert result.empty
        assert set(MID_OUTPUT_COLUMNS).issubset(result.columns)

    def test_no_spy_data(self):
        """SPY가 없으면 UNKNOWN."""
        df = pd.DataFrame([
            {"symbol": "TLT", "trade_date": date(2024, 6, 3),
             "ret_20d": 0.02, "vol_20d": 0.10},
        ])
        result = build_mid_regime(df)
        assert len(result) == 1
        assert result.iloc[0]["mid_regime"] == "UNKNOWN"

    def test_missing_ret_20d(self):
        """ret_20d가 None → UNKNOWN."""
        df = pd.DataFrame([
            {"symbol": "SPY", "trade_date": date(2024, 6, 3),
             "ret_20d": None, "vol_20d": 0.008},
        ])
        result = build_mid_regime(df)
        assert result.iloc[0]["mid_regime"] == "UNKNOWN"
