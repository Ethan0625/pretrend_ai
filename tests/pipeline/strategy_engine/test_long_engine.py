"""
Long Phase Engine 계약 테스트.

Contract: docs/architecture/market_structure_long_v1_contract.md
DoD: ML1 (컬럼/타입), ML2 (ENUM), ML3 (결측→UNKNOWN)
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from pretrend.pipeline.strategy_engine.axis_horizon_state.schema import (
    LONG_PHASE_ENUM,
    LONG_OUTPUT_COLUMNS,
)
from pretrend.pipeline.strategy_engine.axis_horizon_state.long_engine import (
    build_long_phase,
)


@pytest.fixture
def macro_policy_sample() -> pd.DataFrame:
    """macro_policy axis 샘플."""
    return pd.DataFrame({
        "indicator_id": ["CPI_US_ALL_ITEMS_SA", "US_UNEMPLOYMENT_RATE"] * 2,
        "trade_date": [date(2024, 6, 3)] * 2 + [date(2024, 6, 4)] * 2,
        "selected_value": [310.0, 3.9, 310.5, 3.8],
        "selected_release_date": [date(2024, 6, 1)] * 4,
        "regime": ["tightening", "tightening", "easing", "easing"],
        "delta_1m": [0.5, -0.1, 0.6, -0.2],
        "delta_3m": [1.2, -0.3, -0.5, -0.4],
        "delta_6m": [2.1, 0.5, -1.0, -0.6],
        "release_source": ["econ_events"] * 4,
        "coverage": [1.0] * 4,
        "is_stale": [False] * 4,
    })


class TestLongPhaseML1:
    """ML1: 필수 컬럼 존재 및 타입 검증."""

    def test_output_columns(self, macro_policy_sample):
        result = build_long_phase(macro_policy_sample)
        for col in LONG_OUTPUT_COLUMNS:
            assert col in result.columns, f"Missing: {col}"

    def test_output_not_empty(self, macro_policy_sample):
        result = build_long_phase(macro_policy_sample)
        assert len(result) > 0


class TestLongPhaseML2:
    """ML2: long_phase ENUM 유효성."""

    def test_enum_values_valid(self, macro_policy_sample):
        result = build_long_phase(macro_policy_sample)
        for val in result["long_phase"]:
            assert val in LONG_PHASE_ENUM, f"Invalid: {val}"

    def test_tightening_positive_delta(self, macro_policy_sample):
        """tightening + delta_6m > 0 → LATE_CYCLE."""
        result = build_long_phase(macro_policy_sample)
        # 2024-06-03: regime=tightening, delta_6m_mean=positive
        row = result[result["trade_date"] == date(2024, 6, 3)]
        assert row.iloc[0]["long_phase"] == "LATE_CYCLE"

    def test_easing_negative_delta(self, macro_policy_sample):
        """easing + delta_6m < 0 → RECESSION."""
        result = build_long_phase(macro_policy_sample)
        # 2024-06-04: regime=easing, delta_6m_mean=negative
        row = result[result["trade_date"] == date(2024, 6, 4)]
        assert row.iloc[0]["long_phase"] == "RECESSION"

    def test_neutral_regime(self):
        """neutral regime → EXPANSION."""
        df = pd.DataFrame({
            "indicator_id": ["CPI"],
            "trade_date": [date(2024, 7, 1)],
            "regime": ["neutral"],
            "delta_6m": [0.0],
        })
        result = build_long_phase(df)
        assert result.iloc[0]["long_phase"] == "EXPANSION"


class TestLongPhaseML3:
    """ML3: 결측 시 UNKNOWN (fail-open)."""

    def test_empty_input(self):
        result = build_long_phase(pd.DataFrame())
        assert result.empty
        assert set(LONG_OUTPUT_COLUMNS).issubset(result.columns)

    def test_missing_regime(self):
        """regime이 None → UNKNOWN."""
        df = pd.DataFrame({
            "indicator_id": ["CPI"],
            "trade_date": [date(2024, 7, 1)],
            "regime": [None],
            "delta_6m": [1.0],
        })
        result = build_long_phase(df)
        assert result.iloc[0]["long_phase"] == "UNKNOWN"

    def test_missing_delta_column(self):
        """delta_6m 컬럼 자체가 없어도 동작."""
        df = pd.DataFrame({
            "indicator_id": ["CPI"],
            "trade_date": [date(2024, 7, 1)],
            "regime": ["tightening"],
        })
        result = build_long_phase(df)
        assert result.iloc[0]["long_phase"] in LONG_PHASE_ENUM
