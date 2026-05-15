"""Next Step Signal I/O helpers."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

from .history_io import load_next_step_history


def load_next_step_snapshot(strategy_root: Path) -> Optional[pd.DataFrame]:
    """Load merged next_step_signal snapshot history from strategy root."""
    from pretrend.pipeline.utils.snapshot import load_strategy_snapshot

    return load_strategy_snapshot(strategy_root, "next_step_signal")


def load_next_step_for_runtime(
    strategy_root: Path,
    *,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> pd.DataFrame:
    """Load runtime next-step table (snapshot + history merged).

    Priority:
      1) next_step_history (if available)
      2) next_step_signal snapshot fallback
    """
    hist = load_next_step_history(strategy_root, start_date=start_date, end_date=end_date)
    snap = load_next_step_snapshot(strategy_root)

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

    # same key dedupe; latest source_run_id kept for deterministic replay
    key_cols = [c for c in ("trade_date", "decision_date_ref") if c in out.columns]
    if key_cols:
        sort_cols = key_cols + (["source_run_id"] if "source_run_id" in out.columns else [])
        out = out.sort_values(sort_cols).drop_duplicates(subset=key_cols, keep="last")
    return out.sort_values("trade_date").reset_index(drop=True)
