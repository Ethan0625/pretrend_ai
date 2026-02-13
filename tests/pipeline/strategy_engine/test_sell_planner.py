"""
Sell Planner 계약 테스트.

SOT: docs/strategy_engine_design.md §D3, §F
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from pretrend.pipeline.strategy_engine.sell_planner.schema import (
    SELL_PLAN_OUTPUT_COLUMNS,
)
from pretrend.pipeline.strategy_engine.sell_planner.engine import build_sell_plan


@pytest.fixture
def allocation_decrease() -> pd.DataFrame:
    return pd.DataFrame({
        "trade_date": [date(2024, 6, 3)],
        "action": ["DECREASE"],
        "next_invested_ratio": [0.55],
        "delta_ratio": [-0.10],
        "blocked_by_risk_gate": [False],
        "notes": [["target_upper=0.60"]],
    })


@pytest.fixture
def allocation_hold() -> pd.DataFrame:
    return pd.DataFrame({
        "trade_date": [date(2024, 6, 3)],
        "action": ["HOLD"],
        "next_invested_ratio": [0.50],
        "delta_ratio": [0.0],
        "blocked_by_risk_gate": [False],
        "notes": [["in_target_range"]],
    })


@pytest.fixture
def policy_selection() -> pd.DataFrame:
    return pd.DataFrame({
        "trade_date": [date(2024, 6, 3)],
        "long_phase": ["EXPANSION"],
        "mid_regime": ["RISK_ON"],
        "short_signal": ["STABLE"],
        "run_universe": [True],
        "risk_gate": [True],
        "policy_profile_id": ["RC_V0_DEFAULT"],
        "target_invested_lower": [0.3],
        "target_invested_upper": [0.6],
        "adjustment_limit": [0.1],
        "step_size": [0.05],
        "policy_version": ["v0"],
        "notes": [[]],
        "source_run_id": ["run1"],
    })


@pytest.fixture
def universe_sample() -> pd.DataFrame:
    return pd.DataFrame({
        "rebalance_date": [date(2024, 6, 3)] * 3,
        "symbol": ["SPY", "TLT", "XLV"],
        "asset_group": ["INDEX", "BOND", "SECTOR"],
        "relative_strength": [0.05, -0.02, 0.04],
        "is_candidate": [True, True, True],
    })


class TestSellPlan:
    def test_output_columns(self, allocation_decrease, policy_selection, universe_sample):
        result = build_sell_plan(allocation_decrease, policy_selection, universe_sample)
        for col in SELL_PLAN_OUTPUT_COLUMNS:
            assert col in result.columns, f"Missing: {col}"

    def test_sell_budget_on_decrease(self, allocation_decrease, policy_selection, universe_sample):
        result = build_sell_plan(allocation_decrease, policy_selection, universe_sample)
        assert result.iloc[0]["sell_budget_ratio"] > 0

    def test_no_sell_on_hold(self, allocation_hold, policy_selection, universe_sample):
        result = build_sell_plan(allocation_hold, policy_selection, universe_sample)
        assert result.iloc[0]["sell_budget_ratio"] == 0.0

    def test_priority_list_on_decrease(self, allocation_decrease, policy_selection, universe_sample):
        result = build_sell_plan(allocation_decrease, policy_selection, universe_sample)
        priority = result.iloc[0]["sell_priority_list"]
        assert isinstance(priority, list)
        assert len(priority) > 0
        # 약한 것(TLT ret_20d=-0.02)이 먼저
        assert priority[0] == "TLT"

    def test_empty_input(self, policy_selection, universe_sample):
        result = build_sell_plan(pd.DataFrame(), policy_selection, universe_sample)
        assert result.empty

    def test_no_per_symbol_percentage(self, allocation_decrease, policy_selection, universe_sample):
        """v0: 종목별 정밀 매도 비율 없음 (budget + priority만)."""
        result = build_sell_plan(allocation_decrease, policy_selection, universe_sample)
        # sell_weight 같은 컬럼이 없어야 함
        assert "sell_weight" not in result.columns
        assert "sell_pct" not in result.columns
