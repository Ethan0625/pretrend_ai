"""
Universe Selector 계약 테스트.

Contract: docs/architecture/universe_contract.md
DoD: UV1 (run_universe=false→0), UV2 (필수 컬럼), UV3 (asset_group ENUM)
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from pretrend.pipeline.strategy_engine.universe.schema import (
    ASSET_GROUP_ENUM,
    UNIVERSE_OUTPUT_COLUMNS,
)
from pretrend.pipeline.strategy_engine.universe.engine import build_universe


@pytest.fixture
def policy_selection_run_true() -> pd.DataFrame:
    return pd.DataFrame({
        "trade_date": [date(2024, 6, 3)],
        "run_universe": [True],
        "risk_gate": [True],
        "long_phase": ["EXPANSION"],
        "mid_regime": ["RISK_ON"],
        "short_signal": ["STABLE"],
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
def policy_selection_run_false() -> pd.DataFrame:
    return pd.DataFrame({
        "trade_date": [date(2024, 6, 3)],
        "run_universe": [False],
        "risk_gate": [False],
        "long_phase": ["RECESSION"],
        "mid_regime": ["RISK_OFF"],
        "short_signal": ["PANIC"],
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
def gold_eod_sample() -> pd.DataFrame:
    return pd.DataFrame([
        {"symbol": "SPY", "trade_date": date(2024, 6, 3),
         "asset_group": "INDEX", "asset_name": "SPY", "ret_20d": 0.05, "vol_20d": 0.15},
        {"symbol": "TLT", "trade_date": date(2024, 6, 3),
         "asset_group": "BOND", "asset_name": "TLT", "ret_20d": -0.02, "vol_20d": 0.10},
        {"symbol": "IAU", "trade_date": date(2024, 6, 3),
         "asset_group": "COMMODITY", "asset_name": "IAU", "ret_20d": 0.03, "vol_20d": 0.12},
        {"symbol": "XLV", "trade_date": date(2024, 6, 3),
         "asset_group": "SECTOR", "asset_name": "XLV", "ret_20d": 0.04, "vol_20d": 0.18},
    ])


class TestUniverseUV1:
    """UV1: run_universe=false → 0 candidates."""

    def test_zero_candidates(self, policy_selection_run_false, gold_eod_sample):
        result = build_universe(policy_selection_run_false, gold_eod_sample)
        assert len(result) == 0


class TestUniverseUV2:
    """UV2: 필수 컬럼/타입 검증."""

    def test_output_columns(self, policy_selection_run_true, gold_eod_sample):
        result = build_universe(policy_selection_run_true, gold_eod_sample)
        for col in UNIVERSE_OUTPUT_COLUMNS:
            assert col in result.columns, f"Missing: {col}"

    def test_has_candidates(self, policy_selection_run_true, gold_eod_sample):
        result = build_universe(policy_selection_run_true, gold_eod_sample)
        assert len(result) > 0
        assert result["is_candidate"].all()

    def test_empty_input(self):
        result = build_universe(pd.DataFrame(), pd.DataFrame())
        assert result.empty


class TestUniverseUV3:
    """UV3: asset_group ENUM 위반 금지."""

    def test_asset_group_valid(self, policy_selection_run_true, gold_eod_sample):
        result = build_universe(policy_selection_run_true, gold_eod_sample)
        for val in result["asset_group"]:
            assert val in ASSET_GROUP_ENUM, f"Invalid: {val}"
