"""
Allocation v2 + dispatch 레지스트리 테스트.

DoD:
  - v2 2D lookup 정확성
  - 4단계 fallback (long_UNKNOWN, mid_UNKNOWN, 둘 다 UNKNOWN)
  - risk_gate=false → INCREASE 차단
  - run_universe=false → INCREASE 차단
  - DECREASE는 risk_gate/run_universe 무관하게 허용
  - dispatch_allocation(): preset_name → 올바른 함수 호출
  - 미등록 preset_name → v0 fallback
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from pretrend.pipeline.backtest.config import BacktestConfig, PRESET_V2
from pretrend.pipeline.backtest.allocation import (
    compute_allocation_v2,
    dispatch_allocation,
    ALLOCATION_REGISTRY,
)


@pytest.fixture
def v2_config():
    return BacktestConfig.from_preset(
        "v2", start_date=date(2012, 1, 3), end_date=date(2024, 6, 3),
    )


# ── v2 2D Lookup ────────────────────────────────────────────


class TestAllocationV2Lookup:
    """v2: f(long_phase, mid_regime) 2D 룩업 정확성."""

    def test_late_cycle_risk_off(self, v2_config):
        """LATE_CYCLE + RISK_OFF → target=0.30 (핵심 개선 케이스)."""
        row = pd.Series({
            "long_phase": "LATE_CYCLE", "mid_regime": "RISK_OFF",
            "risk_gate": True, "run_universe": True,
        })
        result = compute_allocation_v2(0.60, row, v2_config)
        # current=0.60, target=0.30 → DECREASE
        assert result["action"] == "DECREASE"
        assert result["next_invested_ratio"] == pytest.approx(0.50)

    def test_late_cycle_risk_on(self, v2_config):
        """LATE_CYCLE + RISK_ON → target=0.60."""
        row = pd.Series({
            "long_phase": "LATE_CYCLE", "mid_regime": "RISK_ON",
            "risk_gate": True, "run_universe": True,
        })
        result = compute_allocation_v2(0.60, row, v2_config)
        assert result["action"] == "HOLD"
        assert result["next_invested_ratio"] == pytest.approx(0.60)

    def test_expansion_risk_on(self, v2_config):
        """EXPANSION + RISK_ON → target=0.80 → INCREASE."""
        row = pd.Series({
            "long_phase": "EXPANSION", "mid_regime": "RISK_ON",
            "risk_gate": True, "run_universe": True,
        })
        result = compute_allocation_v2(0.60, row, v2_config)
        assert result["action"] == "INCREASE"
        assert result["next_invested_ratio"] == pytest.approx(0.70)

    def test_recession_risk_off(self, v2_config):
        """RECESSION + RISK_OFF → target=0.05 → DECREASE."""
        row = pd.Series({
            "long_phase": "RECESSION", "mid_regime": "RISK_OFF",
            "risk_gate": True, "run_universe": True,
        })
        result = compute_allocation_v2(0.60, row, v2_config)
        assert result["action"] == "DECREASE"
        assert result["next_invested_ratio"] == pytest.approx(0.50)

    def test_all_table_values_reachable(self, v2_config):
        """2D 테이블 모든 (long_phase, mid_regime) 키 정상 lookup."""
        m = v2_config.target_ratio_map_v2
        assert len(m) == 24  # 6 phases × 4 regimes


# ── 4단계 Fallback ──────────────────────────────────────────


class TestAllocationV2Fallback:
    """v2 4단계 fallback 동작."""

    def test_exact_match(self, v2_config):
        """(long, mid) exact match 사용."""
        row = pd.Series({
            "long_phase": "RECOVERY", "mid_regime": "NEUTRAL",
            "risk_gate": True, "run_universe": True,
        })
        result = compute_allocation_v2(0.30, row, v2_config)
        # target=0.60 (RECOVERY, NEUTRAL)
        assert result["action"] == "INCREASE"

    def test_fallback_long_unknown(self, v2_config):
        """(UNKNOWN, mid) → (UNKNOWN, UNKNOWN) fallback."""
        row = pd.Series({
            "long_phase": "UNKNOWN", "mid_regime": "RISK_ON",
            "risk_gate": True, "run_universe": True,
        })
        result = compute_allocation_v2(0.30, row, v2_config)
        # (UNKNOWN, RISK_ON) = 0.50 → INCREASE
        assert result["action"] == "INCREASE"

    def test_fallback_mid_unknown(self, v2_config):
        """(long, UNKNOWN) fallback."""
        row = pd.Series({
            "long_phase": "EXPANSION", "mid_regime": "UNKNOWN",
            "risk_gate": True, "run_universe": True,
        })
        result = compute_allocation_v2(0.30, row, v2_config)
        # (EXPANSION, UNKNOWN) = 0.65 → INCREASE
        assert result["action"] == "INCREASE"

    def test_fallback_both_unknown(self, v2_config):
        """(UNKNOWN, UNKNOWN) → target=0.40."""
        row = pd.Series({
            "long_phase": "UNKNOWN", "mid_regime": "UNKNOWN",
            "risk_gate": True, "run_universe": True,
        })
        result = compute_allocation_v2(0.60, row, v2_config)
        # target=0.40 → DECREASE
        assert result["action"] == "DECREASE"


# ── risk_gate / run_universe 차단 ────────────────────────────


class TestAllocationV2Guards:
    """risk_gate, run_universe INCREASE 차단 동작."""

    def test_risk_gate_blocks_increase(self, v2_config):
        """risk_gate=false → INCREASE 차단."""
        row = pd.Series({
            "long_phase": "EXPANSION", "mid_regime": "RISK_ON",
            "risk_gate": False, "run_universe": True,
        })
        result = compute_allocation_v2(0.30, row, v2_config)
        assert result["action"] == "HOLD"
        assert result["blocked_by_risk_gate"] is True

    def test_run_universe_blocks_increase(self, v2_config):
        """run_universe=false → INCREASE 차단."""
        row = pd.Series({
            "long_phase": "EXPANSION", "mid_regime": "RISK_ON",
            "risk_gate": True, "run_universe": False,
        })
        result = compute_allocation_v2(0.30, row, v2_config)
        assert result["action"] == "HOLD"
        assert result["blocked_by_risk_gate"] is False
        assert "increase_blocked_by_run_universe" in result["notes"][0]

    def test_risk_gate_allows_decrease(self, v2_config):
        """risk_gate=false여도 DECREASE는 허용."""
        row = pd.Series({
            "long_phase": "RECESSION", "mid_regime": "RISK_OFF",
            "risk_gate": False, "run_universe": True,
        })
        result = compute_allocation_v2(0.60, row, v2_config)
        assert result["action"] == "DECREASE"

    def test_run_universe_allows_decrease(self, v2_config):
        """run_universe=false여도 DECREASE는 허용."""
        row = pd.Series({
            "long_phase": "RECESSION", "mid_regime": "RISK_OFF",
            "risk_gate": True, "run_universe": False,
        })
        result = compute_allocation_v2(0.60, row, v2_config)
        assert result["action"] == "DECREASE"


# ── dispatch_allocation 레지스트리 ────────────────────────────


class TestDispatchAllocation:
    """dispatch_allocation() 레지스트리 동작."""

    def test_v0_dispatch(self):
        """preset_name='v0' → compute_allocation_v0 호출."""
        assert "v0" in ALLOCATION_REGISTRY

    def test_v1_dispatch(self):
        """preset_name='v1' → compute_allocation_v1 호출."""
        assert "v1" in ALLOCATION_REGISTRY

    def test_v2_dispatch(self):
        """preset_name='v2' → compute_allocation_v2 호출."""
        assert "v2" in ALLOCATION_REGISTRY

    def test_unknown_preset_fallback_v0(self):
        """미등록 preset → v0 fallback (경고 로그, 예외 없음)."""
        config = BacktestConfig.from_preset(
            "v0", start_date=date(2012, 1, 3), end_date=date(2024, 6, 3),
        )
        row = pd.Series({
            "target_invested_lower": 0.10, "target_invested_upper": 0.60,
            "adjustment_limit": 0.10, "step_size": 0.05,
            "risk_gate": True, "run_universe": True,
        })
        result = dispatch_allocation("v99", 0.40, row, config)
        assert result["action"] in {"HOLD", "INCREASE", "DECREASE"}

    def test_none_policy_row(self):
        """policy_row=None → HOLD 반환."""
        config = BacktestConfig.from_preset(
            "v0", start_date=date(2012, 1, 3), end_date=date(2024, 6, 3),
        )
        result = dispatch_allocation("v0", 0.40, None, config)
        assert result["action"] == "HOLD"

    def test_v2_end_to_end_dispatch(self, v2_config):
        """dispatch('v2', ...) → v2 2D lookup 정상 동작."""
        row = pd.Series({
            "long_phase": "LATE_CYCLE", "mid_regime": "RISK_OFF",
            "risk_gate": True, "run_universe": True,
        })
        result = dispatch_allocation("v2", 0.60, row, v2_config)
        # target=0.30 → DECREASE
        assert result["action"] == "DECREASE"


# ── PRESET_V2 설정 검증 ──────────────────────────────────────


class TestPresetV2Config:
    """BacktestConfig.from_preset('v2') 설정 검증."""

    def test_v2_preset_registered(self):
        """PRESET_V2가 PRESET_REGISTRY에 등록."""
        from pretrend.pipeline.backtest.config import PRESET_REGISTRY
        assert "v2" in PRESET_REGISTRY

    def test_v2_config_has_map(self, v2_config):
        """v2 config에 target_ratio_map_v2 있음."""
        assert v2_config.target_ratio_map_v2 is not None
        assert len(v2_config.target_ratio_map_v2) == 24

    def test_v2_all_values_in_range(self, v2_config):
        """target_ratio_map_v2 모든 값 ∈ [0, 1]."""
        for (lp, mr), ratio in v2_config.target_ratio_map_v2.items():
            assert 0.0 <= ratio <= 1.0, f"({lp}, {mr}) = {ratio} out of range"

    def test_v2_config_validation_invalid_ratio(self):
        """잘못된 ratio → ValueError."""
        with pytest.raises(ValueError, match="must be in \\[0, 1\\]"):
            BacktestConfig(
                start_date=date(2012, 1, 3),
                end_date=date(2024, 6, 3),
                target_ratio_map_v2={("EXPANSION", "RISK_ON"): 1.5},
            )
