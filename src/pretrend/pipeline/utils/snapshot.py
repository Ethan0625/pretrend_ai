"""Shared snapshot parquet helpers.

These helpers are infrastructure-level utilities used by Observability and
legacy Personal assets. They intentionally live outside Strategy/Backtest
ownership so runtime Observability code does not import frozen modules.
"""
from __future__ import annotations

import logging
import shutil
from datetime import date
from errno import EXDEV
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


def load_strategy_snapshot(
    root: Path,
    stage_name: str,
) -> Optional[pd.DataFrame]:
    """Load a parquet snapshot stage from a strategy-style root."""
    stage_root = root / stage_name
    if not stage_root.exists():
        logger.warning("[load_strategy_snapshot] No snapshot dir: %s", stage_root)
        return None

    files = list(stage_root.rglob("*.parquet"))
    if not files:
        return None

    frames = []
    for file in files:
        chunk = pd.read_parquet(file)
        if "decision_date" not in chunk.columns:
            decision_date = next(
                (
                    part.split("=", 1)[1]
                    for part in file.parts
                    if part.startswith("decision_date=")
                ),
                None,
            )
            chunk["decision_date"] = decision_date
        frames.append(chunk)

    out = pd.concat(frames, ignore_index=True)
    for column in ("trade_date", "rebalance_date", "decision_date"):
        if column in out.columns:
            out[column] = pd.to_datetime(out[column]).dt.date
    return out


def write_snapshot_atomic(
    df: pd.DataFrame,
    output_root: Path,
    stage_name: str,
    decision_date: date,
    run_id: str,
) -> Path:
    """Write one snapshot partition through a temp run directory."""
    dd_str = decision_date.strftime("%Y-%m-%d")
    dd_compact = decision_date.strftime("%Y%m%d")

    final_dir = output_root / stage_name / f"decision_date={dd_str}"
    final_file = final_dir / f"{stage_name}_{dd_compact}.parquet"

    tmp_dir = output_root / stage_name / f"_tmp_run={run_id}"
    tmp_file = tmp_dir / f"{stage_name}_{dd_compact}.parquet"

    tmp_dir.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir(parents=True, exist_ok=True)

    df.to_parquet(tmp_file, index=False)

    if final_file.exists():
        final_file.unlink()
    try:
        tmp_file.replace(final_file)
    except OSError as exc:
        if exc.errno != EXDEV:
            raise
        shutil.move(str(tmp_file), str(final_file))

    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)

    logger.info("[SnapshotIO] Saved snapshot: %s", final_file)
    return final_file
