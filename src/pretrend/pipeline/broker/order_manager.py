"""Broker order execution + reconciliation helpers."""
from __future__ import annotations

import os
import time
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from .base import BrokerAdapter, BrokerPosition, OrderResult


def _to_order_rows(
    results: Sequence[OrderResult],
    *,
    decision_date: date,
    simulation_date: date,
    source_job: str,
) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for r in results:
        rows.append(
            {
                "order_date": decision_date,
                "simulation_date": simulation_date,
                "source_job": source_job,
                "order_id": r.order_id,
                "symbol": r.symbol,
                "side": r.side,
                "qty": float(r.quantity),
                "status": r.status,
                "requested_price": r.requested_price,
                "filled_price": r.filled_price,
                "executed_at": r.executed_at,
                "raw_json": str(r.raw),
            }
        )
    return pd.DataFrame(rows)


def _to_fill_rows(
    results: Sequence[OrderResult],
    *,
    decision_date: date,
    simulation_date: date,
    source_job: str,
) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for r in results:
        rows.append(
            {
                "fill_date": decision_date,
                "simulation_date": simulation_date,
                "source_job": source_job,
                "order_id": r.order_id,
                "symbol": r.symbol,
                "side": r.side,
                "filled_qty": float(r.quantity),
                "fill_status": r.status,
                "filled_price": r.filled_price,
                "executed_at": r.executed_at,
                "raw_json": str(r.raw),
            }
        )
    return pd.DataFrame(rows)


def execute_from_virtual_fills(
    adapter: BrokerAdapter,
    *,
    virtual_fills: Iterable[str],
    decision_date: date,
    simulation_date: date,
    source_job: str,
    max_orders: int = 20,
) -> Tuple[pd.DataFrame, List[str]]:
    """Execute broker orders from virtual fill lines.

    Expected fill format examples:
    - "SPY BUY $123.45"
    - "IAU SELL $42.00"
    """
    warnings: List[str] = []
    results: List[OrderResult] = []
    count = 0
    for line in virtual_fills:
        if count >= max_orders:
            warnings.append(f"broker order cap reached ({max_orders})")
            break
        parts = str(line).split()
        if len(parts) < 3:
            continue
        symbol = parts[0].strip().upper()
        side = parts[1].strip().upper()
        if side not in {"BUY", "SELL"}:
            continue
        try:
            price = adapter.get_current_price(symbol)
        except Exception:
            price = 0.0
        # conservative default qty=1 when quote unavailable
        qty = 1
        if price > 0:
            # parse amount token e.g. "$123.45"
            try:
                amt = float(parts[2].replace("$", "").replace(",", ""))
                qty = max(1, int(amt / price))
            except Exception:
                qty = 1
        try:
            if side == "BUY":
                res = adapter.place_buy_order(symbol, qty=qty)
            else:
                res = adapter.place_sell_order(symbol, qty=qty)
            results.append(res)
            count += 1
        except Exception as exc:
            warnings.append(f"{symbol} {side} failed: {exc}")
    return _to_order_rows(results, decision_date=decision_date, simulation_date=simulation_date, source_job=source_job), warnings


