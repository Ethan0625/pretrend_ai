from __future__ import annotations

from datetime import date

import pandas as pd

from pretrend.pipeline.backtest.config import BacktestConfig
from pretrend.pipeline.backtest.paper_execution import simulate_paper_execution


def test_schd_sell_is_blocked_on_decrease() -> None:
    cfg = BacktestConfig(start_date=date(2026, 1, 6), end_date=date(2026, 1, 9))
    exposure = pd.DataFrame(
        [
            {"trade_date": date(2026, 1, 6), "action": "INCREASE", "next_invested_ratio": 0.80, "delta_ratio": 0.20},
            {"trade_date": date(2026, 1, 9), "action": "DECREASE", "next_invested_ratio": 0.20, "delta_ratio": -0.60},
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

    ledger, _, _ = simulate_paper_execution(
        config=cfg,
        exposure_df=exposure,
        prices_df=prices,
        source_job="paper_trading_dag",
        decision_date=date(2026, 1, 9),
        simulation_date=date(2026, 1, 9),
        schd_sell_locked=True,
    )

    schd_sells = ledger[(ledger["symbol"] == "SCHD") & (ledger["action"] == "SELL")]
    assert schd_sells.empty


def test_weekday_rule_blocks_monday_increase_execution() -> None:
    cfg = BacktestConfig(start_date=date(2026, 1, 5), end_date=date(2026, 1, 6))
    exposure = pd.DataFrame(
        [
            {"trade_date": date(2026, 1, 5), "action": "INCREASE", "next_invested_ratio": 0.80, "delta_ratio": 0.20},
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": date(2026, 1, 5), "symbol": "SPY", "adj_close": 100.0},
            {"trade_date": date(2026, 1, 5), "symbol": "SCHD", "adj_close": 50.0},
            {"trade_date": date(2026, 1, 5), "symbol": "IAU", "adj_close": 20.0},
        ]
    )

    ledger, _, _ = simulate_paper_execution(
        config=cfg,
        exposure_df=exposure,
        prices_df=prices,
        source_job="paper_trading_dag",
        decision_date=date(2026, 1, 5),
        simulation_date=date(2026, 1, 5),
    )

    assert ledger.empty


def test_tactical_universe_is_reflected_when_policy_allows() -> None:
    cfg = BacktestConfig(start_date=date(2026, 1, 6), end_date=date(2026, 1, 7))
    exposure = pd.DataFrame(
        [
            {"trade_date": date(2026, 1, 6), "action": "INCREASE", "next_invested_ratio": 0.80, "delta_ratio": 0.20},
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": date(2026, 1, 6), "symbol": "SPY", "adj_close": 100.0},
            {"trade_date": date(2026, 1, 6), "symbol": "SCHD", "adj_close": 50.0},
            {"trade_date": date(2026, 1, 6), "symbol": "IAU", "adj_close": 20.0},
            {"trade_date": date(2026, 1, 6), "symbol": "XLE", "adj_close": 80.0},
        ]
    )
    policy = pd.DataFrame(
        [
            {
                "trade_date": date(2026, 1, 6),
                "run_universe": True,
                "risk_gate": True,
            }
        ]
    )
    universe = pd.DataFrame(
        [
            {"rebalance_date": date(2026, 1, 6), "symbol": "SPY", "asset_group": "SECTOR", "relative_strength": 0.00, "is_candidate": True},
            {"rebalance_date": date(2026, 1, 6), "symbol": "XLE", "asset_group": "SECTOR", "relative_strength": 0.10, "is_candidate": True},
        ]
    )

    ledger, _, _ = simulate_paper_execution(
        config=cfg,
        exposure_df=exposure,
        prices_df=prices,
        source_job="paper_trading_dag",
        decision_date=date(2026, 1, 6),
        simulation_date=date(2026, 1, 6),
        policy_df=policy,
        universe_df=universe,
    )

    assert not ledger[ledger["symbol"] == "XLE"].empty
