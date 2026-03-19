from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Iterable, Tuple

import pandas as pd

from pretrend.pipeline.calendar.config import (
    FRED_VINTAGES_SILVER_COLUMNS,
    SERIES_ID_TO_INDICATOR_ID,
    CalendarConfig,
)


# =========================
# 1. Context
# =========================

@dataclass
class FredVintagesRunContext:
    """Execution context for fred_vintages Silver build."""

    run_id: str
    ingestion_ts: pd.Timestamp
    cfg: CalendarConfig


# =========================
# 2. Normalizer (Bronze → Silver)
# =========================

def normalize_fred_vintages(
    bronze_df: pd.DataFrame,
    ctx: FredVintagesRunContext,
) -> pd.DataFrame:
    """
    Bronze fred_vintages → Silver fred_vintages.

    Steps:
      1. Map series_id → indicator_id (reject unknown series_ids).
      2. Normalize date types.
      3. Dedup on (indicator_id, observation_date, vintage_date): keep last ingested.
      4. Compute is_first_vintage flag.
      5. Enforce Silver column order.
    """
    if bronze_df.empty:
        return pd.DataFrame(columns=FRED_VINTAGES_SILVER_COLUMNS)

    df = bronze_df.copy()

    # ── Step 1: map series_id → indicator_id, reject unknown ──
    known_mask = df["series_id"].isin(SERIES_ID_TO_INDICATOR_ID)
    n_rejected = (~known_mask).sum()
    if n_rejected > 0:
        rejected_ids = df.loc[~known_mask, "series_id"].unique().tolist()
        print(
            f"[CalendarFredVintages] Rejected {n_rejected} rows "
            f"with unknown series_ids: {rejected_ids}"
        )
    df = df.loc[known_mask].copy()

    if df.empty:
        return pd.DataFrame(columns=FRED_VINTAGES_SILVER_COLUMNS)

    df["indicator_id"] = df["series_id"].map(SERIES_ID_TO_INDICATOR_ID)

    # ── Step 2: normalize date types ──
    df["observation_date"] = pd.to_datetime(df["observation_date"]).dt.date
    df["vintage_date"] = pd.to_datetime(df["vintage_date"]).dt.date

    # ── Step 3: dedup on (indicator_id, observation_date, vintage_date) ──
    # Keep last ingested (latest run_id / row order).
    df = df.drop_duplicates(
        subset=["indicator_id", "observation_date", "vintage_date"],
        keep="last",
    )

    # ── Step 4: compute is_first_vintage ──
    # For each (indicator_id, observation_date), the row with the earliest
    # vintage_date gets is_first_vintage=True.
    df = df.sort_values(
        ["indicator_id", "observation_date", "vintage_date"]
    )
    min_vintage = df.groupby(
        ["indicator_id", "observation_date"], sort=False
    )["vintage_date"].transform("min")
    df["is_first_vintage"] = df["vintage_date"] == min_vintage

    # ── Step 5: Silver metadata and column order ──
    df["run_id_silver"] = ctx.run_id
    df["ingestion_ts_silver"] = ctx.ingestion_ts

    for col in FRED_VINTAGES_SILVER_COLUMNS:
        if col not in df.columns:
            df[col] = None

    return df[FRED_VINTAGES_SILVER_COLUMNS].copy().reset_index(drop=True)


# =========================
# 3. Writer (Silver, idempotent)
# =========================

def _partition_keys(df: pd.DataFrame) -> Iterable[Tuple[int, int]]:
    dates = pd.to_datetime(df["observation_date"])
    return sorted(set(zip(dates.dt.year, dates.dt.month)))


def write_silver_fred_vintages(
    df: pd.DataFrame,
    ctx: FredVintagesRunContext,
) -> None:
    """
    Write Silver fred_vintages to partitioned Parquet.

    Partition: year=YYYY/month=MM/fred_vintages_YYYYMM.parquet
    Strategy: partition-level overwrite via tmp directory.
    """
    if df.empty:
        print("[CalendarFredVintages] Nothing to write.")
        return

    df = df.copy()
    df["observation_date"] = pd.to_datetime(df["observation_date"])

    silver_root = ctx.cfg.silver_fred_vintages_root
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

        filename = f"fred_vintages_{year:04d}{month:02d}.parquet"
        tmp_file = tmp_dir / filename
        final_file = final_dir / filename

        part.to_parquet(tmp_file, index=False)

        if final_file.exists():
            final_file.unlink()
        try:
            tmp_file.replace(final_file)
        except OSError:
            shutil.move(str(tmp_file), str(final_file))

        print(f"[CalendarFredVintages] Saved: {final_file}")

    if tmp_root.exists():
        shutil.rmtree(tmp_root)
        print(f"[CalendarFredVintages] Cleaned tmp directory: {tmp_root}")
