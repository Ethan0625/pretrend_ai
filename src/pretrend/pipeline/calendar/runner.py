from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
from typing import List, Optional

import pandas as pd

from pretrend.pipeline.calendar.config import CalendarConfig
from pretrend.pipeline.calendar.econ_events import (
    EconEventsRunContext,
    normalize_econ_events,
    write_silver_econ_events,
)
from pretrend.pipeline.calendar.fred_vintages import (
    FredVintagesRunContext,
    normalize_fred_vintages,
    write_silver_fred_vintages,
)


# =========================
# Bronze Loaders
# =========================

def load_bronze_econ_events(cfg: CalendarConfig) -> pd.DataFrame:
    """Load all Bronze econ_events parquet files."""
    files = list(cfg.bronze_econ_events_root.rglob("*.parquet"))
    if not files:
        print(
            f"[CalendarRunner] No econ_events parquet under "
            f"{cfg.bronze_econ_events_root}"
        )
        return pd.DataFrame()
    return pd.concat(
        (pd.read_parquet(f) for f in files), ignore_index=True
    )


def load_bronze_fred_vintages(cfg: CalendarConfig) -> pd.DataFrame:
    """Load all Bronze fred_vintages parquet files."""
    files = list(cfg.bronze_fred_vintages_root.rglob("*.parquet"))
    if not files:
        print(
            f"[CalendarRunner] No fred_vintages parquet under "
            f"{cfg.bronze_fred_vintages_root}"
        )
        return pd.DataFrame()
    return pd.concat(
        (pd.read_parquet(f) for f in files), ignore_index=True
    )


# =========================
# Runners
# =========================

def run_econ_events_silver(
    cfg: Optional[CalendarConfig] = None,
) -> int:
    """Build Silver econ_events from Bronze. Returns row count."""
    cfg = cfg or CalendarConfig.from_env()
    run_id = dt.datetime.utcnow().strftime("cal_econ_%Y%m%d%H%M%S")

    ctx = EconEventsRunContext(
        run_id=run_id,
        ingestion_ts=pd.Timestamp.utcnow(),
        cfg=cfg,
    )

    bronze_df = load_bronze_econ_events(cfg)
    if bronze_df.empty:
        print("[CalendarRunner] No econ_events Bronze data. Exit.")
        return 0

    silver_df = normalize_econ_events(bronze_df, ctx)
    write_silver_econ_events(silver_df, ctx)

    print(
        f"[CalendarRunner] econ_events done. "
        f"run_id={run_id}, rows={len(silver_df)}"
    )
    return len(silver_df)


def run_fred_vintages_silver(
    cfg: Optional[CalendarConfig] = None,
) -> int:
    """Build Silver fred_vintages from Bronze. Returns row count."""
    cfg = cfg or CalendarConfig.from_env()
    run_id = dt.datetime.utcnow().strftime("cal_fred_%Y%m%d%H%M%S")

    ctx = FredVintagesRunContext(
        run_id=run_id,
        ingestion_ts=pd.Timestamp.utcnow(),
        cfg=cfg,
    )

    bronze_df = load_bronze_fred_vintages(cfg)
    if bronze_df.empty:
        print("[CalendarRunner] No fred_vintages Bronze data. Exit.")
        return 0

    silver_df = normalize_fred_vintages(bronze_df, ctx)
    write_silver_fred_vintages(silver_df, ctx)

    print(
        f"[CalendarRunner] fred_vintages done. "
        f"run_id={run_id}, rows={len(silver_df)}"
    )
    return len(silver_df)


# =========================
# CLI
# =========================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Calendar Silver (econ_events / fred_vintages)"
    )
    parser.add_argument(
        "--target",
        type=str,
        choices=["econ_events", "fred_vintages", "all"],
        default="all",
        help="Which Calendar table to build.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = CalendarConfig.from_env()

    if args.target in ("econ_events", "all"):
        run_econ_events_silver(cfg)
    if args.target in ("fred_vintages", "all"):
        run_fred_vintages_silver(cfg)


if __name__ == "__main__":
    main()
