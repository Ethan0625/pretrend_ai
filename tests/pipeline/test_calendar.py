"""
Calendar Pipeline v1 — Tests ST1–ST11.

All tests use synthetic fixtures (no external API calls, no real data files).
"""

from datetime import date
from pathlib import Path

import pandas as pd
from pandas.api.types import is_string_dtype
import pytest

from pretrend.pipeline.calendar.config import (
    ECON_EVENTS_SILVER_COLUMNS,
    FRED_VINTAGES_SILVER_COLUMNS,
    KNOWN_INDICATOR_IDS,
)
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
from pretrend.pipeline.calendar.config import CalendarConfig
from pretrend.pipeline.calendar.runner import (
    load_bronze_econ_events,
    load_bronze_fred_vintages,
)
from pretrend.pipeline.macro_job import MacroJobConfig, MacroJobRunner


# ── Helpers ──────────────────────────────────────────────────


def _econ_ctx(tmp_path: Path, run_id: str = "test_run") -> EconEventsRunContext:
    cfg = CalendarConfig(data_root=tmp_path)
    return EconEventsRunContext(
        run_id=run_id,
        ingestion_ts=pd.Timestamp("2024-06-01T00:00:00", tz="UTC"),
        cfg=cfg,
    )


def _fred_ctx(tmp_path: Path, run_id: str = "test_run") -> FredVintagesRunContext:
    cfg = CalendarConfig(data_root=tmp_path)
    return FredVintagesRunContext(
        run_id=run_id,
        ingestion_ts=pd.Timestamp("2024-06-01T00:00:00", tz="UTC"),
        cfg=cfg,
    )


def _make_econ_bronze(
    indicator_id: str = "CPI_US_ALL_ITEMS_SA",
    observation_date: str = "2024-01-01",
    release_ts_utc: str | None = "2024-02-13 13:30:00+00:00",
    release_date_local: str | None = "2024-02-13",
    source: str = "manual_csv",
) -> pd.DataFrame:
    row = {
        "indicator_id": indicator_id,
        "observation_date": observation_date,
        "release_ts_utc": (
            pd.Timestamp(release_ts_utc) if release_ts_utc else pd.NaT
        ),
        "release_date_local": release_date_local,
        "source": source,
        "run_id": "bronze_run",
        "ingestion_ts": pd.Timestamp("2024-06-01"),
    }
    return pd.DataFrame([row])


def _make_fred_bronze(
    series_id: str = "CPIAUCSL",
    observation_date: str = "2024-01-01",
    vintage_date: str = "2024-02-15",
    source: str = "fred_api",
    run_id: str = "bronze_run",
) -> pd.DataFrame:
    row = {
        "series_id": series_id,
        "observation_date": observation_date,
        "vintage_date": vintage_date,
        "source": source,
        "run_id": run_id,
        "ingestion_ts": pd.Timestamp("2024-06-01"),
    }
    return pd.DataFrame([row])


def _load_all_parquets_under(path: Path) -> pd.DataFrame:
    files = sorted(path.rglob("*.parquet"))
    assert files, f"no parquet files found under {path}"
    return pd.concat([pd.read_parquet(p) for p in files], ignore_index=True)


def _write_partition_parquet(
    df: pd.DataFrame,
    root: Path,
    dataset: str,
    year: int,
    month: int,
) -> Path:
    out_dir = root / f"year={year:04d}" / f"month={month:02d}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{dataset}_{year:04d}{month:02d}.parquet"
    df.to_parquet(out_path, index=False)
    return out_path


# ════════════════════════════════════════════════════════════
# 5a. Schema Invariant Tests
# ════════════════════════════════════════════════════════════


