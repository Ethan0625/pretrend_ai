"""
Market Position + Policy Selector 계약 테스트.

Contract: docs/architecture/market_structure_composer_contract.md
DoD: MSC1 (출력 스키마), MSC2 (ENUM), MSC3 (run_universe=false 전파), MSC4 (policy fail-fast)
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from pretrend.pipeline.strategy_engine.axis_horizon_state.schema import (
    LONG_PHASE_ENUM,
    MID_REGIME_ENUM,
    SHORT_SIGNAL_ENUM,
)
from pretrend.pipeline.strategy_engine.market_position.schema import (
    MARKET_POSITION_COLUMNS,
)
from pretrend.pipeline.strategy_engine.market_position.engine import (
    build_market_position,
)
from pretrend.pipeline.strategy_engine.policy_selector.schema import (
    POLICY_SELECTION_COLUMNS,
)
from pretrend.pipeline.strategy_engine.policy_selector.engine import (
    build_policy_selection,
)


@pytest.fixture
def ahs_sample() -> pd.DataFrame:
    """Axis×Horizon State 샘플."""
    return pd.DataFrame({
        "trade_date": [date(2024, 6, 3), date(2024, 6, 4), date(2024, 6, 5)],
        "long_phase": ["LATE_CYCLE", "RECESSION", "EXPANSION"],
        "long_phase_confidence": [None, None, None],
        "mid_regime": ["RISK_ON", "RISK_OFF", "NEUTRAL"],
        "mid_regime_confidence": [None, None, None],
        "short_signal": ["STABLE", "PANIC", "RELIEF"],
        "short_signal_confidence": [None, None, None],
        "source_run_id": ["run1"] * 3,
    })


# ── Market Position 테스트 ────────────────────────────────


class TestMarketPosition:
    def test_output_columns(self, ahs_sample):
        result = build_market_position(ahs_sample)
        for col in MARKET_POSITION_COLUMNS:
            assert col in result.columns, f"Missing: {col}"

    def test_row_count_preserved(self, ahs_sample):
        result = build_market_position(ahs_sample)
        assert len(result) == len(ahs_sample)

    def test_empty_input(self):
        result = build_market_position(pd.DataFrame())
        assert result.empty
        assert set(MARKET_POSITION_COLUMNS).issubset(result.columns)

    def test_run_universe_recession_risk_off(self, ahs_sample):
        """RECESSION + RISK_OFF → run_universe=false."""
        result = build_market_position(ahs_sample)
        row = result[result["trade_date"] == date(2024, 6, 4)]
        assert not row.iloc[0]["run_universe"]

    def test_run_universe_normal(self, ahs_sample):
        """정상 상태 → run_universe=true."""
        result = build_market_position(ahs_sample)
        row = result[result["trade_date"] == date(2024, 6, 3)]
        assert row.iloc[0]["run_universe"]

    def test_risk_gate_panic(self, ahs_sample):
        """PANIC → risk_gate=false."""
        result = build_market_position(ahs_sample)
        row = result[result["trade_date"] == date(2024, 6, 4)]
        assert not row.iloc[0]["risk_gate"]

    def test_risk_gate_stable(self, ahs_sample):
        """STABLE → risk_gate=true."""
        result = build_market_position(ahs_sample)
        row = result[result["trade_date"] == date(2024, 6, 3)]
        assert row.iloc[0]["risk_gate"]

    def test_notes_contains_reasons(self, ahs_sample):
        result = build_market_position(ahs_sample)
        # PANIC day should have risk_gate notes
        panic_row = result[result["trade_date"] == date(2024, 6, 4)]
        notes = panic_row.iloc[0]["notes"]
        assert any("risk_gate_blocked" in n for n in notes)


# ── Policy Selector 테스트 (MSC1-MSC4) ──────────────────


class TestPolicySelectorMSC1:
    """MSC1: Composer 출력 스키마 검증 (policy resolved 필드 포함)."""

    def test_output_columns(self, ahs_sample):
        mp = build_market_position(ahs_sample)
        result = build_policy_selection(mp)
        for col in POLICY_SELECTION_COLUMNS:
            assert col in result.columns, f"Missing: {col}"

    def test_policy_fields_present(self, ahs_sample):
        mp = build_market_position(ahs_sample)
        result = build_policy_selection(mp)
        assert result["policy_profile_id"].iloc[0] == "RC_V0_DEFAULT"
        assert result["target_invested_lower"].iloc[0] > 0
        assert result["target_invested_upper"].iloc[0] > 0
        assert result["adjustment_limit"].iloc[0] > 0
        assert result["step_size"].iloc[0] > 0
        assert result["policy_version"].iloc[0] == "v0"

    def test_lower_le_upper(self, ahs_sample):
        mp = build_market_position(ahs_sample)
        result = build_policy_selection(mp)
        assert (result["target_invested_lower"] <= result["target_invested_upper"]).all()


class TestPolicySelectorMSC2:
    """MSC2: ENUM 위반 금지."""

    def test_enums_valid(self, ahs_sample):
        mp = build_market_position(ahs_sample)
        result = build_policy_selection(mp)
        for val in result["long_phase"]:
            assert val in LONG_PHASE_ENUM
        for val in result["mid_regime"]:
            assert val in MID_REGIME_ENUM
        for val in result["short_signal"]:
            assert val in SHORT_SIGNAL_ENUM


class TestPolicySelectorMSC3:
    """MSC3: run_universe=false 전파."""

    def test_run_universe_propagated(self, ahs_sample):
        mp = build_market_position(ahs_sample)
        result = build_policy_selection(mp)
        # RECESSION+RISK_OFF day → run_universe=false
        row = result[result["trade_date"] == date(2024, 6, 4)]
        assert not row.iloc[0]["run_universe"]


class TestPolicySelectorMSC4:
    """MSC4: policy resolve 실패 시 fail-fast."""

    def test_unknown_policy_raises(self, ahs_sample):
        mp = build_market_position(ahs_sample)
        with pytest.raises(KeyError, match="Unknown policy_profile_id"):
            build_policy_selection(mp, policy_profile_id="NONEXISTENT")

    def test_empty_input(self):
        result = build_policy_selection(pd.DataFrame())
        assert result.empty
