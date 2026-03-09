"""Paper module I/O helpers."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional
import shutil
import uuid

import pandas as pd

from pretrend.pipeline.backtest._utils import load_strategy_snapshot
from pretrend.pipeline.strategy_engine.next_step.io import load_next_step_for_runtime
from pretrend.pipeline.strategy_engine.group_transition.io import load_group_transition_for_runtime


def load_prices(data_root: Path) -> pd.DataFrame:
    """Load Gold EOD adj_close table."""
    root = data_root / "gold" / "eod" / "eod_features"
    files = list(root.rglob("*.parquet"))
    if not files:
        return pd.DataFrame(columns=["symbol", "trade_date", "adj_close"])

    df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
    if "trade_date" in df.columns:
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date

    needed = ["symbol", "trade_date", "adj_close"]
    for col in needed:
        if col not in df.columns:
            return pd.DataFrame(columns=needed)

    return df[needed].dropna(subset=["adj_close"])


def latest_snapshot_by_date(df: Optional[pd.DataFrame], date_col: str) -> pd.DataFrame:
    """Keep latest decision_date row for each date_col."""
    if df is None or df.empty:
        return pd.DataFrame()

    x = df.copy()
    if date_col not in x.columns:
        return x

    x[date_col] = pd.to_datetime(x[date_col]).dt.date
    if "decision_date" in x.columns:
        x["decision_date"] = pd.to_datetime(x["decision_date"]).dt.date
        x = x.sort_values(["decision_date"])
        x = x.groupby([date_col], as_index=False).tail(1)
    return x.sort_values(date_col)


def load_strategy_stage(data_root: Path, stage: str, date_col: str) -> pd.DataFrame:
    """Load deduped strategy snapshot history for stage."""
    strategy_root = data_root / "strategy"
    df = load_strategy_snapshot(strategy_root, stage)
    return latest_snapshot_by_date(df, date_col)


def load_next_step_for_date(next_step_df: Optional[pd.DataFrame], td: date) -> Optional[pd.Series]:
    """Get latest next_step row at or before td."""
    if next_step_df is None or next_step_df.empty or "trade_date" not in next_step_df.columns:
        return None

    mask = next_step_df["trade_date"] <= td
    if not mask.any():
        return None

    latest = next_step_df.loc[mask, "trade_date"].max()
    row = next_step_df[next_step_df["trade_date"] == latest]
    if row.empty:
        return None
    return row.iloc[-1]


def load_next_step_runtime_stage(
    data_root: Path,
    *,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> pd.DataFrame:
    """Load runtime next-step table (snapshot + history merged)."""
    strategy_root = data_root / "strategy"
    return load_next_step_for_runtime(
        strategy_root,
        start_date=start_date,
        end_date=end_date,
    )


def load_group_transition_runtime_stage(
    data_root: Path,
    *,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> pd.DataFrame:
    """Load runtime group-transition table (snapshot + history merged)."""
    strategy_root = data_root / "strategy"
    return load_group_transition_for_runtime(
        strategy_root,
        start_date=start_date,
        end_date=end_date,
    )


def save_decision_partition(
    df: pd.DataFrame,
    root: Path,
    decision_date: date,
    stem: str,
    *,
    execution_mode: Optional[str] = None,
) -> Optional[Path]:
    """Save frame into decision_date partition.

    When execution_mode is provided, writes under:
    root/execution_mode=<MODE>/decision_date=YYYY-MM-DD/<stem>_YYYYMMDD.parquet
    """
    if df is None or df.empty:
        return None

    part = root
    if execution_mode:
        part = part / f"execution_mode={str(execution_mode).upper()}"
    part = part / f"decision_date={decision_date.isoformat()}"
    part.mkdir(parents=True, exist_ok=True)
    out = part / f"{stem}_{decision_date.strftime('%Y%m%d')}.parquet"
    tmp_out = part / f"{stem}_{decision_date.strftime('%Y%m%d')}_tmp_{uuid.uuid4().hex}.parquet"
    df.to_parquet(tmp_out, index=False)
    try:
        tmp_out.replace(out)
    except OSError:
        shutil.move(str(tmp_out), str(out))
    return out


def load_decision_partition(
    root: Path,
    decision_date: date,
    *,
    execution_mode: Optional[str] = None,
) -> pd.DataFrame:
    """Load decision partition with mode-first, legacy fallback."""
    paths = []
    if execution_mode:
        paths.append(root / f"execution_mode={str(execution_mode).upper()}" / f"decision_date={decision_date.isoformat()}")
    paths.append(root / f"decision_date={decision_date.isoformat()}")

    for part in paths:
        files = list(part.glob("*.parquet"))
        if files:
            return pd.read_parquet(files[0])
    return pd.DataFrame()