class TestSchemaInvariants:
    """ST1, ST2, ST3 — column presence, dtypes, unknown rejection."""

    def test_st1_econ_events_silver_columns_and_dtypes(self, tmp_path: Path):
        """ST1: econ_events Silver has exactly the required columns."""
        ctx = _econ_ctx(tmp_path)
        bronze = _make_econ_bronze()
        silver = normalize_econ_events(bronze, ctx)

        assert list(silver.columns) == ECON_EVENTS_SILVER_COLUMNS
        assert is_string_dtype(silver["indicator_id"].dtype)  # TEXT
        assert silver["has_timestamp"].dtype == bool

        # observation_date should be date objects
        assert all(isinstance(d, date) for d in silver["observation_date"])

    def test_st2_fred_vintages_silver_columns_and_dtypes(self, tmp_path: Path):
        """ST2: fred_vintages Silver has exactly the required columns."""
        ctx = _fred_ctx(tmp_path)
        bronze = _make_fred_bronze()
        silver = normalize_fred_vintages(bronze, ctx)

        assert list(silver.columns) == FRED_VINTAGES_SILVER_COLUMNS
        assert is_string_dtype(silver["indicator_id"].dtype)  # TEXT
        assert silver["is_first_vintage"].dtype == bool

        # observation_date and vintage_date should be date objects
        assert all(isinstance(d, date) for d in silver["observation_date"])
        assert all(isinstance(d, date) for d in silver["vintage_date"])

    def test_st3_unknown_indicator_rejected(self, tmp_path: Path):
        """ST3: Rows with unknown indicator_id are dropped; known are kept."""
        ctx = _econ_ctx(tmp_path)

        known_row = _make_econ_bronze(indicator_id="CPI_US_ALL_ITEMS_SA")
        unknown_row = _make_econ_bronze(
            indicator_id="UNKNOWN_INDICATOR",
            observation_date="2024-02-01",
        )
        bronze = pd.concat([known_row, unknown_row], ignore_index=True)

        silver = normalize_econ_events(bronze, ctx)

        assert len(silver) == 1
        assert silver.iloc[0]["indicator_id"] == "CPI_US_ALL_ITEMS_SA"
        assert "UNKNOWN_INDICATOR" not in silver["indicator_id"].values

    def test_st3_unknown_series_id_rejected_fred(self, tmp_path: Path):
        """ST3 variant: fred_vintages rejects unknown series_ids."""
        ctx = _fred_ctx(tmp_path)

        known_row = _make_fred_bronze(series_id="CPIAUCSL")
        unknown_row = _make_fred_bronze(
            series_id="UNKNOWN_SERIES",
            observation_date="2024-02-01",
        )
        bronze = pd.concat([known_row, unknown_row], ignore_index=True)

        silver = normalize_fred_vintages(bronze, ctx)

        assert len(silver) == 1
        assert silver.iloc[0]["indicator_id"] == "CPI_US_ALL_ITEMS_SA"


# ════════════════════════════════════════════════════════════
# 5b. Idempotency Tests
# ════════════════════════════════════════════════════════════


class TestIdempotency:
    """ST4, ST5 — partition overwrite and stable output."""

    def test_st4_econ_events_partition_overwrite(self, tmp_path: Path):
        """ST4: Second write fully replaces first (econ_events)."""
        ctx1 = _econ_ctx(tmp_path, run_id="run_first")
        ctx2 = _econ_ctx(tmp_path, run_id="run_second")

        # First write
        bronze_v1 = _make_econ_bronze()
        silver_v1 = normalize_econ_events(bronze_v1, ctx1)
        write_silver_econ_events(silver_v1, ctx1)

        # Second write (different run_id → distinguishable)
        bronze_v2 = _make_econ_bronze()
        silver_v2 = normalize_econ_events(bronze_v2, ctx2)
        write_silver_econ_events(silver_v2, ctx2)

        loaded = _load_all_parquets_under(ctx2.cfg.silver_econ_events_root)

        assert len(loaded) == 1
        assert loaded.iloc[0]["run_id_silver"] == "run_second"
        assert (
            loaded.duplicated(
                subset=["indicator_id", "observation_date"]
            ).sum()
            == 0
        )

    def test_st5_fred_vintages_partition_overwrite_idempotent(
        self, tmp_path: Path
    ):
        """ST5: Identical input produces identical output across runs."""
        ctx1 = _fred_ctx(tmp_path, run_id="run_first")
        ctx2 = _fred_ctx(tmp_path, run_id="run_second")

        bronze = _make_fred_bronze()
        silver = normalize_fred_vintages(bronze, ctx1)
        write_silver_fred_vintages(silver, ctx1)

        silver_root = ctx1.cfg.silver_fred_vintages_root
        first_files = sorted(silver_root.rglob("*.parquet"))
        assert first_files

        # Write again with same data, different run_id
        silver2 = normalize_fred_vintages(bronze, ctx2)
        write_silver_fred_vintages(silver2, ctx2)

        second_files = sorted(silver_root.rglob("*.parquet"))

        # Same number of files, same file names
        assert len(first_files) == len(second_files)
        assert [f.name for f in first_files] == [f.name for f in second_files]

        loaded = _load_all_parquets_under(silver_root)
        assert len(loaded) == 1  # single row, not duplicated


# ════════════════════════════════════════════════════════════
# 5c. Uniqueness / Dedup Tests
# ════════════════════════════════════════════════════════════


