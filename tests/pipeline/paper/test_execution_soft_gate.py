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

    ledger, _, _, _ = simulate_paper_execution(
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

    ledger, _, _, _ = simulate_paper_execution(
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

    ledger, _, _, _ = simulate_paper_execution(
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


def test_v342a_exit_assist_relaxes_risk_off_bias_to_neutral() -> None:
    cfg = BacktestConfig(
        start_date=date(2026, 1, 6),
        end_date=date(2026, 1, 7),
        preset_name="v3.4.2a",
    )
    exposure = pd.DataFrame(
        [{"trade_date": date(2026, 1, 6), "action": "INCREASE", "next_invested_ratio": 0.80, "delta_ratio": 0.20}]
    )
    policy = pd.DataFrame(
        [{"trade_date": date(2026, 1, 6), "run_universe": True, "risk_gate": True, "short_signal": "RELIEF", "mid_regime": "NEUTRAL"}]
    )
    universe = pd.DataFrame(
        [
            {"rebalance_date": date(2026, 1, 6), "symbol": "SPY", "asset_group": "SECTOR", "relative_strength": 0.00, "is_candidate": True},
            {"rebalance_date": date(2026, 1, 6), "symbol": "XLE", "asset_group": "SECTOR", "relative_strength": 0.10, "is_candidate": True},
        ]
    )
    next_step = pd.DataFrame(
        [
            {
                "trade_date": date(2026, 1, 6),
                "bias_20d": "RISK_OFF_BIAS",
                "hard_gate_exit_assist_flag": True,
                "hard_gate_exit_assist_reason": "RUN_UNIVERSE_RECOVERY_RELIEF",
                "cooldown_compressed_flag": False,
                "bias_state_source": "BASELINE",
            }
        ]
    )
    ledger, _, _, _ = simulate_paper_execution(
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
    # assist 적용 시 RISK_OFF(슬롯0) 대신 NEUTRAL(슬롯1)로 완화되어 전술 매수가 가능해야 한다.
    assert not ledger[ledger["symbol"] == "XLE"].empty


def test_guardrail_nav_breach_blocks_increase() -> None:
    cfg = BacktestConfig(start_date=date(2026, 1, 6), end_date=date(2026, 1, 13))
    exposure = pd.DataFrame(
        [
            {"trade_date": date(2026, 1, 6), "action": "INCREASE", "next_invested_ratio": 0.60, "delta_ratio": 0.60},
            {"trade_date": date(2026, 1, 7), "action": "HOLD", "next_invested_ratio": 0.60, "delta_ratio": 0.0},
            {"trade_date": date(2026, 1, 12), "action": "HOLD", "next_invested_ratio": 0.60, "delta_ratio": 0.0},
            {"trade_date": date(2026, 1, 13), "action": "INCREASE", "next_invested_ratio": 0.80, "delta_ratio": 0.20},
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": date(2026, 1, 6), "symbol": "SPY", "adj_close": 100.0},
            {"trade_date": date(2026, 1, 6), "symbol": "SCHD", "adj_close": 50.0},
            {"trade_date": date(2026, 1, 6), "symbol": "IAU", "adj_close": 20.0},
            {"trade_date": date(2026, 1, 7), "symbol": "SPY", "adj_close": 40.0},
            {"trade_date": date(2026, 1, 7), "symbol": "SCHD", "adj_close": 20.0},
            {"trade_date": date(2026, 1, 7), "symbol": "IAU", "adj_close": 8.0},
            {"trade_date": date(2026, 1, 12), "symbol": "SPY", "adj_close": 40.0},
            {"trade_date": date(2026, 1, 12), "symbol": "SCHD", "adj_close": 20.0},
            {"trade_date": date(2026, 1, 12), "symbol": "IAU", "adj_close": 8.0},
            {"trade_date": date(2026, 1, 13), "symbol": "SPY", "adj_close": 40.0},
            {"trade_date": date(2026, 1, 13), "symbol": "SCHD", "adj_close": 20.0},
            {"trade_date": date(2026, 1, 13), "symbol": "IAU", "adj_close": 8.0},
        ]
    )
    ledger, _, pf, gs = simulate_paper_execution(
        config=cfg,
        exposure_df=exposure,
        prices_df=prices,
        source_job="paper_trading_dag",
        decision_date=date(2026, 1, 13),
        simulation_date=date(2026, 1, 13),
    )

    jan13 = ledger[ledger["trade_date"] == date(2026, 1, 13)]
    assert jan13.empty
    assert gs["paused"] is True
    assert gs["nav_breach"] is True
    assert bool(pf.iloc[-1]["guardrail_paused"]) is True


def test_max_invested_ratio_forces_staged_decrease_on_friday(monkeypatch) -> None:
    monkeypatch.setenv("PAPER_MAX_INVESTED_RATIO", "0.50")
    cfg = BacktestConfig(start_date=date(2026, 1, 6), end_date=date(2026, 1, 9))
    exposure = pd.DataFrame(
        [
            {"trade_date": date(2026, 1, 6), "action": "INCREASE", "next_invested_ratio": 0.80, "delta_ratio": 0.20},  # Tue
            {"trade_date": date(2026, 1, 9), "action": "HOLD", "next_invested_ratio": 0.80, "delta_ratio": 0.00},      # Fri
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": date(2026, 1, 6), "symbol": "SPY", "adj_close": 100.0},
            {"trade_date": date(2026, 1, 6), "symbol": "SCHD", "adj_close": 50.0},
            {"trade_date": date(2026, 1, 6), "symbol": "IAU", "adj_close": 20.0},
            {"trade_date": date(2026, 1, 9), "symbol": "SPY", "adj_close": 200.0},
            {"trade_date": date(2026, 1, 9), "symbol": "SCHD", "adj_close": 100.0},
            {"trade_date": date(2026, 1, 9), "symbol": "IAU", "adj_close": 40.0},
        ]
    )
    ledger, _, _, _ = simulate_paper_execution(
        config=cfg,
        exposure_df=exposure,
        prices_df=prices,
        source_job="paper_trading_dag",
        decision_date=date(2026, 1, 9),
        simulation_date=date(2026, 1, 9),
        schd_sell_locked=False,
    )
    fri_sells = ledger[(ledger["trade_date"] == date(2026, 1, 9)) & (ledger["action"] == "SELL")]
    assert not fri_sells.empty


def test_sim_schd_floor_blocks_sell_below_floor() -> None:
    cfg = BacktestConfig(start_date=date(2026, 1, 6), end_date=date(2026, 1, 9))
    exposure = pd.DataFrame(
        [
            {"trade_date": date(2026, 1, 6), "action": "INCREASE", "next_invested_ratio": 1.00, "delta_ratio": 1.00},
            {"trade_date": date(2026, 1, 9), "action": "DECREASE", "next_invested_ratio": 0.0, "delta_ratio": -1.00},
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": date(2026, 1, 6), "symbol": "SPY", "adj_close": 100.0},
            {"trade_date": date(2026, 1, 6), "symbol": "SCHD", "adj_close": 50.0},
            {"trade_date": date(2026, 1, 6), "symbol": "IAU", "adj_close": 20.0},
            {"trade_date": date(2026, 1, 9), "symbol": "SPY", "adj_close": 100.0},
            {"trade_date": date(2026, 1, 9), "symbol": "SCHD", "adj_close": 50.0},
            {"trade_date": date(2026, 1, 9), "symbol": "IAU", "adj_close": 20.0},
        ]
    )

    ledger, positions, _, _ = simulate_paper_execution(
        config=cfg,
        exposure_df=exposure,
        prices_df=prices,
        source_job="paper_trading_dag",
        decision_date=date(2026, 1, 9),
        simulation_date=date(2026, 1, 9),
        initial_capital=1000.0,
        monthly_addition=0.0,
        schd_sell_locked=False,
        schd_min_weight=0.20,
    )

    schd_friday_sell = ledger[
        (ledger["trade_date"] == date(2026, 1, 9))
        & (ledger["symbol"] == "SCHD")
        & (ledger["action"] == "SELL")
    ]
    assert not schd_friday_sell.empty
    assert float(schd_friday_sell["shares"].sum()) == 4.0

    schd_friday_pos = positions[
        (positions["trade_date"] == date(2026, 1, 9))
        & (positions["symbol"] == "SCHD")
    ]
    assert not schd_friday_pos.empty
    assert float(schd_friday_pos.iloc[-1]["shares"]) == 4.0


def test_sim_schd_floor_allows_sell_above_floor_only() -> None:
    cfg = BacktestConfig(start_date=date(2026, 1, 6), end_date=date(2026, 1, 9))
    exposure = pd.DataFrame(
        [
            {"trade_date": date(2026, 1, 6), "action": "INCREASE", "next_invested_ratio": 1.00, "delta_ratio": 1.00},
            {"trade_date": date(2026, 1, 9), "action": "DECREASE", "next_invested_ratio": 0.0, "delta_ratio": -1.00},
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": date(2026, 1, 6), "symbol": "SPY", "adj_close": 100.0},
            {"trade_date": date(2026, 1, 6), "symbol": "SCHD", "adj_close": 50.0},
            {"trade_date": date(2026, 1, 6), "symbol": "IAU", "adj_close": 20.0},
            {"trade_date": date(2026, 1, 9), "symbol": "SPY", "adj_close": 190.0},
            {"trade_date": date(2026, 1, 9), "symbol": "SCHD", "adj_close": 15.0},
            {"trade_date": date(2026, 1, 9), "symbol": "IAU", "adj_close": 3.0},
        ]
    )

    ledger, positions, _, _ = simulate_paper_execution(
        config=cfg,
        exposure_df=exposure,
        prices_df=prices,
        source_job="paper_trading_dag",
        decision_date=date(2026, 1, 9),
        simulation_date=date(2026, 1, 9),
        initial_capital=1000.0,
        monthly_addition=0.0,
        schd_sell_locked=False,
        schd_min_weight=0.20,
    )

    schd_friday_sell = ledger[
        (ledger["trade_date"] == date(2026, 1, 9))
        & (ledger["symbol"] == "SCHD")
        & (ledger["action"] == "SELL")
    ]
    assert schd_friday_sell.empty

    schd_friday_pos = positions[
        (positions["trade_date"] == date(2026, 1, 9))
        & (positions["symbol"] == "SCHD")
    ]
    assert not schd_friday_pos.empty
    assert float(schd_friday_pos.iloc[-1]["shares"]) == 10.0


def test_guardrail_peak_dd_breach_blocks_increase() -> None:
    cfg = BacktestConfig(start_date=date(2026, 1, 6), end_date=date(2026, 1, 13))
    exposure = pd.DataFrame(
        [
            {"trade_date": date(2026, 1, 6), "action": "INCREASE", "next_invested_ratio": 1.00, "delta_ratio": 1.00},
            {"trade_date": date(2026, 1, 7), "action": "HOLD", "next_invested_ratio": 1.00, "delta_ratio": 0.0},
            {"trade_date": date(2026, 1, 12), "action": "HOLD", "next_invested_ratio": 1.00, "delta_ratio": 0.0},
            {"trade_date": date(2026, 1, 13), "action": "INCREASE", "next_invested_ratio": 1.00, "delta_ratio": 0.0},
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": date(2026, 1, 6), "symbol": "SPY", "adj_close": 100.0},
            {"trade_date": date(2026, 1, 6), "symbol": "SCHD", "adj_close": 50.0},
            {"trade_date": date(2026, 1, 6), "symbol": "IAU", "adj_close": 20.0},
            {"trade_date": date(2026, 1, 7), "symbol": "SPY", "adj_close": 50.0},
            {"trade_date": date(2026, 1, 7), "symbol": "SCHD", "adj_close": 25.0},
            {"trade_date": date(2026, 1, 7), "symbol": "IAU", "adj_close": 10.0},
            {"trade_date": date(2026, 1, 12), "symbol": "SPY", "adj_close": 50.0},
            {"trade_date": date(2026, 1, 12), "symbol": "SCHD", "adj_close": 25.0},
            {"trade_date": date(2026, 1, 12), "symbol": "IAU", "adj_close": 10.0},
            {"trade_date": date(2026, 1, 13), "symbol": "SPY", "adj_close": 50.0},
            {"trade_date": date(2026, 1, 13), "symbol": "SCHD", "adj_close": 25.0},
            {"trade_date": date(2026, 1, 13), "symbol": "IAU", "adj_close": 10.0},
        ]
    )

    ledger, _, _, gs = simulate_paper_execution(
        config=cfg,
        exposure_df=exposure,
        prices_df=prices,
        source_job="paper_trading_dag",
        decision_date=date(2026, 1, 13),
        simulation_date=date(2026, 1, 13),
    )

    assert ledger[ledger["trade_date"] == date(2026, 1, 13)].empty
    assert gs["paused"] is True
    assert gs["peak_dd_breach"] is True


def test_guardrail_auto_resume_allows_increase() -> None:
    cfg = BacktestConfig(start_date=date(2026, 1, 6), end_date=date(2026, 1, 13))
    exposure = pd.DataFrame(
        [
            {"trade_date": date(2026, 1, 6), "action": "INCREASE", "next_invested_ratio": 0.60, "delta_ratio": 0.60},
            {"trade_date": date(2026, 1, 7), "action": "HOLD", "next_invested_ratio": 0.60, "delta_ratio": 0.0},
            {"trade_date": date(2026, 1, 12), "action": "HOLD", "next_invested_ratio": 0.60, "delta_ratio": 0.0},
            {"trade_date": date(2026, 1, 13), "action": "INCREASE", "next_invested_ratio": 0.80, "delta_ratio": 0.20},
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": date(2026, 1, 6), "symbol": "SPY", "adj_close": 100.0},
            {"trade_date": date(2026, 1, 6), "symbol": "SCHD", "adj_close": 50.0},
            {"trade_date": date(2026, 1, 6), "symbol": "IAU", "adj_close": 20.0},
            {"trade_date": date(2026, 1, 7), "symbol": "SPY", "adj_close": 40.0},
            {"trade_date": date(2026, 1, 7), "symbol": "SCHD", "adj_close": 20.0},
            {"trade_date": date(2026, 1, 7), "symbol": "IAU", "adj_close": 8.0},
            {"trade_date": date(2026, 1, 12), "symbol": "SPY", "adj_close": 95.0},
            {"trade_date": date(2026, 1, 12), "symbol": "SCHD", "adj_close": 47.5},
            {"trade_date": date(2026, 1, 12), "symbol": "IAU", "adj_close": 19.0},
            {"trade_date": date(2026, 1, 13), "symbol": "SPY", "adj_close": 95.0},
            {"trade_date": date(2026, 1, 13), "symbol": "SCHD", "adj_close": 47.5},
            {"trade_date": date(2026, 1, 13), "symbol": "IAU", "adj_close": 19.0},
        ]
    )

    ledger, _, _, gs = simulate_paper_execution(
        config=cfg,
        exposure_df=exposure,
        prices_df=prices,
        source_job="paper_trading_dag",
        decision_date=date(2026, 1, 13),
        simulation_date=date(2026, 1, 13),
    )

    assert gs["paused"] is False
    assert not ledger[ledger["trade_date"] == date(2026, 1, 13)].empty


def test_guardrail_panic_streak_warning_does_not_block() -> None:
    cfg = BacktestConfig(start_date=date(2026, 1, 5), end_date=date(2026, 1, 13))
    exposure = pd.DataFrame(
        [
            {"trade_date": date(2026, 1, 5), "action": "HOLD", "next_invested_ratio": 0.60, "delta_ratio": 0.0},
            {"trade_date": date(2026, 1, 6), "action": "HOLD", "next_invested_ratio": 0.60, "delta_ratio": 0.0},
            {"trade_date": date(2026, 1, 7), "action": "HOLD", "next_invested_ratio": 0.60, "delta_ratio": 0.0},
            {"trade_date": date(2026, 1, 8), "action": "HOLD", "next_invested_ratio": 0.60, "delta_ratio": 0.0},
            {"trade_date": date(2026, 1, 9), "action": "HOLD", "next_invested_ratio": 0.60, "delta_ratio": 0.0},
            {"trade_date": date(2026, 1, 12), "action": "HOLD", "next_invested_ratio": 0.60, "delta_ratio": 0.0},
            {"trade_date": date(2026, 1, 13), "action": "INCREASE", "next_invested_ratio": 0.80, "delta_ratio": 0.20},
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": date(2026, 1, 5), "symbol": "SPY", "adj_close": 100.0},
            {"trade_date": date(2026, 1, 5), "symbol": "SCHD", "adj_close": 50.0},
            {"trade_date": date(2026, 1, 5), "symbol": "IAU", "adj_close": 20.0},
            {"trade_date": date(2026, 1, 6), "symbol": "SPY", "adj_close": 100.0},
            {"trade_date": date(2026, 1, 6), "symbol": "SCHD", "adj_close": 50.0},
            {"trade_date": date(2026, 1, 6), "symbol": "IAU", "adj_close": 20.0},
            {"trade_date": date(2026, 1, 7), "symbol": "SPY", "adj_close": 100.0},
            {"trade_date": date(2026, 1, 7), "symbol": "SCHD", "adj_close": 50.0},
            {"trade_date": date(2026, 1, 7), "symbol": "IAU", "adj_close": 20.0},
            {"trade_date": date(2026, 1, 8), "symbol": "SPY", "adj_close": 100.0},
            {"trade_date": date(2026, 1, 8), "symbol": "SCHD", "adj_close": 50.0},
            {"trade_date": date(2026, 1, 8), "symbol": "IAU", "adj_close": 20.0},
            {"trade_date": date(2026, 1, 9), "symbol": "SPY", "adj_close": 100.0},
            {"trade_date": date(2026, 1, 9), "symbol": "SCHD", "adj_close": 50.0},
            {"trade_date": date(2026, 1, 9), "symbol": "IAU", "adj_close": 20.0},
            {"trade_date": date(2026, 1, 12), "symbol": "SPY", "adj_close": 100.0},
            {"trade_date": date(2026, 1, 12), "symbol": "SCHD", "adj_close": 50.0},
            {"trade_date": date(2026, 1, 12), "symbol": "IAU", "adj_close": 20.0},
            {"trade_date": date(2026, 1, 13), "symbol": "SPY", "adj_close": 100.0},
            {"trade_date": date(2026, 1, 13), "symbol": "SCHD", "adj_close": 50.0},
            {"trade_date": date(2026, 1, 13), "symbol": "IAU", "adj_close": 20.0},
        ]
    )
    policy = pd.DataFrame(
        [{"trade_date": td, "run_universe": True, "risk_gate": True, "short_signal": "PANIC"} for td in exposure["trade_date"]]
    )

    ledger, _, _, gs = simulate_paper_execution(
        config=cfg,
        exposure_df=exposure,
        prices_df=prices,
        source_job="paper_trading_dag",
        decision_date=date(2026, 1, 13),
        simulation_date=date(2026, 1, 13),
        policy_df=policy,
    )

    assert gs["panic_streak"] >= 5
    assert gs["paused"] is False
    assert not ledger[ledger["trade_date"] == date(2026, 1, 13)].empty
