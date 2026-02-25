from __future__ import annotations

from datetime import date

import pandas as pd

from pretrend.pipeline.backtest.config import BacktestConfig
from pretrend.pipeline.backtest.paper_execution import simulate_paper_execution


def _prices(rows):
    return pd.DataFrame(rows)


def _exposure(rows):
    return pd.DataFrame(rows)


def test_nav_daily_and_cumulative_pnl_are_computed() -> None:
    cfg = BacktestConfig(start_date=date(2026, 1, 5), end_date=date(2026, 1, 6))
    exposure = _exposure(
        [
            {"trade_date": date(2026, 1, 5), "action": "HOLD", "next_invested_ratio": 0.60, "delta_ratio": 0.0},
            {"trade_date": date(2026, 1, 6), "action": "INCREASE", "next_invested_ratio": 0.60, "delta_ratio": 0.0},
        ]
    )
    prices = _prices(
        [
            {"trade_date": date(2026, 1, 5), "symbol": "SPY", "adj_close": 100.0},
            {"trade_date": date(2026, 1, 5), "symbol": "SCHD", "adj_close": 50.0},
            {"trade_date": date(2026, 1, 5), "symbol": "IAU", "adj_close": 20.0},
            {"trade_date": date(2026, 1, 6), "symbol": "SPY", "adj_close": 101.0},
            {"trade_date": date(2026, 1, 6), "symbol": "SCHD", "adj_close": 50.0},
            {"trade_date": date(2026, 1, 6), "symbol": "IAU", "adj_close": 20.0},
        ]
    )

    _, _, pf = simulate_paper_execution(
        config=cfg,
        exposure_df=exposure,
        prices_df=prices,
        source_job="paper_trading_dag",
        decision_date=date(2026, 1, 6),
        simulation_date=date(2026, 1, 6),
    )

    assert not pf.empty
    assert "nav" in pf.columns
    assert "daily_pnl" in pf.columns
    assert "cumulative_pnl" in pf.columns
    assert pf.iloc[-1]["cumulative_pnl"] is not None


def test_monthly_dca_reflected_in_total_invested_capital() -> None:
    cfg = BacktestConfig(start_date=date(2026, 1, 30), end_date=date(2026, 2, 3))
    exposure = _exposure(
        [
            {"trade_date": date(2026, 1, 30), "action": "HOLD", "next_invested_ratio": 0.60, "delta_ratio": 0.0},
            {"trade_date": date(2026, 2, 3), "action": "INCREASE", "next_invested_ratio": 0.60, "delta_ratio": 0.0},
        ]
    )
    prices = _prices(
        [
            {"trade_date": date(2026, 1, 30), "symbol": "SPY", "adj_close": 100.0},
            {"trade_date": date(2026, 1, 30), "symbol": "SCHD", "adj_close": 50.0},
            {"trade_date": date(2026, 1, 30), "symbol": "IAU", "adj_close": 20.0},
            {"trade_date": date(2026, 2, 3), "symbol": "SPY", "adj_close": 100.0},
            {"trade_date": date(2026, 2, 3), "symbol": "SCHD", "adj_close": 50.0},
            {"trade_date": date(2026, 2, 3), "symbol": "IAU", "adj_close": 20.0},
        ]
    )

    _, _, pf = simulate_paper_execution(
        config=cfg,
        exposure_df=exposure,
        prices_df=prices,
        source_job="paper_trading_dag",
        decision_date=date(2026, 2, 3),
        simulation_date=date(2026, 2, 3),
        initial_capital=1_000_000.0,
        monthly_addition=300_000.0,
    )

    assert pf.iloc[-1]["total_invested_capital"] >= 1_300_000.0