class TestDedup:
    """ST6, ST7, ST8 — dedup rules and is_first_vintage."""

    def test_st6_econ_events_dedup_keeps_earliest_release(
        self, tmp_path: Path
    ):
        """ST6: Duplicate (indicator_id, observation_date) → keep earliest release_ts_utc."""
        ctx = _econ_ctx(tmp_path)

        row_early = _make_econ_bronze(
            release_ts_utc="2024-02-13 13:30:00+00:00",
        )
        row_late = _make_econ_bronze(
            release_ts_utc="2024-02-14 10:00:00+00:00",
        )
        bronze = pd.concat([row_late, row_early], ignore_index=True)

        silver = normalize_econ_events(bronze, ctx)

        assert len(silver) == 1
        ts = silver.iloc[0]["release_ts_utc"]
        assert ts.day == 13  # early row kept (Feb 13, not Feb 14)

    def test_st7_fred_vintages_dedup_on_triple(self, tmp_path: Path):
        """ST7: Duplicate (indicator_id, observation_date, vintage_date) → one row."""
        ctx = _fred_ctx(tmp_path)

        row1 = _make_fred_bronze(run_id="run_a")
        row2 = _make_fred_bronze(run_id="run_b")
        bronze = pd.concat([row1, row2], ignore_index=True)

        silver = normalize_fred_vintages(bronze, ctx)

        assert len(silver) == 1

    def test_st8_is_first_vintage_flag(self, tmp_path: Path):
        """ST8: is_first_vintage=True only for the earliest vintage_date."""
        ctx = _fred_ctx(tmp_path)

        rows = pd.concat(
            [
                _make_fred_bronze(vintage_date="2024-02-15"),
                _make_fred_bronze(vintage_date="2024-03-15"),
                _make_fred_bronze(vintage_date="2024-04-15"),
            ],
            ignore_index=True,
        )

        silver = normalize_fred_vintages(rows, ctx)

        assert len(silver) == 3

        first = silver.loc[
            silver["vintage_date"] == date(2024, 2, 15)
        ]
        assert len(first) == 1
        assert first.iloc[0]["is_first_vintage"] == True  # noqa: E712

        others = silver.loc[
            silver["vintage_date"] != date(2024, 2, 15)
        ]
        assert (others["is_first_vintage"] == False).all()  # noqa: E712


# ════════════════════════════════════════════════════════════
# 5d. Timezone Normalization Tests (econ_events only)
# ════════════════════════════════════════════════════════════


class TestTimezone:
    """ST9, ST10, ST11 — UTC normalization and NULL handling."""

    def test_st9_utc_conversion(self, tmp_path: Path):
        """ST9: Non-UTC timestamp is converted to UTC."""
        ctx = _econ_ctx(tmp_path)

        # CPI released at 8:30 AM Eastern = 13:30 UTC
        bronze = _make_econ_bronze(
            release_ts_utc="2024-02-13 08:30:00-05:00",
        )

        silver = normalize_econ_events(bronze, ctx)

        ts = silver.iloc[0]["release_ts_utc"]
        assert ts.tzinfo is not None  # timezone-aware
        assert str(ts.tzinfo) == "UTC"
        assert ts.hour == 13  # 08:30 EST = 13:30 UTC
        assert ts.minute == 30

        # release_date_utc should be the UTC date
        assert silver.iloc[0]["release_date_utc"] == date(2024, 2, 13)
        assert silver.iloc[0]["has_timestamp"] == True  # noqa: E712

    def test_st10_null_timestamp_with_local_date(self, tmp_path: Path):
        """ST10: NULL release_ts_utc with release_date_local → release_date_utc from local."""
        ctx = _econ_ctx(tmp_path)

        bronze = _make_econ_bronze(
            release_ts_utc=None,
            release_date_local="2024-01-15",
        )

        silver = normalize_econ_events(bronze, ctx)

        assert pd.isna(silver.iloc[0]["release_ts_utc"])
        assert silver.iloc[0]["release_date_utc"] == date(2024, 1, 15)
        assert silver.iloc[0]["has_timestamp"] == False  # noqa: E712

    def test_st11_both_timestamps_null(self, tmp_path: Path):
        """ST11: Both release_ts_utc and release_date_local NULL."""
        ctx = _econ_ctx(tmp_path)

        bronze = _make_econ_bronze(
            release_ts_utc=None,
            release_date_local=None,
        )

        silver = normalize_econ_events(bronze, ctx)

        assert pd.isna(silver.iloc[0]["release_ts_utc"])
        assert silver.iloc[0]["release_date_utc"] is None
        assert silver.iloc[0]["has_timestamp"] == False  # noqa: E712


