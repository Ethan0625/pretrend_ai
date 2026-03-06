"""Broker order execution + reconciliation helpers."""
from __future__ import annotations

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
                res = adapter.place_buy_order(symbol, qty=qty)
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
