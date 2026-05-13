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


def test_execute_from_ledger_rows_scale_factor_scales_buy_qty() -> None:
    """qty_scale_factor가 BUY qty에만 적용되고, 소수 shares가 올바르게 스케일된다."""
    adapter = _FakeAdapter()
    # SIM 소수 shares: SPY=0.183 (scale=87x → round=16), IAU=0.871 (→round=76)
    ledger_df = pd.DataFrame(
        [
            {"symbol": "SPY", "action": "BUY", "shares": 0.183},
            {"symbol": "IAU", "action": "BUY", "shares": 0.871},
        ]
    )
    orders_df, fills_df, warnings = execute_from_ledger_rows(
        adapter,
        ledger_df=ledger_df,
        decision_date=date(2026, 3, 5),
        simulation_date=date(2026, 3, 5),
        source_job="paper_trading_dag",
        qty_scale_factor=87.0,
    )
    assert warnings == []
    assert len(orders_df) == 2
    spy_qty = float(orders_df[orders_df["symbol"] == "SPY"].iloc[0]["qty"])
    iau_qty = float(orders_df[orders_df["symbol"] == "IAU"].iloc[0]["qty"])
    assert spy_qty == round(0.183 * 87.0)
    assert iau_qty == round(0.871 * 87.0)


def test_execute_from_ledger_rows_scale_factor_applied_to_sell() -> None:
    """qty_scale_factor는 SELL qty에도 동일하게 적용된다 (broker 보유량이 scale된 수량이므로)."""
    adapter = _FakeAdapter()
    ledger_df = pd.DataFrame(
        [
            {"symbol": "TLT", "action": "SELL", "shares": 3.9},
        ]
    )
    orders_df, fills_df, warnings = execute_from_ledger_rows(
        adapter,
        ledger_df=ledger_df,
        decision_date=date(2026, 3, 5),
        simulation_date=date(2026, 3, 5),
        source_job="paper_trading_dag",
        qty_scale_factor=50.0,
    )
    assert warnings == []
    assert len(orders_df) == 1
    # SELL qty = round(3.9 * 50) = 195
    assert float(orders_df.iloc[0]["qty"]) == round(3.9 * 50.0)


def test_execute_from_ledger_rows_fractional_buy_without_scale_skipped() -> None:
    """scale_factor=1.0(기본)에서 소수 shares(<1)는 qty=0으로 스킵된다."""
    adapter = _FakeAdapter()
    ledger_df = pd.DataFrame(
        [
            {"symbol": "SPY", "action": "BUY", "shares": 0.183},
        ]
    )
    orders_df, fills_df, warnings = execute_from_ledger_rows(
        adapter,
        ledger_df=ledger_df,
        decision_date=date(2026, 3, 5),
        simulation_date=date(2026, 3, 5),
        source_job="paper_trading_dag",
        qty_scale_factor=1.0,
    )
    # round(0.183 * 1.0) = 0 → skipped
    assert len(orders_df) == 0


# ---------------------------------------------------------------------------
# check_and_cancel_unfilled
# ---------------------------------------------------------------------------

def _make_orders_df(*rows) -> pd.DataFrame:
    """Helper: build a minimal orders_df from (order_id, symbol, side, qty) tuples."""
    return pd.DataFrame(
        [{"order_id": r[0], "symbol": r[1], "side": r[2], "qty": float(r[3])} for r in rows]
    )


def _make_fills_df(*order_ids) -> pd.DataFrame:
    """Helper: build a minimal fills_df with given order_ids."""
    return pd.DataFrame(
        [{"order_id": oid, "symbol": "SPY", "filled_qty": 2.0} for oid in order_ids]
    )


def test_check_and_cancel_all_filled_returns_empty() -> None:
    """모든 주문이 FILLED면 cancelled_df 비어있고 warning 없음."""
    adapter = _FakeAdapter()  # get_order_status → FILLED
    orders_df = _make_orders_df(("ORD-1", "SPY", "BUY", 2), ("ORD-2", "IAU", "SELL", 1))
    cancelled_df, fills_out, warnings = check_and_cancel_unfilled(adapter, orders_df, wait_sec=0)
    assert cancelled_df.empty
    assert fills_out.empty
    assert warnings == []


def test_check_and_cancel_accepted_order_is_cancelled() -> None:
    """ACCEPTED 주문은 cancel_order() 호출되고 cancelled_df에 기록."""
    @dataclass
    class _AcceptedAdapter(_FakeAdapter):
        def get_order_status(self, order_id: str) -> str:
            return "ACCEPTED"

    adapter = _AcceptedAdapter()
    orders_df = _make_orders_df(("ORD-A", "SPY", "BUY", 3))
    cancelled_df, fills_out, warnings = check_and_cancel_unfilled(adapter, orders_df, wait_sec=0)

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
    cancelled_df, fills_out, warnings = check_and_cancel_unfilled(adapter, orders_df, wait_sec=0)

    assert cancelled_df.empty
    assert any("부분체결" in w for w in warnings)


def test_check_and_cancel_empty_orders_df() -> None:
    """orders_df가 비어있으면 즉시 빈 결과 반환."""
    adapter = _FakeAdapter()
    cancelled_df, fills_out, warnings = check_and_cancel_unfilled(adapter, pd.DataFrame(), wait_sec=0)
    assert cancelled_df.empty
    assert fills_out.empty
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
    cancelled_df, fills_out, warnings = check_and_cancel_unfilled(adapter, orders_df, wait_sec=0)

    assert len(cancelled_df) == 1
    assert cancelled_df.iloc[0]["cancel_status"] == "FAILED"
    assert any("취소 실패" in w for w in warnings)


