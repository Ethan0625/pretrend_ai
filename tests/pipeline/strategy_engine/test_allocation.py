"""
Allocation Engine 계약 테스트.

Contract: docs/architecture/allocation_engine_contract.md
DoD: AE1 (컬럼/타입), AE2 (adjustment_limit), AE3 (risk_gate), AE4 (run_universe)
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from pretrend.pipeline.strategy_engine.allocation.schema import (
    ACTION_ENUM,
    ALLOCATION_OUTPUT_COLUMNS,
)
from pretrend.pipeline.strategy_engine.allocation.engine import build_allocation


@pytest.fixture
def ps_normal() -> pd.DataFrame:
    """정상 상태 policy_selection."""
    return pd.DataFrame({
        "trade_date": [date(2024, 6, 3)],
        "run_universe": [True],
        "risk_gate": [True],
        "target_invested_lower": [0.30],
        "target_invested_upper": [0.60],
        "adjustment_limit": [0.10],
        "step_size": [0.05],
    })


@pytest.fixture
def ps_risk_gate_false() -> pd.DataFrame:
    return pd.DataFrame({
        "trade_date": [date(2024, 6, 3)],
        "run_universe": [True],
        "risk_gate": [False],
        "target_invested_lower": [0.30],
        "target_invested_upper": [0.60],
        "adjustment_limit": [0.10],
        "step_size": [0.05],
    })


@pytest.fixture
def ps_run_universe_false() -> pd.DataFrame:
    return pd.DataFrame({
        "trade_date": [date(2024, 6, 3)],
        "run_universe": [False],
        "risk_gate": [True],
        "target_invested_lower": [0.30],
        "target_invested_upper": [0.60],
        "adjustment_limit": [0.10],
        "step_size": [0.05],
    })


class TestAllocationAE1:
    """AE1: 입출력 필수 컬럼/타입."""

    def test_output_columns(self, ps_normal):
        result = build_allocation(ps_normal, current_invested_ratio=0.50)
        for col in ALLOCATION_OUTPUT_COLUMNS:
            assert col in result.columns, f"Missing: {col}"

    def test_action_enum_valid(self, ps_normal):
        result = build_allocation(ps_normal, current_invested_ratio=0.50)
        for val in result["action"]:
            assert val in ACTION_ENUM

    def test_empty_input(self):
        result = build_allocation(pd.DataFrame(), current_invested_ratio=0.50)
        assert result.empty

    def test_in_range_hold(self, ps_normal):
        """범위 내 → HOLD."""
        result = build_allocation(ps_normal, current_invested_ratio=0.45)
        assert result.iloc[0]["action"] == "HOLD"
        assert result.iloc[0]["delta_ratio"] == 0.0

    def test_below_range_increase(self, ps_normal):
        """범위 아래 → INCREASE."""
        result = build_allocation(ps_normal, current_invested_ratio=0.15)
        assert result.iloc[0]["action"] == "INCREASE"
        assert result.iloc[0]["next_invested_ratio"] > 0.15

    def test_above_range_decrease(self, ps_normal):
        """범위 위 → DECREASE."""
        result = build_allocation(ps_normal, current_invested_ratio=0.75)
        assert result.iloc[0]["action"] == "DECREASE"
        assert result.iloc[0]["next_invested_ratio"] < 0.75


class TestAllocationAE2:
    """AE2: abs(delta_ratio) <= adjustment_limit."""

    def test_delta_within_limit(self, ps_normal):
        result = build_allocation(ps_normal, current_invested_ratio=0.10)
        delta = abs(result.iloc[0]["delta_ratio"])
        assert delta <= 0.10 + 1e-9  # floating point tolerance

    def test_large_gap_capped(self):
        """큰 갭도 adjustment_limit로 제한."""
        ps = pd.DataFrame({
            "trade_date": [date(2024, 6, 3)],
            "run_universe": [True],
            "risk_gate": [True],
            "target_invested_lower": [0.30],
            "target_invested_upper": [0.60],
            "adjustment_limit": [0.05],
            "step_size": [0.05],
        })
        result = build_allocation(ps, current_invested_ratio=0.0)
        assert abs(result.iloc[0]["delta_ratio"]) <= 0.05 + 1e-9


class TestAllocationAE3:
    """AE3: risk_gate=false → INCREASE 금지."""

    def test_no_increase_when_risk_gate_false(self, ps_risk_gate_false):
        result = build_allocation(ps_risk_gate_false, current_invested_ratio=0.10)
        assert result.iloc[0]["action"] != "INCREASE"


class TestAllocationAE4:
    """AE4: run_universe=false → INCREASE 금지."""

    def test_no_increase_when_run_universe_false(self, ps_run_universe_false):
        result = build_allocation(ps_run_universe_false, current_invested_ratio=0.10)
        assert result.iloc[0]["action"] != "INCREASE"


class TestAllocationBoundary:
    """경계값 테스트."""

    def test_clamp_to_one(self):
        ps = pd.DataFrame({
            "trade_date": [date(2024, 6, 3)],
            "run_universe": [True],
            "risk_gate": [True],
            "target_invested_lower": [0.90],
            "target_invested_upper": [1.00],
            "adjustment_limit": [0.20],
            "step_size": [0.05],
        })
        result = build_allocation(ps, current_invested_ratio=0.85)
        assert result.iloc[0]["next_invested_ratio"] <= 1.0

    def test_clamp_to_zero(self):
        ps = pd.DataFrame({
            "trade_date": [date(2024, 6, 3)],
            "run_universe": [True],
            "risk_gate": [True],
            "target_invested_lower": [0.00],
            "target_invested_upper": [0.10],
            "adjustment_limit": [0.20],
            "step_size": [0.05],
        })
        result = build_allocation(ps, current_invested_ratio=0.15)
        assert result.iloc[0]["next_invested_ratio"] >= 0.0

    def test_step_size_quantization(self, ps_normal):
        """delta는 step_size 단위."""
        result = build_allocation(ps_normal, current_invested_ratio=0.18)
        delta = abs(result.iloc[0]["delta_ratio"])
        if delta > 0:
            remainder = round(delta % 0.05, 4)
            assert remainder < 1e-9, f"delta {delta} not quantized by step_size 0.05"
