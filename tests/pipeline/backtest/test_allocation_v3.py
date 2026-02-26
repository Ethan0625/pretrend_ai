from __future__ import annotations

from datetime import date

import pandas as pd

from pretrend.pipeline.backtest.allocation import compute_allocation_v3, dispatch_allocation
from pretrend.pipeline.backtest.config import BacktestConfig, PRESET_REGISTRY


def test_v3_applies_next_step_bias_adjustment() -> None:
    cfg = BacktestConfig.from_preset("v3", start_date=date(2012, 1, 3), end_date=date(2024, 6, 3))

    row_on = pd.Series(
        {
            "long_phase": "EXPANSION",
            "mid_regime": "RISK_ON",
            "next_step_bias_20d": "RISK_ON_BIAS",
            "risk_gate": True,
            "run_universe": True,
        }
    )
    row_off = pd.Series(
        {
            "long_phase": "EXPANSION",
            "mid_regime": "RISK_ON",
            "next_step_bias_20d": "RISK_OFF_BIAS",
            "risk_gate": True,
            "run_universe": True,
        }
    )

    res_on = compute_allocation_v3(0.78, row_on, cfg)
    res_off = compute_allocation_v3(0.78, row_off, cfg)

    assert res_on["action"] == "INCREASE"
    assert res_off["action"] == "HOLD"


def test_v3_registry_and_dispatch_work() -> None:
    assert "v3" in PRESET_REGISTRY
    cfg = BacktestConfig.from_preset("v3", start_date=date(2012, 1, 3), end_date=date(2024, 6, 3))
    row = pd.Series(
        {
            "long_phase": "RECESSION",
            "mid_regime": "RISK_OFF",
            "next_step_bias_20d": "RISK_OFF_BIAS",
            "risk_gate": True,
            "run_universe": True,
        }
    )
    result = dispatch_allocation("v3", 0.60, row, cfg)
    assert result["action"] == "DECREASE"


def test_v31_dispatch_uses_v3_logic() -> None:
    """v3.1은 v0 fallback이 아니라 v3 allocation 로직을 사용해야 한다."""
    assert "v3.1" in PRESET_REGISTRY
    cfg = BacktestConfig.from_preset("v3.1", start_date=date(2012, 1, 3), end_date=date(2024, 6, 3))
    row = pd.Series(
        {
            "long_phase": "EXPANSION",
            "mid_regime": "RISK_ON",
            "next_step_bias_20d": "RISK_ON_BIAS",
            "risk_gate": True,
            "run_universe": True,
        }
    )
    result = dispatch_allocation("v3.1", 0.78, row, cfg)
    assert result["action"] == "INCREASE"


def test_v32_dispatch_uses_v3_logic_and_hard_gate_priority() -> None:
    assert "v3.2" in PRESET_REGISTRY
    cfg = BacktestConfig.from_preset("v3.2", start_date=date(2012, 1, 3), end_date=date(2024, 6, 3))
    row = pd.Series(
        {
            "long_phase": "EXPANSION",
            "mid_regime": "RISK_ON",
            "next_step_bias_effective": "RISK_ON_BIAS",
            "risk_gate": True,
            "run_universe": False,
        }
    )
    result = dispatch_allocation("v3.2", 0.70, row, cfg)
    assert result["action"] == "HOLD"
    assert "increase_blocked_by_run_universe" in result["notes"][0]


def test_v33_dispatch_uses_effective_bias() -> None:
    assert "v3.3" in PRESET_REGISTRY
    cfg = BacktestConfig.from_preset("v3.3", start_date=date(2012, 1, 3), end_date=date(2024, 6, 3))
    row = pd.Series(
        {
            "long_phase": "EXPANSION",
            "mid_regime": "RISK_ON",
            "next_step_bias_20d": "RISK_ON_BIAS",
            "next_step_bias_effective": "RISK_OFF_BIAS",
            "risk_gate": True,
            "run_universe": True,
        }
    )
    result = dispatch_allocation("v3.3", 0.78, row, cfg)
    assert result["action"] == "HOLD"


def test_v34_dispatch_uses_v3_logic_with_effective_bias() -> None:
    assert "v3.4" in PRESET_REGISTRY
    cfg = BacktestConfig.from_preset("v3.4", start_date=date(2012, 1, 3), end_date=date(2024, 6, 3))
    row = pd.Series(
        {
            "long_phase": "EXPANSION",
            "mid_regime": "RISK_ON",
            "next_step_bias_20d": "RISK_ON_BIAS",
            "next_step_bias_effective": "RISK_OFF_BIAS",
            "risk_gate": True,
            "run_universe": True,
        }
    )
    result = dispatch_allocation("v3.4", 0.78, row, cfg)
    assert result["action"] == "HOLD"


def test_v341_dispatch_uses_v3_logic_with_effective_bias() -> None:
    assert "v3.4.1" in PRESET_REGISTRY
    cfg = BacktestConfig.from_preset("v3.4.1", start_date=date(2012, 1, 3), end_date=date(2024, 6, 3))
    row = pd.Series(
        {
            "long_phase": "EXPANSION",
            "mid_regime": "RISK_ON",
            "next_step_bias_20d": "RISK_ON_BIAS",
            "next_step_bias_effective": "RISK_OFF_BIAS",
            "risk_gate": True,
            "run_universe": True,
        }
    )
    result = dispatch_allocation("v3.4.1", 0.78, row, cfg)
    assert result["action"] == "HOLD"
