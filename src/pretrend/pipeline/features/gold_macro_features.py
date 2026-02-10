"""
Gold Macro Feature v1 — build_gold_macro_features.

Contract: docs/architecture/gold_design_contract.md §10
"""

from __future__ import annotations

from datetime import date
from typing import List, Optional, Tuple

from dateutil.relativedelta import relativedelta
import pandas as pd


# Daily indicator IDs use row-offset deltas; all others use month-offset.
DAILY_INDICATORS = frozenset({"US_TREASURY_10Y_YIELD"})

GOLD_MACRO_FEATURE_COLUMNS = [
    "indicator_id",
    "trade_date",
    "selected_observation_date",
    "selected_value",
    "selected_release_date",
    "delta_1m",
    "delta_3m",
    "delta_6m",
    "direction",
    "regime",
    "zscore_12m",
    "release_source",
    "is_assumption_based",
]


def build_gold_macro_features(
    df_macro_silver: pd.DataFrame,
    df_calendar: pd.DataFrame,
    trade_dates: List[date],
) -> pd.DataFrame:
    """Build Gold Macro Feature v1 for given trade_dates.

    Parameters
    ----------
    df_macro_silver : Silver macro (indicator_id, date, value).
    df_calendar : Calendar evidence (indicator_id, observation_date,
                  release_date, release_source, is_assumption_based).
    trade_dates : Target trade dates.

    Returns
    -------
    DataFrame with GOLD_MACRO_FEATURE_COLUMNS, sorted by
    (indicator_id, trade_date).
    """
    merged = pd.merge(
        df_macro_silver.rename(columns={"date": "observation_date"}),
        df_calendar,
        on=["indicator_id", "observation_date"],
        how="inner",
    )

    rows: list[dict] = []
    for td in trade_dates:
        for ind_id in sorted(merged["indicator_id"].unique()):
            row = _select_and_compute(merged, ind_id, td)
            if row is not None:
                rows.append(row)

    if not rows:
        return pd.DataFrame(columns=GOLD_MACRO_FEATURE_COLUMNS)

    result = pd.DataFrame(rows)[GOLD_MACRO_FEATURE_COLUMNS]
    result = result.sort_values(
        ["indicator_id", "trade_date"]
    ).reset_index(drop=True)
    return result


# ── Internal helpers ────────────────────────────────────────


def _select_and_compute(
    merged: pd.DataFrame,
    indicator_id: str,
    trade_date: date,
) -> Optional[dict]:
    """Select latest-as-of observation and compute features."""
    ind = merged[merged["indicator_id"] == indicator_id]

    # PIT gate: strict inequality
    pit_safe = ind[ind["release_date"] < trade_date].copy()
    if pit_safe.empty:
        return None

    pit_safe = pit_safe.sort_values("observation_date").reset_index(drop=True)

    # Latest-as-of: max release_date
    selected_idx = pit_safe["release_date"].idxmax()
    sel = pit_safe.loc[selected_idx]
    selected_value = sel["value"]
    selected_obs = sel["observation_date"]

    # Deltas
    is_daily = indicator_id in DAILY_INDICATORS
    if is_daily:
        d1, d3, d6 = _daily_deltas(pit_safe, selected_idx, selected_value)
    else:
        d1, d3, d6 = _monthly_deltas(pit_safe, selected_obs, selected_value)

    return {
        "indicator_id": indicator_id,
        "trade_date": trade_date,
        "selected_observation_date": selected_obs,
        "selected_value": selected_value,
        "selected_release_date": sel["release_date"],
        "delta_1m": d1,
        "delta_3m": d3,
        "delta_6m": d6,
        "direction": _direction(d1),
        "regime": _regime(d3, d6),
        "zscore_12m": None,
        "release_source": sel["release_source"],
        "is_assumption_based": sel["is_assumption_based"],
    }


def _monthly_deltas(
    pit_safe: pd.DataFrame,
    selected_obs: date,
    selected_value: float,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Month-offset deltas (1m / 3m / 6m)."""
    if pd.isna(selected_value):
        return None, None, None

    out: list[Optional[float]] = []
    for months in (1, 3, 6):
        target = selected_obs - relativedelta(months=months)
        match = pit_safe[pit_safe["observation_date"] == target]
        if match.empty or pd.isna(match.iloc[0]["value"]):
            out.append(None)
        else:
            out.append(selected_value - match.iloc[0]["value"])
    return out[0], out[1], out[2]


def _daily_deltas(
    pit_safe: pd.DataFrame,
    selected_idx: int,
    selected_value: float,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Row-offset deltas: shift(21) / shift(63) / shift(126)."""
    if pd.isna(selected_value):
        return None, None, None

    out: list[Optional[float]] = []
    for shift in (21, 63, 126):
        target_idx = selected_idx - shift
        if target_idx < 0:
            out.append(None)
        else:
            val = pit_safe.loc[target_idx, "value"]
            if pd.isna(val):
                out.append(None)
            else:
                out.append(selected_value - val)
    return out[0], out[1], out[2]


def _direction(delta_1m: Optional[float]) -> Optional[str]:
    """up / down / flat from delta_1m. NULL if delta is NULL."""
    if delta_1m is None or pd.isna(delta_1m):
        return None
    if delta_1m == 0:
        return "flat"
    return "up" if delta_1m > 0 else "down"


def _regime(
    delta_3m: Optional[float], delta_6m: Optional[float]
) -> Optional[str]:
    """tightening / easing / neutral. NULL if either delta is NULL."""
    if delta_3m is None or delta_6m is None:
        return None
    if pd.isna(delta_3m) or pd.isna(delta_6m):
        return None
    if delta_3m > 0 and delta_6m > 0:
        return "tightening"
    if delta_3m < 0 and delta_6m < 0:
        return "easing"
    return "neutral"