def execute_from_ledger_rows(
    adapter: BrokerAdapter,
    *,
    ledger_df: pd.DataFrame,
    decision_date: date,
    simulation_date: date,
    source_job: str,
    max_orders: int = 20,
) -> Tuple[pd.DataFrame, pd.DataFrame, List[str]]:
    """Execute broker orders from execution_ledger rows."""
    if ledger_df is None or ledger_df.empty:
        return pd.DataFrame(), pd.DataFrame(), ["execution_ledger empty"]

    warnings: List[str] = []
    results: List[OrderResult] = []
    count = 0
    remaining_budget_usd: Optional[float] = None

    def _safe_float(v: Any) -> Optional[float]:
        try:
            if v is None:
                return None
            return float(v)
        except Exception:
            return None

    def _init_balance_budget() -> None:
        nonlocal remaining_budget_usd
        if remaining_budget_usd is not None:
            return
        try:
            bal = adapter.get_balance()
            fx = bal.fx_usdkrw if bal.fx_usdkrw and bal.fx_usdkrw > 0 else None
            if (fx is None or fx <= 0) and hasattr(adapter, "get_usdkrw_rate"):
                try:
                    fx = adapter.get_usdkrw_rate()
                except Exception:
                    fx = None
            if fx and fx > 0:
                total_usd = float(bal.total_value) / float(fx)
            else:
                total_usd = None
            if total_usd is None:
                remaining_budget_usd = None
                return

            max_ratio = _safe_float(os.getenv("PAPER_MAX_INVESTED_RATIO", "1.0"))
            if max_ratio is None:
                max_ratio = 0.8
            max_ratio = min(1.0, max(0.0, max_ratio))

            invested_usd = 0.0
            try:
                for pos in adapter.get_positions():
                    mv = _safe_float(getattr(pos, "market_value", None))
                    if mv is None or mv <= 0:
                        qty = _safe_float(getattr(pos, "quantity", None)) or 0.0
                        mp = _safe_float(getattr(pos, "market_price", None))
                        if mp is None or mp <= 0:
                            mp = _safe_float(getattr(pos, "avg_price", None)) or 0.0
                        mv = qty * mp
                    invested_usd += max(0.0, mv)
            except Exception:
                invested_usd = 0.0

            budget_cap_usd = float(total_usd) * float(max_ratio)
            remaining_budget_usd = max(0.0, budget_cap_usd - invested_usd)
        except Exception:
            remaining_budget_usd = None
    for _, r in ledger_df.iterrows():
        if count >= max_orders:
            warnings.append(f"broker order cap reached ({max_orders})")
            break
        side_raw = str(r.get("action", "")).upper()
        symbol = str(r.get("symbol", "")).upper().strip()
        if not symbol:
            continue
        side = "BUY" if side_raw == "BUY" else ("SELL" if side_raw == "SELL" else "")
        if not side:
            continue
        try:
            qty = int(float(r.get("shares", 0.0)))
        except Exception:
            qty = 0
        if qty <= 0:
            continue
        try:
            if side == "BUY":
                # BUY qty cap: psamount first, fallback to balance-derived budget.
                px = 0.0
                try:
                    px = float(adapter.get_current_price(symbol))
                except Exception:
                    px = 0.0
                qty_cap: Optional[int] = None
                if px > 0 and hasattr(adapter, "get_orderable_cash_usd"):
                    try:
                        amt = adapter.get_orderable_cash_usd(symbol)
                        if amt is not None and amt > 0:
                            qty_cap = int(float(amt) / float(px))
                    except Exception:
                        qty_cap = None
                if qty_cap is None:
                    _init_balance_budget()
                    if px > 0 and remaining_budget_usd is not None and remaining_budget_usd > 0:
                        qty_cap = int(float(remaining_budget_usd) / float(px))
                if qty_cap is not None:
                    qty = min(qty, max(0, qty_cap))
                if qty <= 0:
                    warnings.append(f"{symbol} BUY skipped: no orderable budget")
                    continue
                res = adapter.place_buy_order(symbol, qty=qty)
                if px > 0 and remaining_budget_usd is not None:
                    remaining_budget_usd = max(0.0, float(remaining_budget_usd) - float(qty) * float(px))
            else:
                res = adapter.place_sell_order(symbol, qty=qty)
            results.append(res)
            count += 1
        except Exception as exc:
            warnings.append(f"{symbol} {side} failed: {exc}")

    orders_df = _to_order_rows(
        results,
        decision_date=decision_date,
        simulation_date=simulation_date,
        source_job=source_job,
    )
    fills_df = _to_fill_rows(
        results,
        decision_date=decision_date,
        simulation_date=simulation_date,
        source_job=source_job,
    )
    return orders_df, fills_df, warnings


