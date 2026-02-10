from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set


# ── Indicator constants (re-exported from macro_features for single source of truth) ──

INDICATOR_CPI_HEADLINE = "CPI_US_ALL_ITEMS_SA"
INDICATOR_CPI_CORE = "CPI_US_CORE_SA"
INDICATOR_UNRATE = "US_UNEMPLOYMENT_RATE"
INDICATOR_FEDFUNDS = "US_FED_FUNDS_RATE"
INDICATOR_DGS10 = "US_TREASURY_10Y_YIELD"

KNOWN_INDICATOR_IDS: Set[str] = {
    INDICATOR_CPI_HEADLINE,
    INDICATOR_CPI_CORE,
    INDICATOR_UNRATE,
    INDICATOR_FEDFUNDS,
    INDICATOR_DGS10,
}

# FRED series_id → internal indicator_id mapping.
# Must stay in sync with FredSeriesSpec in pipeline/ingest/macro.py.
SERIES_ID_TO_INDICATOR_ID: Dict[str, str] = {
    "CPIAUCSL": INDICATOR_CPI_HEADLINE,
    "CPILFESL": INDICATOR_CPI_CORE,
    "UNRATE": INDICATOR_UNRATE,
    "FEDFUNDS": INDICATOR_FEDFUNDS,
    "DGS10": INDICATOR_DGS10,
}

# FRED release_id → indicator_ids mapping (monthly releases only).
# H.15 (release_id=18) excluded: weekly/daily release, DGS10/FEDFUNDS
# covered by fred_vintages is_first_vintage fallback.
RELEASE_ID_TO_INDICATORS: Dict[int, List[str]] = {
    10: [INDICATOR_CPI_HEADLINE, INDICATOR_CPI_CORE],  # Consumer Price Index
    50: [INDICATOR_UNRATE],                             # Employment Situation
}

# ── Bronze schema column lists ──

ECON_EVENTS_BRONZE_COLUMNS: List[str] = [
    "indicator_id",
    "observation_date",
    "release_ts_utc",
    "release_date_local",
    "source",
    "run_id",
    "ingestion_ts",
]

# ── Silver schema column lists (used for validation and ordering) ──

ECON_EVENTS_SILVER_COLUMNS: List[str] = [
    "indicator_id",
    "observation_date",
    "release_ts_utc",
    "release_date_utc",
    "source",
    "has_timestamp",
    "run_id_silver",
    "ingestion_ts_silver",
]

FRED_VINTAGES_SILVER_COLUMNS: List[str] = [
    "indicator_id",
    "observation_date",
    "vintage_date",
    "is_first_vintage",
    "source",
    "run_id_silver",
    "ingestion_ts_silver",
]


@dataclass
class CalendarConfig:
    """Calendar pipeline configuration."""

    data_root: Path = field(
        default_factory=lambda: Path(os.getenv("PRETREND_DATA_ROOT", "data"))
    )

    # Derived in __post_init__
    bronze_econ_events_root: Path = Path()
    bronze_fred_vintages_root: Path = Path()
    silver_econ_events_root: Path = Path()
    silver_fred_vintages_root: Path = Path()

    def __post_init__(self) -> None:
        self.bronze_econ_events_root = (
            self.data_root / "bronze" / "calendar" / "econ_events"
        )
        self.bronze_fred_vintages_root = (
            self.data_root / "bronze" / "calendar" / "fred_vintages"
        )
        self.silver_econ_events_root = (
            self.data_root / "silver" / "calendar" / "econ_events"
        )
        self.silver_fred_vintages_root = (
            self.data_root / "silver" / "calendar" / "fred_vintages"
        )

    @classmethod
    def from_env(cls) -> "CalendarConfig":
        return cls()
