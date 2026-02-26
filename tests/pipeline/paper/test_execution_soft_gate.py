from __future__ import annotations

from datetime import date

import pandas as pd

from pretrend.pipeline.backtest.config import BacktestConfig
from pretrend.pipeline.paper.execution import (
    _apply_group_transition_gate_v341,
    simulate_paper_execution,
)


def _base_prices() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": date(2026, 1, 6), "symbol": "SPY", "adj_close": 100.0},
            {"trade_date": date(2026, 1, 6), "symbol": "SCHD", "adj_close": 50.0},
            {"trade_date": date(2026, 1, 6), "symbol": "IAU", "adj_close": 20.0},
            {"trade_date": date(2026, 1, 6), "symbol": "XLE", "adj_close": 80.0},
        ]
    )


def test_soft_gate_risk_off_reduces_tactical_to_zero() -> None:
    cfg = BacktestConfig(start_date=date(2026, 1, 6), end_date=date(2026, 1, 7))
    exposure = pd.DataFrame(
        [{"trade_date": date(2026, 1, 6), "action": "INCREASE", "next_invested_ratio": 0.80, "delta_ratio": 0.20}]
    )
    policy = pd.DataFrame(
        [{"trade_date": date(2026, 1, 6), "run_universe": True, "risk_gate": True}]
    )
    universe = pd.DataFrame(
        [
            {"rebalance_date": date(2026, 1, 6), "symbol": "SPY", "asset_group": "SECTOR", "relative_strength": 0.00, "is_candidate": True},
            {"rebalance_date": date(2026, 1, 6), "symbol": "XLE", "asset_group": "SECTOR", "relative_strength": 0.10, "is_candidate": True},
        ]
    )
    next_step = pd.DataFrame(
        [{"trade_date": date(2026, 1, 6), "bias_20d": "RISK_OFF_BIAS"}]
    )

    ledger, _, _ = simulate_paper_execution(
        config=cfg,
        exposure_df=exposure,
        prices_df=_base_prices(),
        source_job="paper_trading_dag",
        decision_date=date(2026, 1, 6),
        simulation_date=date(2026, 1, 6),
        policy_df=policy,
        universe_df=universe,
        next_step_df=next_step,
        enable_predictor_gate=True,
    )

    assert ledger[ledger["symbol"] == "XLE"].empty


def test_hard_gate_precedes_soft_gate_when_run_universe_false() -> None:
    cfg = BacktestConfig(start_date=date(2026, 1, 6), end_date=date(2026, 1, 7))
    exposure = pd.DataFrame(
        [{"trade_date": date(2026, 1, 6), "action": "INCREASE", "next_invested_ratio": 0.80, "delta_ratio": 0.20}]
    )
    policy = pd.DataFrame(
        [{"trade_date": date(2026, 1, 6), "run_universe": False, "risk_gate": True}]
    )
    universe = pd.DataFrame(
        [
            {"rebalance_date": date(2026, 1, 6), "symbol": "SPY", "asset_group": "SECTOR", "relative_strength": 0.00, "is_candidate": True},
            {"rebalance_date": date(2026, 1, 6), "symbol": "XLE", "asset_group": "SECTOR", "relative_strength": 0.10, "is_candidate": True},
        ]
    )
    next_step = pd.DataFrame(
        [{"trade_date": date(2026, 1, 6), "bias_20d": "RISK_ON_BIAS"}]
    )

    ledger, _, _ = simulate_paper_execution(
        config=cfg,
        exposure_df=exposure,
        prices_df=_base_prices(),
        source_job="paper_trading_dag",
        decision_date=date(2026, 1, 6),
        simulation_date=date(2026, 1, 6),
        policy_df=policy,
        universe_df=universe,
        next_step_df=next_step,
        enable_predictor_gate=True,
    )

    assert ledger[ledger["symbol"] == "XLE"].empty