class TestOperationalScope:
    """Guardrails for incremental DAG runs touching only current partitions."""

    def test_bronze_loaders_scope_to_requested_partitions(self, tmp_path: Path):
        cfg = CalendarConfig(data_root=tmp_path)

        old_fred = _make_fred_bronze(
            observation_date="2003-01-01",
            vintage_date="2003-02-01",
        )
        new_fred = _make_fred_bronze(
            observation_date="2026-04-01",
            vintage_date="2026-05-15",
        )
        _write_partition_parquet(
            old_fred,
            cfg.bronze_fred_vintages_root,
            "fred_vintages",
            2003,
            1,
        )
        _write_partition_parquet(
            new_fred,
            cfg.bronze_fred_vintages_root,
            "fred_vintages",
            2026,
            4,
        )

        loaded_fred = load_bronze_fred_vintages(
            cfg,
            partitions=["year=2026/month=04"],
        )

        assert len(loaded_fred) == 1
        assert (
            pd.Timestamp(loaded_fred.iloc[0]["observation_date"]).date()
            == date(2026, 4, 1)
        )

        old_econ = _make_econ_bronze(observation_date="2003-01-01")
        new_econ = _make_econ_bronze(
            observation_date="2026-04-01",
            release_date_local="2026-05-13",
        )
        _write_partition_parquet(
            old_econ,
            cfg.bronze_econ_events_root,
            "econ_events",
            2003,
            1,
        )
        _write_partition_parquet(
            new_econ,
            cfg.bronze_econ_events_root,
            "econ_events",
            2026,
            4,
        )

        loaded_econ = load_bronze_econ_events(
            cfg,
            partitions=["year=2026/month=04"],
        )

        assert len(loaded_econ) == 1
        assert (
            pd.Timestamp(loaded_econ.iloc[0]["observation_date"]).date()
            == date(2026, 4, 1)
        )

    def test_macro_silver_calendar_keeps_untouched_history(
        self,
        tmp_path: Path,
    ):
        cfg = CalendarConfig(data_root=tmp_path)

        old_fred_silver = normalize_fred_vintages(
            _make_fred_bronze(
                observation_date="2003-01-01",
                vintage_date="2003-02-01",
            ),
            _fred_ctx(tmp_path, run_id="old_run"),
        )
        write_silver_fred_vintages(
            old_fred_silver,
            _fred_ctx(tmp_path, run_id="old_run"),
        )
        old_econ_silver = normalize_econ_events(
            _make_econ_bronze(observation_date="2003-01-01"),
            _econ_ctx(tmp_path, run_id="old_run"),
        )
        write_silver_econ_events(
            old_econ_silver,
            _econ_ctx(tmp_path, run_id="old_run"),
        )

        _write_partition_parquet(
            _make_fred_bronze(
                observation_date="2026-04-01",
                vintage_date="2026-05-15",
            ),
            cfg.bronze_fred_vintages_root,
            "fred_vintages",
            2026,
            4,
        )
        _write_partition_parquet(
            _make_econ_bronze(
                observation_date="2026-04-01",
                release_date_local="2026-05-13",
            ),
            cfg.bronze_econ_events_root,
            "econ_events",
            2026,
            4,
        )

        runner = MacroJobRunner(MacroJobConfig(data_root=tmp_path))
        result = runner._run_silver_calendar(
            run_id="new_run",
            fred_partitions=["year=2026/month=04"],
            econ_partitions=["year=2026/month=04"],
        )

        assert result.row_count == 2

        old_fred_file = (
            cfg.silver_fred_vintages_root
            / "year=2003"
            / "month=01"
            / "fred_vintages_200301.parquet"
        )
        old_econ_file = (
            cfg.silver_econ_events_root
            / "year=2003"
            / "month=01"
            / "econ_events_200301.parquet"
        )
        new_fred_file = (
            cfg.silver_fred_vintages_root
            / "year=2026"
            / "month=04"
            / "fred_vintages_202604.parquet"
        )
        new_econ_file = (
            cfg.silver_econ_events_root
            / "year=2026"
            / "month=04"
            / "econ_events_202604.parquet"
        )

        assert pd.read_parquet(old_fred_file).iloc[0]["run_id_silver"] == "old_run"
        assert pd.read_parquet(old_econ_file).iloc[0]["run_id_silver"] == "old_run"
        assert pd.read_parquet(new_fred_file).iloc[0]["run_id_silver"] == "new_run"
        assert pd.read_parquet(new_econ_file).iloc[0]["run_id_silver"] == "new_run"
