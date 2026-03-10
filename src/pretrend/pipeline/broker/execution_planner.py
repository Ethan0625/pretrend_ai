"""Pure broker target order planner from strategy outputs + broker state."""
from __future__ import annotations

from datetime import date
from typing import Dict, Iterable, List, Tuple

import pandas as pd

from .base import BrokerPosition

_CORE_BASE_WEIGHTS: Dict[str, float] = {
    "SPY": 0.30,
    "SCHD": 0.50,
    "IAU": 0.20,
}
_TACTICAL_GROUPS: Tuple[str, ...] = ("SECTOR", "COMMODITY", "BOND", "COUNTRY")
_TACTICAL_WEIGHT: float = 0.15
_MIN_CORE_WEIGHT: float = 0.05
_EMPTY_COLUMNS: List[str] = [
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


def _empty_orders_df() -> pd.DataFrame:
    return pd.DataFrame(columns=_EMPTY_COLUMNS)


def _max_tactical_slots_allowed() -> int:
    max_deductable = sum(max(0.0, weight - _MIN_CORE_WEIGHT) for weight in _CORE_BASE_WEIGHTS.values())
    return int(max_deductable / _TACTICAL_WEIGHT)


def _compute_tactical_slots(
    what_to_hold_df: pd.DataFrame,
    effective_bias: str,
) -> List[Dict[str, object]]:
    if what_to_hold_df is None or what_to_hold_df.empty:
        return []
    if effective_bias == "RISK_OFF_BIAS":
        return []

    per_group_limit = 2 if effective_bias == "RISK_ON_BIAS" else 1
    df = what_to_hold_df.copy()
    if "is_candidate" in df.columns:
        df = df[df["is_candidate"] == True]
    if df.empty or "asset_group" not in df.columns or "symbol" not in df.columns:
        return []

    if "relative_strength" not in df.columns:
        df["relative_strength"] = 0.0
    df["relative_strength"] = pd.to_numeric(df["relative_strength"], errors="coerce").fillna(0.0)
    df["symbol"] = df["symbol"].astype(str).str.upper()
    df["asset_group"] = df["asset_group"].astype(str).str.upper()
    df = df[df["asset_group"].isin(_TACTICAL_GROUPS)]
    if df.empty:
        return []

    selected: List[Dict[str, object]] = []
    max_total_slots = _max_tactical_slots_allowed()
    for group in _TACTICAL_GROUPS:
        if len(selected) >= max_total_slots:
            break
        group_rows = (
            df[df["asset_group"] == group]
            .sort_values("relative_strength", ascending=False)
            .head(per_group_limit)
        )
        for _, row in group_rows.iterrows():
            if len(selected) >= max_total_slots:
                break
            selected.append(
                {
                    "symbol": str(row["symbol"]).upper(),
                    "asset_group": group,
                    "relative_strength": float(row.get("relative_strength", 0.0)),
                }
            )
    return selected


def _compute_core_weights(tactical_total: float) -> Dict[str, float]:
    core_remaining = max(0.0, 1.0 - tactical_total)
    return {
        symbol: round(base_weight * core_remaining, 10)
        for symbol, base_weight in _CORE_BASE_WEIGHTS.items()
    }


def _compute_target_weights(
    what_to_hold_df: pd.DataFrame,
    effective_bias: str,
) -> Tuple[Dict[str, float], Dict[str, str]]:
    tactical_slots = _compute_tactical_slots(what_to_hold_df, effective_bias)
    tactical_total = len(tactical_slots) * _TACTICAL_WEIGHT
    weights = _compute_core_weights(tactical_total)
    reasons = {symbol: "CORE_TARGET" for symbol in weights}
    for slot in tactical_slots:
        symbol = str(slot["symbol"])
        weights[symbol] = _TACTICAL_WEIGHT
        reasons[symbol] = f"TACTICAL_TARGET:{slot['asset_group']}"
    return weights, reasons


def _as_position_map(positions: Iterable[BrokerPosition]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for pos in positions:
        out[str(pos.symbol).upper()] = float(pos.quantity)
    return out


def build_broker_target_orders(
    *,
    action: str,
    next_invested_ratio: float,
    what_to_hold_df: pd.DataFrame,
    broker_nav_usd: float,
    broker_positions: List[BrokerPosition],
    live_prices: Dict[str, float],
    effective_bias: str,
    decision_date: date,
    simulation_date: date,
    source_job: str,
) -> pd.DataFrame:
    if str(action).upper() == "HOLD":
        return _empty_orders_df()

    position_map = _as_position_map(broker_positions)
    clean_prices = {
        str(symbol).upper(): float(price)
        for symbol, price in (live_prices or {}).items()
        if price is not None and float(price) > 0
    }
    rows: List[Dict[str, object]] = []

    if next_invested_ratio <= 0.0:
        for symbol, current_qty in position_map.items():
            price = clean_prices.get(symbol)
            if price is None:
                continue
            rows.append(
                {
                    "decision_date": decision_date,
                    "simulation_date": simulation_date,
                    "source_job": source_job,
                    "symbol": symbol,
                    "action": "SELL",
                    "qty": int(round(current_qty)),
                    "estimated_price": float(price),
                    "target_usd": 0.0,
                    "reason": "TARGET_ZERO",
                }
            )
        return pd.DataFrame(rows, columns=_EMPTY_COLUMNS)

    target_weights, reasons = _compute_target_weights(what_to_hold_df, effective_bias)
    symbols = list(target_weights.keys()) + [s for s in position_map.keys() if s not in target_weights]
    for symbol in symbols:
        price = clean_prices.get(symbol)
        if price is None:
            continue
        current_qty = float(position_map.get(symbol, 0.0))
        weight = float(target_weights.get(symbol, 0.0))
        target_usd = max(0.0, float(broker_nav_usd) * float(next_invested_ratio) * weight)
        target_qty = int(round(target_usd / price)) if price > 0 else 0
        delta = target_qty - current_qty
        if delta == 0:
            continue
        order_action = "BUY" if delta > 0 else "SELL"
        qty = int(abs(round(delta)))
        if qty <= 0:
            continue
        rows.append(
            {
                "decision_date": decision_date,
                "simulation_date": simulation_date,
                "source_job": source_job,
                "symbol": symbol,
                "action": order_action,
                "qty": qty,
                "estimated_price": float(price),
                "target_usd": round(target_usd, 6),
                "reason": reasons.get(symbol, "TARGET_EXIT" if target_qty == 0 else "TARGET_ADJUST"),
            }
        )

    return pd.DataFrame(rows, columns=_EMPTY_COLUMNS)
