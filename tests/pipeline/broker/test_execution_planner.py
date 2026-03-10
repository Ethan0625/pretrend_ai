from __future__ import annotations

from datetime import date

import pandas as pd

from pretrend.pipeline.broker.base import BrokerPosition
from pretrend.pipeline.broker.execution_planner import build_broker_target_orders


def _candidate_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_build_broker_target_orders_hold_returns_empty_df() -> None:
    out = build_broker_target_orders(
        action="HOLD",
        next_invested_ratio=0.8,
        what_to_hold_df=_candidate_df([]),
        broker_nav_usd=1000.0,
        broker_positions=[],
        live_prices={"SPY": 100.0},
        effective_bias="NEUTRAL_BIAS",
        decision_date=date(2026, 3, 10),
        simulation_date=date(2026, 3, 10),
        source_job="broker_mock_trading_dag",
    )
    assert out.empty
    assert list(out.columns) == [
        "decision_date",
        "simulation_date",
        "source_job",
        "symbol",
        "action",
        "qty",
        "estimated_price",
        "target_usd",
        "reason",
    ]


def test_build_broker_target_orders_risk_on_adds_core_and_tactical_orders() -> None:
    candidates = _candidate_df(
        [
            {"symbol": "XLE", "asset_group": "SECTOR", "relative_strength": 0.30, "is_candidate": True},
            {"symbol": "XLU", "asset_group": "SECTOR", "relative_strength": 0.20, "is_candidate": True},
            {"symbol": "DBA", "asset_group": "COMMODITY", "relative_strength": 0.25, "is_candidate": True},
            {"symbol": "USO", "asset_group": "COMMODITY", "relative_strength": 0.18, "is_candidate": True},
        ]
    )
    prices = {
        "SPY": 100.0,
        "SCHD": 50.0,
        "IAU": 20.0,
        "XLE": 40.0,
        "XLU": 80.0,
        "DBA": 25.0,
        "USO": 50.0,
    }
    out = build_broker_target_orders(
        action="INCREASE",
        next_invested_ratio=0.8,
        what_to_hold_df=candidates,
        broker_nav_usd=1000.0,
        broker_positions=[],
        live_prices=prices,
        effective_bias="RISK_ON_BIAS",
        decision_date=date(2026, 3, 10),
        simulation_date=date(2026, 3, 10),
        source_job="broker_mock_trading_dag",
    )
    assert {"SPY", "SCHD", "IAU"}.issubset(set(out["symbol"]))
    assert {"XLE", "XLU", "DBA", "USO"}.issubset(set(out["symbol"]))
    assert all(out["action"] == "BUY")
    assert len(out[out["reason"].str.startswith("TACTICAL_TARGET:SECTOR")]) == 2
    assert len(out[out["reason"].str.startswith("TACTICAL_TARGET:COMMODITY")]) == 2


def test_build_broker_target_orders_risk_off_only_core_orders() -> None:
    candidates = _candidate_df(
        [
            {"symbol": "XLE", "asset_group": "SECTOR", "relative_strength": 0.30, "is_candidate": True},
            {"symbol": "DBA", "asset_group": "COMMODITY", "relative_strength": 0.25, "is_candidate": True},
        ]
    )
    out = build_broker_target_orders(
        action="INCREASE",
        next_invested_ratio=0.8,
        what_to_hold_df=candidates,
        broker_nav_usd=1000.0,
        broker_positions=[],
        live_prices={"SPY": 100.0, "SCHD": 50.0, "IAU": 20.0, "XLE": 40.0, "DBA": 25.0},
        effective_bias="RISK_OFF_BIAS",
        decision_date=date(2026, 3, 10),
        simulation_date=date(2026, 3, 10),
        source_job="broker_mock_trading_dag",
    )
    assert set(out["symbol"]) == {"SPY", "SCHD", "IAU"}
    assert all(out["reason"] == "CORE_TARGET")


def test_build_broker_target_orders_missing_live_price_skips_symbol() -> None:
    candidates = _candidate_df(
        [
            {"symbol": "XLE", "asset_group": "SECTOR", "relative_strength": 0.30, "is_candidate": True},
        ]
    )
    out = build_broker_target_orders(
        action="INCREASE",
        next_invested_ratio=0.8,
        what_to_hold_df=candidates,
        broker_nav_usd=1000.0,
        broker_positions=[],
        live_prices={"SPY": 100.0, "SCHD": 50.0, "IAU": 20.0},
        effective_bias="RISK_ON_BIAS",
        decision_date=date(2026, 3, 10),
        simulation_date=date(2026, 3, 10),
        source_job="broker_mock_trading_dag",
    )
    assert "XLE" not in set(out["symbol"])
    assert set(out["symbol"]) == {"SPY", "SCHD", "IAU"}


def test_build_broker_target_orders_generates_buy_and_sell_deltas_vs_current_positions() -> None:
    out = build_broker_target_orders(
        action="DECREASE",
        next_invested_ratio=0.5,
        what_to_hold_df=_candidate_df([]),
        broker_nav_usd=1000.0,
        broker_positions=[
            BrokerPosition(symbol="SPY", quantity=5.0, avg_price=100.0),
            BrokerPosition(symbol="QQQ", quantity=3.0, avg_price=100.0),
        ],
        live_prices={"SPY": 100.0, "SCHD": 50.0, "IAU": 20.0, "QQQ": 100.0},
        effective_bias="RISK_OFF_BIAS",
        decision_date=date(2026, 3, 10),
        simulation_date=date(2026, 3, 10),
        source_job="broker_mock_trading_dag",
    )
    by_symbol = {row["symbol"]: row for _, row in out.iterrows()}
    assert by_symbol["SPY"]["action"] == "SELL"
    assert by_symbol["QQQ"]["action"] == "SELL"
    assert by_symbol["SCHD"]["action"] == "BUY"
    assert by_symbol["IAU"]["action"] == "BUY"


def test_build_broker_target_orders_zero_target_ratio_sells_all_positions() -> None:
    out = build_broker_target_orders(
        action="DECREASE",
        next_invested_ratio=0.0,
        what_to_hold_df=_candidate_df([]),
        broker_nav_usd=1000.0,
        broker_positions=[
            BrokerPosition(symbol="SPY", quantity=2.0, avg_price=100.0),
            BrokerPosition(symbol="IAU", quantity=4.0, avg_price=20.0),
        ],
        live_prices={"SPY": 100.0, "IAU": 20.0},
        effective_bias="RISK_OFF_BIAS",
        decision_date=date(2026, 3, 10),
        simulation_date=date(2026, 3, 10),
        source_job="broker_mock_trading_dag",
    )
    assert len(out) == 2
    assert set(out["action"]) == {"SELL"}
    assert set(out["reason"]) == {"TARGET_ZERO"}
