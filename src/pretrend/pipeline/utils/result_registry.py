"""Result registry helpers (parquet partition based)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

UNIQUE_KEY = [
    "pipeline",
    "preset",
    "start_date",
    "end_date",
    "decision_date_ref",
    "code_version",
]


def append_registry_entry(root: Path, entry: Dict) -> Path:
    """Append one registry entry into parquet partition.

    Partition path:
      {root}/pipeline={pipeline}/run_date=YYYY-MM-DD/registry.parquet
    """
    pipeline = str(entry.get("pipeline", "unknown"))
    run_date = str(entry.get("created_at", datetime.utcnow().isoformat()))[:10]
    part = root / f"pipeline={pipeline}" / f"run_date={run_date}"
    part.mkdir(parents=True, exist_ok=True)
    out = part / "registry.parquet"

    cur = pd.DataFrame([entry])
    if out.exists():
        old = pd.read_parquet(out)
        merged = pd.concat([old, cur], ignore_index=True)
    else:
        merged = cur

    keep_cols = [c for c in UNIQUE_KEY if c in merged.columns]
    if keep_cols:
        merged = merged.sort_values([c for c in keep_cols + ["created_at"] if c in merged.columns])
        merged = merged.drop_duplicates(subset=keep_cols, keep="last")
    merged.to_parquet(out, index=False)
    return out


def query_registry(
    root: Path,
    *,
    pipeline: Optional[str] = None,
    preset: Optional[str] = None,
) -> pd.DataFrame:
    files = list(root.rglob("registry.parquet"))
    if not files:
        return pd.DataFrame()
    df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
    if pipeline is not None and "pipeline" in df.columns:
        df = df[df["pipeline"] == pipeline]
    if preset is not None and "preset" in df.columns:
        df = df[df["preset"] == preset]
    if "created_at" in df.columns:
        df = df.sort_values("created_at")
    return df.reset_index(drop=True)

