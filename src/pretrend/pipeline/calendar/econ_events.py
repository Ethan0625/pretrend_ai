from __future__ import annotations

import datetime as dt
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Tuple

import pandas as pd

from pretrend.pipeline.calendar.config import (
    ECON_EVENTS_SILVER_COLUMNS,
    KNOWN_INDICATOR_IDS,
    CalendarConfig,
)


# =========================
# 1. Context
# =========================

@dataclass
class EconEventsRunContext:
    """Execution context for econ_events Silver build."""

    run_id: str
    ingestion_ts: pd.Timestamp
    cfg: CalendarConfig


# =========================
# 2. Normalizer (Bronze → Silver)
# =========================

def normalize_econ_events(
    bronze_df: pd.DataFrame,
    ctx: EconEventsRunContext,
) -> pd.DataFrame:
    """
    Bronze econ_events → Silver econ_events.

    Steps:
      1. Validate indicator_id (reject unknown).
      2. Normalize release_ts_utc to UTC.
      3. Derive release_date_utc and has_timestamp.
      4. Dedup on (indicator_id, observation_date): keep earliest release_ts_utc.
      5. Enforce Silver column order.
    """
    if bronze_df.empty:
        return pd.DataFrame(columns=ECON_EVENTS_SILVER_COLUMNS)

    df = bronze_df.copy()

    # ── Step 1: reject unknown indicator_ids ──
    known_mask = df["indicator_id"].isin(KNOWN_INDICATOR_IDS)
    n_rejected = (~known_mask).sum()
    if n_rejected > 0:
        rejected_ids = df.loc[~known_mask, "indicator_id"].unique().tolist()
        print(
            f"[CalendarEconEvents] Rejected {n_rejected} rows "
            f"with unknown indicator_ids: {rejected_ids}"
        )
    df = df.loc[known_mask].copy()

    if df.empty:
        return pd.DataFrame(columns=ECON_EVENTS_SILVER_COLUMNS)

    # ── Step 2: normalize types ──
    df["observation_date"] = pd.to_datetime(df["observation_date"]).dt.date

    # release_ts_utc: ensure UTC timezone
    if "release_ts_utc" in df.columns:
        df["release_ts_utc"] = pd.to_datetime(df["release_ts_utc"], utc=True)
    else:
        df["release_ts_utc"] = pd.NaT

    # release_date_local: ensure date type
    if "release_date_local" in df.columns:
        df["release_date_local"] = pd.to_datetime(
            df["release_date_local"]
        ).dt.date
    else:
        df["release_date_local"] = None

    # ── Step 3: derive release_date_utc and has_timestamp ──
    has_ts = df["release_ts_utc"].notna()
    df["has_timestamp"] = has_ts

    # release_date_utc: from release_ts_utc.date() if available, else release_date_local
    df["release_date_utc"] = None
    df.loc[has_ts, "release_date_utc"] = (
        df.loc[has_ts, "release_ts_utc"].dt.date
    )
    no_ts_has_local = (~has_ts) & df["release_date_local"].notna()
    df.loc[no_ts_has_local, "release_date_utc"] = df.loc[
        no_ts_has_local, "release_date_local"
    ]

    # ── Step 4: dedup on (indicator_id, observation_date) ──
    # Keep earliest release_ts_utc; if all NaT, keep first row.
    df = df.sort_values(
        ["indicator_id", "observation_date", "release_ts_utc"],
        na_position="last",
    )
    df = df.drop_duplicates(
        subset=["indicator_id", "observation_date"],
        keep="first",
    )

    # ── Step 5: Silver metadata and column order ──
    df["run_id_silver"] = ctx.run_id
    df["ingestion_ts_silver"] = ctx.ingestion_ts

    # Ensure all Silver columns exist
    for col in ECON_EVENTS_SILVER_COLUMNS:
        if col not in df.columns:
            df[col] = None

    return df[ECON_EVENTS_SILVER_COLUMNS].copy().reset_index(drop=True)


# =========================
# 3. Writer (Silver, idempotent)
# =========================

def _partition_keys(df: pd.DataFrame) -> Iterable[Tuple[int, int]]:
    dates = pd.to_datetime(df["observation_date"])
    return sorted(set(zip(dates.dt.year, dates.dt.month)))


def write_silver_econ_events(
    df: pd.DataFrame,
    ctx: EconEventsRunContext,
) -> None:
    """
    Write Silver econ_events to partitioned Parquet.

    Partition: year=YYYY/month=MM/econ_events_YYYYMM.parquet
    Strategy: partition-level overwrite via tmp directory.
    """
    if df.empty:
        print("[CalendarEconEvents] Nothing to write.")
        return

    df = df.copy()
    df["observation_date"] = pd.to_datetime(df["observation_date"])

    silver_root = ctx.cfg.silver_econ_events_root
    tmp_root = silver_root / f"_tmp_run={ctx.run_id}"

    for year, month in _partition_keys(df):
        part = df[
            (df["observation_date"].dt.year == year)
            & (df["observation_date"].dt.month == month)
        ]
        if part.empty:
            continue

        tmp_dir = tmp_root / f"year={year:04d}" / f"month={month:02d}"
        final_dir = silver_root / f"year={year:04d}" / f"month={month:02d}"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        final_dir.mkdir(parents=True, exist_ok=True)

        filename = f"econ_events_{year:04d}{month:02d}.parquet"
        tmp_file = tmp_dir / filename
        final_file = final_dir / filename

        part.to_parquet(tmp_file, index=False)

        if final_file.exists():
            final_file.unlink()
        tmp_file.replace(final_file)

        print(f"[CalendarEconEvents] Saved: {final_file}")

    if tmp_root.exists():
        shutil.rmtree(tmp_root)
        print(f"[CalendarEconEvents] Cleaned tmp directory: {tmp_root}")
