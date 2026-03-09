from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

import pandas as pd

from pretrend.pipeline.broker.base import BrokerAdapter, BrokerBalance, BrokerPosition, OrderResult
from pretrend.pipeline.broker.order_manager import (
    check_and_cancel_unfilled,
    execute_from_ledger_rows,
    execute_from_virtual_fills,
    reconcile_positions,
)


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

    def cancel_order(self, order_id: str, symbol: str, qty: int, side: str) -> dict:
        return {"status": "CANCELLED", "order_id": order_id, "raw": {}}


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


def test_execute_from_ledger_rows_applies_max_invested_ratio_budget(monkeypatch) -> None:
    class _CapAdapter(_FakeAdapter):
        def get_balance(self) -> BrokerBalance:
            # 1000 USD total
            return BrokerBalance(cash=0.0, total_value=1300000.0, currency="KRW", fx_usdkrw=1300.0)

        def get_positions(self) -> list[BrokerPosition]:
            # already invested 700 USD
            return [BrokerPosition(symbol="SPY", quantity=7.0, avg_price=100.0, market_price=100.0, market_value=700.0)]

    monkeypatch.setenv("PAPER_MAX_INVESTED_RATIO", "0.8")
    adapter = _CapAdapter()
    ledger_df = pd.DataFrame([{"symbol": "QQQ", "action": "BUY", "shares": 2}])
    orders_df, fills_df, warnings = execute_from_ledger_rows(
        adapter,
        ledger_df=ledger_df,
        decision_date=date(2026, 3, 6),
        simulation_date=date(2026, 3, 6),
        source_job="paper_trading_dag",
    )
    # budget = 1000*0.8 - 700 = 100 USD, price=100 => qty cap = 1
    assert warnings == []
    assert len(orders_df) == 1
    assert len(fills_df) == 1
    assert float(orders_df.iloc[0]["qty"]) == 1.0


# ---------------------------------------------------------------------------
# check_and_cancel_unfilled
# ---------------------------------------------------------------------------

def _make_orders_df(*rows) -> pd.DataFrame:
    """Helper: build a minimal orders_df from (order_id, symbol, side, qty) tuples."""
    return pd.DataFrame(
        [{"order_id": r[0], "symbol": r[1], "side": r[2], "qty": float(r[3])} for r in rows]
    )


def test_check_and_cancel_all_filled_returns_empty() -> None:
    """모든 주문이 FILLED면 cancelled_df 비어있고 warning 없음."""
    adapter = _FakeAdapter()  # get_order_status → FILLED
    orders_df = _make_orders_df(("ORD-1", "SPY", "BUY", 2), ("ORD-2", "IAU", "SELL", 1))
    cancelled_df, warnings = check_and_cancel_unfilled(adapter, orders_df, wait_sec=0)
    assert cancelled_df.empty
    assert warnings == []


def test_check_and_cancel_accepted_order_is_cancelled() -> None:
    """ACCEPTED 주문은 cancel_order() 호출되고 cancelled_df에 기록."""
    @dataclass
    class _AcceptedAdapter(_FakeAdapter):
        def get_order_status(self, order_id: str) -> str:
            return "ACCEPTED"

    adapter = _AcceptedAdapter()
    orders_df = _make_orders_df(("ORD-A", "SPY", "BUY", 3))
    cancelled_df, warnings = check_and_cancel_unfilled(adapter, orders_df, wait_sec=0)

    assert len(cancelled_df) == 1
    assert cancelled_df.iloc[0]["cancel_status"] == "CANCELLED"
    assert cancelled_df.iloc[0]["symbol"] == "SPY"
    assert any("취소 완료" in w for w in warnings)


def test_check_and_cancel_partial_filled_warns_only() -> None:
    """PARTIAL_FILLED는 취소하지 않고 경고만 남김."""
    @dataclass
    class _PartialAdapter(_FakeAdapter):
        def get_order_status(self, order_id: str) -> str:
            return "PARTIAL_FILLED"

    adapter = _PartialAdapter()
    orders_df = _make_orders_df(("ORD-P", "TLT", "SELL", 5))
    cancelled_df, warnings = check_and_cancel_unfilled(adapter, orders_df, wait_sec=0)

    assert cancelled_df.empty
    assert any("부분체결" in w for w in warnings)


def test_check_and_cancel_empty_orders_df() -> None:
    """orders_df가 비어있으면 즉시 빈 결과 반환."""
    adapter = _FakeAdapter()
    cancelled_df, warnings = check_and_cancel_unfilled(adapter, pd.DataFrame(), wait_sec=0)
    assert cancelled_df.empty
    assert warnings == []


def test_check_and_cancel_cancel_failure_recorded() -> None:
    """cancel_order가 FAILED를 반환해도 task는 계속되고 warning에 기록."""
    @dataclass
    class _FailCancelAdapter(_FakeAdapter):
        def get_order_status(self, order_id: str) -> str:
            return "ACCEPTED"

        def cancel_order(self, order_id: str, symbol: str, qty: int, side: str) -> dict:
            return {"status": "FAILED", "order_id": order_id, "error": "API timeout", "raw": {}}

    adapter = _FailCancelAdapter()
    orders_df = _make_orders_df(("ORD-F", "SPY", "BUY", 1))
    cancelled_df, warnings = check_and_cancel_unfilled(adapter, orders_df, wait_sec=0)

    assert len(cancelled_df) == 1
    assert cancelled_df.iloc[0]["cancel_status"] == "FAILED"
    assert any("취소 실패" in w for w in warnings)