def test_group_transition_weak_sector_reduces_sector_tactical() -> None:
    cfg = BacktestConfig(start_date=date(2026, 1, 6), end_date=date(2026, 1, 7))
    exposure = pd.DataFrame(
        [{"trade_date": date(2026, 1, 6), "action": "INCREASE", "next_invested_ratio": 0.80, "delta_ratio": 0.20}]
    )
    policy = pd.DataFrame(
        [{"trade_date": date(2026, 1, 6), "run_universe": True, "risk_gate": True}]
    )
    universe = pd.DataFrame(
        [
            {"rebalance_date": date(2026, 1, 6), "symbol": "SPY", "asset_group": "SECTOR", "relative_strength": 0.00, "is_candidate": True},
            {"rebalance_date": date(2026, 1, 6), "symbol": "XLE", "asset_group": "SECTOR", "relative_strength": 0.10, "is_candidate": True},
            {"rebalance_date": date(2026, 1, 6), "symbol": "TLT", "asset_group": "BOND", "relative_strength": 0.08, "is_candidate": True},
        ]
    )
    next_step = pd.DataFrame(
        [{"trade_date": date(2026, 1, 6), "bias_20d": "RISK_ON_BIAS"}]
    )
    group_transition = pd.DataFrame(
        [
            {"trade_date": date(2026, 1, 6), "asset_group": "SECTOR", "group_state_now": "WEAK"},
            {"trade_date": date(2026, 1, 6), "asset_group": "BOND", "group_state_now": "STRONG"},
        ]
    )

    ledger, _, _ = simulate_paper_execution(
        config=cfg,
        exposure_df=exposure,
        prices_df=_base_prices(),
        source_job="paper_trading_dag",
        decision_date=date(2026, 1, 6),
        simulation_date=date(2026, 1, 6),
        policy_df=policy,
        universe_df=universe,
        next_step_df=next_step,
        group_transition_df=group_transition,
        enable_predictor_gate=True,
    )

    # WEAK(SECTOR) -> XLE 매수 축소/차단, BOND(TLT) 중심 유지
    assert ledger[ledger["symbol"] == "XLE"].empty


def test_group_transition_v341_weak_one_does_not_trigger() -> None:
    cfg = BacktestConfig.from_preset("v3.4.1", start_date=date(2026, 1, 6), end_date=date(2026, 1, 7))
    group_transition = pd.DataFrame(
        [
            {"trade_date": date(2026, 1, 6), "asset_group": "SECTOR", "group_state_now": "WEAK"},
            {"trade_date": date(2026, 1, 6), "asset_group": "BOND", "group_state_now": "STRONG"},
        ]
    )
    new_cfg, meta, _, active = _apply_group_transition_gate_v341(
        cfg,
        group_transition,
        date(2026, 1, 6),
        short_signal="STABLE",
        mid_regime="NEUTRAL",
        relief_streak=0,
        group_gate_active=False,
    )
    assert active is False
    assert meta["group_gate_applied"] is False
    assert new_cfg.max_tactical_slots == cfg.max_tactical_slots


def test_group_transition_v341_reentry_mid_risk_on_releases_gate() -> None:
    cfg = BacktestConfig.from_preset("v3.4.1", start_date=date(2026, 1, 6), end_date=date(2026, 1, 7))
    group_transition = pd.DataFrame(
        [
            {"trade_date": date(2026, 1, 6), "asset_group": "SECTOR", "group_state_now": "WEAK"},
            {"trade_date": date(2026, 1, 6), "asset_group": "BOND", "group_state_now": "WEAK"},
        ]
    )
    new_cfg, meta, _, active = _apply_group_transition_gate_v341(
        cfg,
        group_transition,
        date(2026, 1, 6),
        short_signal="STABLE",
        mid_regime="RISK_ON",
        relief_streak=0,
        group_gate_active=True,
    )
    assert active is False
    assert meta["reentry_trigger"] == "MID_RISK_ON"
    assert new_cfg.max_tactical_slots == cfg.max_tactical_slots
