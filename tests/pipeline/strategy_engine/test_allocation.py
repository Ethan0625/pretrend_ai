"""
Allocation Engine 계약 테스트.

Contract: docs/architecture/allocation_engine_contract.md
DoD: AE1 (컬럼/타입), AE2 (adjustment_limit), AE3 (risk_gate), AE4 (run_universe)
     AEV1 (v1 target-seeking), AEV2 (v2 2D lookup)
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


# ── v1 tests ──────────────────────────────────────────────────────────────────

def _make_ps_v1(long_phase: str, run_universe: bool = True, risk_gate: bool = True):
    """v1 테스트용 policy_selection 픽스처."""
    return pd.DataFrame({
        "trade_date": [date(2024, 6, 3)],
        "long_phase": [long_phase],
        "mid_regime": ["NEUTRAL"],
        "run_universe": [run_universe],
        "risk_gate": [risk_gate],
        "target_invested_lower": [0.10],
        "target_invested_upper": [0.60],
        "adjustment_limit": [0.10],
        "step_size": [0.05],
    })


class TestAllocationV1:
    """AEV1: v1 target-seeking — f(long_phase)."""

    def test_output_columns(self):
        ps = _make_ps_v1("EXPANSION")
        result = build_allocation(ps, 0.10, allocation_mode="v1")
        for col in ALLOCATION_OUTPUT_COLUMNS:
            assert col in result.columns

    def test_expansion_increase(self):
        """EXPANSION: target=0.60, current=0.10 → INCREASE."""
        ps = _make_ps_v1("EXPANSION")
        result = build_allocation(ps, 0.10, allocation_mode="v1")
        assert result.iloc[0]["action"] == "INCREASE"
        assert result.iloc[0]["next_invested_ratio"] == pytest.approx(0.20)

    def test_recession_decrease(self):
        """RECESSION: target=0.10, current=0.60 → DECREASE."""
        ps = _make_ps_v1("RECESSION")
        result = build_allocation(ps, 0.60, allocation_mode="v1")
        assert result.iloc[0]["action"] == "DECREASE"
        assert result.iloc[0]["next_invested_ratio"] == pytest.approx(0.50)

    def test_slowdown_decrease(self):
        """SLOWDOWN: target=0.20, current=0.60 → DECREASE."""
        ps = _make_ps_v1("SLOWDOWN")
        result = build_allocation(ps, 0.60, allocation_mode="v1")
        assert result.iloc[0]["action"] == "DECREASE"

    def test_at_target_hold(self):
        """EXPANSION에서 current=0.60 → HOLD (이미 목표값)."""
        ps = _make_ps_v1("EXPANSION")
        result = build_allocation(ps, 0.60, allocation_mode="v1")
        assert result.iloc[0]["action"] == "HOLD"

    def test_run_universe_false_blocks_increase(self):
        """run_universe=False → INCREASE 금지."""
        ps = _make_ps_v1("EXPANSION", run_universe=False)
        result = build_allocation(ps, 0.10, allocation_mode="v1")
        assert result.iloc[0]["action"] != "INCREASE"

    def test_risk_gate_false_allows_increase(self):
        """risk_gate=False(PANIC)이어도 INCREASE 허용 (저점매수)."""
        ps = _make_ps_v1("EXPANSION", risk_gate=False)
        result = build_allocation(ps, 0.10, allocation_mode="v1")
        assert result.iloc[0]["action"] == "INCREASE"

    def test_unknown_phase_fallback(self):
        """알 수 없는 phase → UNKNOWN map(0.40)으로 fallback."""
        ps = _make_ps_v1("UNKNOWN")
        result = build_allocation(ps, 0.10, allocation_mode="v1")
        # target=0.40, current=0.10 → INCREASE
        assert result.iloc[0]["action"] == "INCREASE"

    def test_delta_within_adj_limit(self):
        """delta는 adjustment_limit(0.10) 이내."""
        ps = _make_ps_v1("EXPANSION")
        result = build_allocation(ps, 0.10, allocation_mode="v1")
        assert abs(result.iloc[0]["delta_ratio"]) <= 0.10 + 1e-9


# ── v2 tests ──────────────────────────────────────────────────────────────────

def _make_ps_v2(long_phase: str, mid_regime: str, run_universe: bool = True, risk_gate: bool = True):
    """v2 테스트용 policy_selection 픽스처."""
    return pd.DataFrame({
        "trade_date": [date(2024, 6, 3)],
        "long_phase": [long_phase],
        "mid_regime": [mid_regime],
        "run_universe": [run_universe],
        "risk_gate": [risk_gate],
        "target_invested_lower": [0.10],
        "target_invested_upper": [0.60],
        "adjustment_limit": [0.10],
        "step_size": [0.05],
    })


class TestAllocationV2:
    """AEV2: v2 2D lookup — f(long_phase, mid_regime)."""

    def test_output_columns(self):
        ps = _make_ps_v2("LATE_CYCLE", "RISK_OFF")
        result = build_allocation(ps, 0.60, allocation_mode="v2")
        for col in ALLOCATION_OUTPUT_COLUMNS:
            assert col in result.columns

    def test_late_cycle_risk_off_decrease(self):
        """LATE_CYCLE+RISK_OFF: target=0.30, current=0.60 → DECREASE."""
        ps = _make_ps_v2("LATE_CYCLE", "RISK_OFF")
        result = build_allocation(ps, 0.60, allocation_mode="v2")
        assert result.iloc[0]["action"] == "DECREASE"
        assert result.iloc[0]["next_invested_ratio"] == pytest.approx(0.50)

    def test_expansion_risk_on_increase(self):
        """EXPANSION+RISK_ON: target=0.80, current=0.50 → INCREASE."""
        ps = _make_ps_v2("EXPANSION", "RISK_ON")
        result = build_allocation(ps, 0.50, allocation_mode="v2")
        assert result.iloc[0]["action"] == "INCREASE"
        assert result.iloc[0]["next_invested_ratio"] == pytest.approx(0.60)

    def test_recession_risk_off_decrease(self):
        """RECESSION+RISK_OFF: target=0.05, current=0.60 → DECREASE."""
        ps = _make_ps_v2("RECESSION", "RISK_OFF")
        result = build_allocation(ps, 0.60, allocation_mode="v2")
        assert result.iloc[0]["action"] == "DECREASE"

    def test_unknown_unknown_hold(self):
        """UNKNOWN+UNKNOWN: target=0.40, current=0.40 → HOLD."""
        ps = _make_ps_v2("UNKNOWN", "UNKNOWN")
        result = build_allocation(ps, 0.40, allocation_mode="v2")
        assert result.iloc[0]["action"] == "HOLD"

    def test_fallback_to_long_unknown(self):
        """mid_regime 미매핑 → (long_phase, 'UNKNOWN') fallback."""
        ps = _make_ps_v2("EXPANSION", "INVALID_REGIME")
        result = build_allocation(ps, 0.10, allocation_mode="v2")
        # (EXPANSION, UNKNOWN)=0.65 → INCREASE
        assert result.iloc[0]["action"] == "INCREASE"

    def test_risk_gate_false_allows_increase(self):
        """risk_gate=False(PANIC)이어도 INCREASE 허용."""
        ps = _make_ps_v2("EXPANSION", "RISK_ON", risk_gate=False)
        result = build_allocation(ps, 0.10, allocation_mode="v2")
        assert result.iloc[0]["action"] == "INCREASE"

    def test_run_universe_false_blocks_increase(self):
        """run_universe=False → INCREASE 금지."""
        ps = _make_ps_v2("EXPANSION", "RISK_ON", run_universe=False)
        result = build_allocation(ps, 0.10, allocation_mode="v2")
        assert result.iloc[0]["action"] != "INCREASE"


class TestAllocationModeDispatch:
    """allocation_mode 파라미터 dispatch 테스트."""

    def test_default_mode_is_v0(self):
        """allocation_mode 미지정 → v0 동작 (범위 내 HOLD)."""
        ps = pd.DataFrame({
            "trade_date": [date(2024, 6, 3)],
            "long_phase": ["EXPANSION"],
            "mid_regime": ["RISK_ON"],
            "run_universe": [True], "risk_gate": [True],
            "target_invested_lower": [0.30],
            "target_invested_upper": [0.60],
            "adjustment_limit": [0.10], "step_size": [0.05],
        })
        result = build_allocation(ps, 0.45)  # in [0.30, 0.60] → HOLD for v0
        assert result.iloc[0]["action"] == "HOLD"

    def test_unknown_mode_fallback_v0(self):
        """미등록 mode → v0 fallback (경고 로그)."""
        ps = pd.DataFrame({
            "trade_date": [date(2024, 6, 3)],
            "run_universe": [True], "risk_gate": [True],
            "target_invested_lower": [0.30],
            "target_invested_upper": [0.60],
            "adjustment_limit": [0.10], "step_size": [0.05],
        })
        result = build_allocation(ps, 0.45, allocation_mode="v99")
        assert result.iloc[0]["action"] == "HOLD"  # v0 fallback, in range
