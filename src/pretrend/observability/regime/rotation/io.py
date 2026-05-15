"""Group transition I/O helpers."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

from .history_io import load_group_transition_history


def load_group_transition_snapshot(strategy_root: Path) -> Optional[pd.DataFrame]:
    from pretrend.pipeline.utils.snapshot import load_strategy_snapshot

    return load_strategy_snapshot(strategy_root, "group_transition_signal")


def load_group_transition_for_runtime(
    strategy_root: Path,
    *,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> pd.DataFrame:
    """Load runtime group-transition table (history + snapshot merged)."""
    hist = load_group_transition_history(strategy_root, start_date=start_date, end_date=end_date)
    snap = load_group_transition_snapshot(strategy_root)

    frames = []
    if hist is not None and not hist.empty:
        frames.append(hist.copy())
    if snap is not None and not snap.empty:
        s = snap.copy()
        if "decision_date" in s.columns:
            s["decision_date_ref"] = pd.to_datetime(s["decision_date"]).dt.date
        elif "decision_date_ref" not in s.columns:
            s["decision_date_ref"] = pd.NaT
        frames.append(s)

    if not frames:
        return pd.DataFrame()

    out = pd.concat(frames, ignore_index=True)
    if "trade_date" in out.columns:
        out["trade_date"] = pd.to_datetime(out["trade_date"]).dt.date
    if "decision_date_ref" in out.columns:
        out["decision_date_ref"] = pd.to_datetime(out["decision_date_ref"], errors="coerce").dt.date

    if start_date is not None and "trade_date" in out.columns:
        out = out[out["trade_date"] >= start_date]
    if end_date is not None and "trade_date" in out.columns:
        out = out[out["trade_date"] <= end_date]

    key_cols = [c for c in ("trade_date", "asset_group", "decision_date_ref") if c in out.columns]
    if key_cols:
        sort_cols = key_cols + (["source_run_id"] if "source_run_id" in out.columns else [])
        out = out.sort_values(sort_cols).drop_duplicates(subset=key_cols, keep="last")

    return out.sort_values(["trade_date", "asset_group"]).reset_index(drop=True)


def load_universe_for_group_transition(strategy_root: Path) -> pd.DataFrame:
    """Load what_to_hold snapshot history as group-transition source."""
    from pretrend.pipeline.utils.snapshot import load_strategy_snapshot

    df = load_strategy_snapshot(strategy_root, "what_to_hold")
    if df is None or df.empty:
        return pd.DataFrame()
    if "decision_date" in df.columns:
        df["decision_date"] = pd.to_datetime(df["decision_date"], errors="coerce").dt.date
    elif "rebalance_date" in df.columns:
        df["rebalance_date"] = pd.to_datetime(df["rebalance_date"], errors="coerce").dt.date
    return df
