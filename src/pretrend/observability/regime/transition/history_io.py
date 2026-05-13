"""Next-step history storage helpers.

History table key: (trade_date, decision_date_ref)
Partition: year=YYYY/month=MM
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd


def _history_root(strategy_root: Path) -> Path:
    return strategy_root / "next_step_history"


def _to_date(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
    return df


def _month_partition(root: Path, dt: date) -> Path:
    return root / f"year={dt.year:04d}" / f"month={dt.month:02d}"


def load_next_step_history(
    strategy_root: Path,
    *,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> pd.DataFrame:
    root = _history_root(strategy_root)
    files = list(root.rglob("*.parquet"))
    if not files:
        return pd.DataFrame()

    df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
    df = _to_date(df, "trade_date")
    df = _to_date(df, "decision_date_ref")

    if start_date is not None and "trade_date" in df.columns:
        df = df[df["trade_date"] >= start_date]
    if end_date is not None and "trade_date" in df.columns:
        df = df[df["trade_date"] <= end_date]
    return df.sort_values(["trade_date", "decision_date_ref"]).reset_index(drop=True)


def save_next_step_history_incremental(
    next_step_df: pd.DataFrame,
    strategy_root: Path,
    *,
    decision_date_ref: date,
    run_id: str,
) -> int:
    """Append one decision-date snapshot into monthly history partitions.

    Returns number of saved rows.
    """
    if next_step_df is None or next_step_df.empty:
        return 0

    root = _history_root(strategy_root)
    x = next_step_df.copy()
    x = _to_date(x, "trade_date")
    x["decision_date_ref"] = decision_date_ref
    if "source_run_id" not in x.columns:
        x["source_run_id"] = run_id

    saved = 0
    for (year, month), chunk in x.groupby([x["trade_date"].apply(lambda d: d.year), x["trade_date"].apply(lambda d: d.month)]):
        part = root / f"year={year:04d}" / f"month={month:02d}"
        part.mkdir(parents=True, exist_ok=True)
        out = part / f"next_step_history_{year:04d}{month:02d}.parquet"

        if out.exists():
            old = pd.read_parquet(out)
            old = _to_date(old, "trade_date")
            old = _to_date(old, "decision_date_ref")
            merged = pd.concat([old, chunk], ignore_index=True)
        else:
            merged = chunk.copy()

        merged = merged.sort_values(
            [c for c in ("trade_date", "decision_date_ref", "source_run_id") if c in merged.columns]
        )
        merged = merged.drop_duplicates(subset=["trade_date", "decision_date_ref"], keep="last")
        merged.to_parquet(out, index=False)
        saved += len(chunk)
    return saved


def save_next_step_history_full(
    next_step_df: pd.DataFrame,
    strategy_root: Path,
    *,
    decision_date_ref: date,
    run_id: str,
) -> int:
    """Rewrite history from full dataframe payload."""
    root = _history_root(strategy_root)
    if root.exists():
        # full refresh: remove old partitions first
        for f in root.rglob("*.parquet"):
            f.unlink()
    return save_next_step_history_incremental(
        next_step_df,
        strategy_root,
        decision_date_ref=decision_date_ref,
        run_id=run_id,
    )
