from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

import pandas as pd

from pretrend.pipeline.broker.base import BrokerAdapter, BrokerBalance, BrokerPosition, OrderResult
from pretrend.pipeline.broker.order_manager import execute_from_ledger_rows, execute_from_virtual_fills, reconcile_positions


@dataclass
class _FakeAdapter(BrokerAdapter):
    def get_balance(self) -> BrokerBalance:
        return BrokerBalance(cash=1000.0, total_value=1000.0)

    def get_positions(self) -> list[BrokerPosition]:
        return [BrokerPosition(symbol="SPY", quantity=2.0, avg_price=500.0)]

    def get_current_price(self, symbol: str) -> float:
        return 100.0

    def place_buy_order(self, symbol: str, qty: int, order_type: str = "MARKET") -> OrderResult:
        return OrderResult(
            order_id="OID-BUY",
            symbol=symbol,
            side="BUY",
            quantity=float(qty),
            requested_price=None,
            filled_price=100.0,
            status="FILLED",
            executed_at=datetime.now(timezone.utc),
            raw={"ok": True},
        )

    def place_sell_order(self, symbol: str, qty: int, order_type: str = "MARKET") -> OrderResult:
        return OrderResult(
            order_id="OID-SELL",
            symbol=symbol,
            side="SELL",
            quantity=float(qty),
            requested_price=None,
            filled_price=100.0,
            status="FILLED",
            executed_at=datetime.now(timezone.utc),
            raw={"ok": True},
        )

    def get_order_status(self, order_id: str) -> str:
        return "FILLED"


def test_execute_from_virtual_fills_generates_orders() -> None:
    adapter = _FakeAdapter()
    orders_df, warnings = execute_from_virtual_fills(
        adapter,
        virtual_fills=["SPY BUY $250.00", "IAU SELL $90.00"],
        decision_date=date(2026, 3, 5),
        simulation_date=date(2026, 3, 5),
        source_job="paper_trading_dag",
    )
    assert warnings == []
    assert len(orders_df) == 2
    assert set(orders_df["side"].unique()) == {"BUY", "SELL"}


def test_reconcile_positions_detects_diff() -> None:
    recon = reconcile_positions(
        broker_positions=[BrokerPosition(symbol="SPY", quantity=5.0, avg_price=500.0)],
        paper_positions_df=pd.DataFrame(
            [
                {"trade_date": "2026-03-05", "symbol": "SPY", "shares": 3.0},
            ]
        ),
        decision_date=date(2026, 3, 5),
        source_job="paper_trading_dag",
    )
    assert len(recon) == 1
    row = recon.iloc[0]
    assert row["symbol"] == "SPY"
    assert float(row["diff"]) == 2.0


def test_execute_from_ledger_rows_generates_orders_and_fills() -> None:
    adapter = _FakeAdapter()
    ledger_df = pd.DataFrame(
        [
            {"symbol": "SPY", "action": "BUY", "shares": 2},
            {"symbol": "IAU", "action": "SELL", "shares": 1},
        ]
    )
    orders_df, fills_df, warnings = execute_from_ledger_rows(
        adapter,
        ledger_df=ledger_df,
        decision_date=date(2026, 3, 5),
        simulation_date=date(2026, 3, 5),
        source_job="paper_trading_dag",
    )
    assert warnings == []
    assert len(orders_df) == 2
    assert len(fills_df) == 2
    assert set(fills_df["fill_status"].unique()) == {"FILLED"}
