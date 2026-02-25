from __future__ import annotations

from datetime import date

import pandas as pd

from pretrend.pipeline.backtest.config import BacktestConfig
from pretrend.pipeline.backtest.paper_execution import simulate_paper_execution


def test_positions_include_required_fields_and_gain_pct() -> None:
    cfg = BacktestConfig(start_date=date(2026, 1, 6), end_date=date(2026, 1, 7))
    exposure = pd.DataFrame(
        [
            {"trade_date": date(2026, 1, 6), "action": "INCREASE", "next_invested_ratio": 0.60, "delta_ratio": 0.0},
            {"trade_date": date(2026, 1, 7), "action": "HOLD", "next_invested_ratio": 0.60, "delta_ratio": 0.0},
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": date(2026, 1, 6), "symbol": "SPY", "adj_close": 100.0},
            {"trade_date": date(2026, 1, 6), "symbol": "SCHD", "adj_close": 50.0},
            {"trade_date": date(2026, 1, 6), "symbol": "IAU", "adj_close": 20.0},
            {"trade_date": date(2026, 1, 7), "symbol": "SPY", "adj_close": 101.0},
            {"trade_date": date(2026, 1, 7), "symbol": "SCHD", "adj_close": 50.0},
            {"trade_date": date(2026, 1, 7), "symbol": "IAU", "adj_close": 20.0},
        ]
    )

    _, positions, _ = simulate_paper_execution(
        config=cfg,
        exposure_df=exposure,
        prices_df=prices,
        source_job="paper_trading_dag",
        decision_date=date(2026, 1, 7),
        simulation_date=date(2026, 1, 7),
    )

    assert not positions.empty
    expected = {"symbol", "shares", "avg_cost", "eod_price", "market_value", "gain_pct", "weight"}
    assert expected.issubset(set(positions.columns))
    assert positions["market_value"].ge(0).all()