def test_check_and_cancel_skips_failed_prefix_order_id() -> None:
    """FAILED- prefix order_id는 status 조회·취소 없이 warning만 기록."""
    adapter = _FakeAdapter()
    orders_df = _make_orders_df(("FAILED-abc12345", "SCHD", "BUY", 1))
    cancelled_df, fills_out, warnings = check_and_cancel_unfilled(adapter, orders_df, wait_sec=0)

    assert cancelled_df.empty
    assert any("주문접수 실패" in w for w in warnings)


# ---------------------------------------------------------------------------
# check_and_cancel_unfilled — actual_filled_qty (P4-1a)
# ---------------------------------------------------------------------------


def test_check_and_cancel_filled_with_ccnl_returns_actual_qty() -> None:
    """FILLED 주문이고 adapter가 _inquire_algo_ccnl을 지원하면 actual_filled_qty가 fills_df에 반영된다."""

    @dataclass
    class _CcnlAdapter(_FakeAdapter):
        def get_order_status(self, order_id: str) -> str:
            return "FILLED"

        def _inquire_algo_ccnl(self, order_id: str, *, order_date=None):
            return [{"FT_CCLD_QTY": "3", "FT_ORD_QTY": "3"}]

    adapter = _CcnlAdapter()
    orders_df = _make_orders_df(("ORD-C1", "SPY", "BUY", 3))
    fills_df = _make_fills_df("ORD-C1")
    cancelled_df, fills_out, warnings = check_and_cancel_unfilled(
        adapter, orders_df, fills_df=fills_df, wait_sec=0
    )
    assert cancelled_df.empty
    assert "actual_filled_qty" in fills_out.columns
    row = fills_out[fills_out["order_id"] == "ORD-C1"].iloc[0]
    assert float(row["actual_filled_qty"]) == 3.0


def test_check_and_cancel_cancelled_order_has_zero_actual_qty() -> None:
    """ACCEPTED → 취소 완료된 주문은 actual_filled_qty=0.0."""

    @dataclass
    class _AcceptedAdapter2(_FakeAdapter):
        def get_order_status(self, order_id: str) -> str:
            return "ACCEPTED"

    adapter = _AcceptedAdapter2()
    orders_df = _make_orders_df(("ORD-AC", "SPY", "BUY", 2))
    fills_df = _make_fills_df("ORD-AC")
    cancelled_df, fills_out, warnings = check_and_cancel_unfilled(
        adapter, orders_df, fills_df=fills_df, wait_sec=0
    )
    assert len(cancelled_df) == 1
    assert "actual_filled_qty" in fills_out.columns
    row = fills_out[fills_out["order_id"] == "ORD-AC"].iloc[0]
    assert float(row["actual_filled_qty"]) == 0.0


def test_check_and_cancel_fail_but_already_filled_is_not_error() -> None:
    """취소 실패했지만 재조회 시 FILLED 확인 → warning이 '취소 실패'가 아니라 '이미 체결됨 확인'으로 기록된다."""

    @dataclass
    class _FilledOnRecheckAdapter(_FakeAdapter):
        call_count: int = 0

        def get_order_status(self, order_id: str) -> str:
            self.call_count += 1
            # 1st call (fill check before cancel): inquiry 빈 응답으로 ACCEPTED 오판
            # 2nd call (recheck after cancel fail): 체결 확인
            return "ACCEPTED" if self.call_count == 1 else "FILLED"

        def cancel_order(self, order_id: str, symbol: str, qty: int, side: str) -> dict:
            return {"status": "FAILED", "error": "이미 체결된 주문", "raw": {}}

    adapter = _FilledOnRecheckAdapter()
    orders_df = _make_orders_df(("ORD-R", "SPY", "BUY", 2))
    cancelled_df, fills_out, warnings = check_and_cancel_unfilled(adapter, orders_df, wait_sec=0)

    assert len(cancelled_df) == 1
    assert cancelled_df.iloc[0]["cancel_status"] == "ALREADY_FILLED"
    assert not any("취소 실패" in w for w in warnings)
    assert any("이미 체결됨 확인" in w for w in warnings)


def test_check_and_cancel_empty_ccnl_response_gives_none_qty() -> None:
    """_inquire_algo_ccnl이 빈 리스트를 반환하면 actual_filled_qty=None + warning."""

    @dataclass
    class _EmptyCcnlAdapter(_FakeAdapter):
        def get_order_status(self, order_id: str) -> str:
            return "FILLED"

        def _inquire_algo_ccnl(self, order_id: str, *, order_date=None):
            return []  # VTS 500 또는 데이터 없음

    adapter = _EmptyCcnlAdapter()
    orders_df = _make_orders_df(("ORD-E", "IAU", "BUY", 1))
    fills_df = _make_fills_df("ORD-E")
    cancelled_df, fills_out, warnings = check_and_cancel_unfilled(
        adapter, orders_df, fills_df=fills_df, wait_sec=0
    )
    assert cancelled_df.empty
    assert "actual_filled_qty" in fills_out.columns
    row = fills_out[fills_out["order_id"] == "ORD-E"].iloc[0]
    assert row["actual_filled_qty"] is None or pd.isna(row["actual_filled_qty"])
    assert any("fill inquiry empty" in w for w in warnings)