def check_and_cancel_unfilled(
    adapter: BrokerAdapter,
    orders_df: pd.DataFrame,
    *,
    wait_sec: int = 30,
) -> Tuple[pd.DataFrame, List[str]]:
    """Wait, then cancel any ACCEPTED (unfilled) orders.

    Policy:
    - ACCEPTED  → cancel_order() 호출, cancelled_df에 기록
    - PARTIAL_FILLED → 경고만 (취소 안 함 — 잔여 처리는 2단계)
    - FILLED    → 정상, 기록 없음

    Returns:
        cancelled_df  : 취소된 주문 행 (order_id, symbol, side, status, cancel_status, error)
        warnings      : 경고 메시지 목록
    """
    warnings: List[str] = []
    cancelled_rows: List[Dict[str, Any]] = []

    if orders_df is None or orders_df.empty:
        return pd.DataFrame(), warnings

    # cancel_order가 없는 adapter는 경고만
    if not hasattr(adapter, "cancel_order"):
        warnings.append("adapter does not support cancel_order — fill check skipped")
        return pd.DataFrame(), warnings

    if wait_sec > 0:
        time.sleep(wait_sec)

    for _, row in orders_df.iterrows():
        order_id = str(row.get("order_id", "")).strip()
        symbol = str(row.get("symbol", "")).strip().upper()
        side = str(row.get("side", "")).strip().upper()
        qty = int(float(row.get("qty", 0) or 0))

        if not order_id or not symbol:
            continue

        try:
            fill_status = adapter.get_order_status(order_id)
        except Exception as exc:
            warnings.append(f"{symbol} get_order_status failed: {exc}")
            fill_status = "UNKNOWN"

        if fill_status == "FILLED":
            continue

        if fill_status == "PARTIAL_FILLED":
            warnings.append(f"{symbol} {side} order_id={order_id} 부분체결 — 잔여 수량 미처리 (수동 확인 필요)")
            continue

        # ACCEPTED or UNKNOWN → cancel
        try:
            result = adapter.cancel_order(order_id=order_id, symbol=symbol, qty=qty, side=side)
            cancel_status = result.get("status", "FAILED")
            error = result.get("error")
        except Exception as exc:
            cancel_status = "FAILED"
            error = str(exc)

        cancelled_rows.append(
            {
                "order_id": order_id,
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "fill_status": fill_status,
                "cancel_status": cancel_status,
                "error": error,
            }
        )

        if cancel_status == "CANCELLED":
            warnings.append(f"{symbol} {side} order_id={order_id} 미체결 → 취소 완료")
        else:
            warnings.append(f"{symbol} {side} order_id={order_id} 취소 실패: {error}")

    return pd.DataFrame(cancelled_rows), warnings


def reconcile_positions(
    *,
    broker_positions: Sequence[BrokerPosition],
    paper_positions_df: pd.DataFrame,
    decision_date: date,
    source_job: str,
) -> pd.DataFrame:
    paper_map: Dict[str, float] = {}
    if paper_positions_df is not None and not paper_positions_df.empty:
        x = paper_positions_df.copy()
        if "trade_date" in x.columns:
            x = x[pd.to_datetime(x["trade_date"]).dt.date <= decision_date]
            if not x.empty:
                latest = pd.to_datetime(x["trade_date"]).dt.date.max()
                x = x[pd.to_datetime(x["trade_date"]).dt.date == latest]
        for _, r in x.iterrows():
            sym = str(r.get("symbol", "")).upper()
            if not sym:
                continue
            paper_map[sym] = float(r.get("shares", 0.0))

    broker_map = {p.symbol.upper(): float(p.quantity) for p in broker_positions}
    symbols = sorted(set(paper_map) | set(broker_map))
    rows: List[Dict[str, Any]] = []
    for sym in symbols:
        p_qty = paper_map.get(sym, 0.0)
        b_qty = broker_map.get(sym, 0.0)
        diff = b_qty - p_qty
        diff_pct = None if p_qty == 0 else diff / p_qty
        rows.append(
            {
                "recon_date": decision_date,
                "source_job": source_job,
                "symbol": sym,
                "paper_shares": p_qty,
                "broker_shares": b_qty,
                "diff": diff,
                "diff_pct": diff_pct,
            }
        )
    return pd.DataFrame(rows)
