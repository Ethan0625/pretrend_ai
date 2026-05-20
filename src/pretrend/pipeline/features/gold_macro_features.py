"""
Gold Macro Feature v1 — build_gold_macro_features.

Contract: docs/architecture/gold_design_contract.md §10
"""

from __future__ import annotations

import logging
import shutil
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

from dateutil.relativedelta import relativedelta
import pandas as pd

logger = logging.getLogger(__name__)


# Daily indicator IDs use row-offset deltas; all others use month-offset.
DAILY_INDICATORS = frozenset({"US_TREASURY_10Y_YIELD"})

GOLD_MACRO_FEATURE_COLUMNS = [
    "indicator_id",
    "trade_date",
    "selected_observation_date",
    "selected_value",
    "selected_release_date",
    "delta_1m",
    "delta_3m",
    "delta_6m",
    "direction",
    "regime",
    "zscore_12m",
    "release_source",
    "is_assumption_based",
]


def build_gold_macro_features(
    df_macro_silver: pd.DataFrame,
    df_calendar: pd.DataFrame,
    trade_dates: List[date],
) -> pd.DataFrame:
    """Build Gold Macro Feature v1 for given trade_dates.

    Parameters
    ----------
    df_macro_silver : Silver macro (indicator_id, date, value).
    df_calendar : Calendar evidence (indicator_id, observation_date,
                  release_date, release_source, is_assumption_based).
    trade_dates : Target trade dates.

    Returns
    -------
    DataFrame with GOLD_MACRO_FEATURE_COLUMNS, sorted by
    (indicator_id, trade_date).
    """
    merged = pd.merge(
        df_macro_silver.rename(columns={"date": "observation_date"}),
        df_calendar,
        on=["indicator_id", "observation_date"],
        how="inner",
    )

    rows: list[dict] = []
    for td in trade_dates:
        for ind_id in sorted(merged["indicator_id"].unique()):
            row = _select_and_compute(merged, ind_id, td)
            if row is not None:
                rows.append(row)

    if not rows:
        return pd.DataFrame(columns=GOLD_MACRO_FEATURE_COLUMNS)

    result = pd.DataFrame(rows)[GOLD_MACRO_FEATURE_COLUMNS]
    result = result.sort_values(
        ["indicator_id", "trade_date"]
    ).reset_index(drop=True)
    return result


# ── Internal helpers ────────────────────────────────────────


def _select_and_compute(
    merged: pd.DataFrame,
    indicator_id: str,
    trade_date: date,
) -> Optional[dict]:
    """Select latest-as-of observation and compute features."""
    ind = merged[merged["indicator_id"] == indicator_id]

    # PIT gate: strict inequality
    pit_safe = ind[ind["release_date"] < trade_date].copy()
    if pit_safe.empty:
        return None

    pit_safe = pit_safe.sort_values("observation_date").reset_index(drop=True)

    # Latest-as-of: max release_date. Some pandas versions cannot idxmax()
    # object-dtype Python date values, so compare through datetime64.
    release_rank = pd.to_datetime(pit_safe["release_date"])
    selected_idx = release_rank.idxmax()
    sel = pit_safe.loc[selected_idx]
    selected_value = sel["value"]
    selected_obs = sel["observation_date"]

    # Deltas
    is_daily = indicator_id in DAILY_INDICATORS
    if is_daily:
        d1, d3, d6 = _daily_deltas(pit_safe, selected_idx, selected_value)
    else:
        d1, d3, d6 = _monthly_deltas(pit_safe, selected_obs, selected_value)

    return {
        "indicator_id": indicator_id,
        "trade_date": trade_date,
        "selected_observation_date": selected_obs,
        "selected_value": selected_value,
        "selected_release_date": sel["release_date"],
        "delta_1m": d1,
        "delta_3m": d3,
        "delta_6m": d6,
        "direction": _direction(d1),
        "regime": _regime(d3, d6),
        "zscore_12m": _zscore_12m(pit_safe, selected_idx, selected_value, is_daily),
        "release_source": sel["release_source"],
        "is_assumption_based": sel["is_assumption_based"],
    }


def _monthly_deltas(
    pit_safe: pd.DataFrame,
    selected_obs: date,
    selected_value: float,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Month-offset deltas (1m / 3m / 6m)."""
    if pd.isna(selected_value):
        return None, None, None

    out: list[Optional[float]] = []
    for months in (1, 3, 6):
        target = selected_obs - relativedelta(months=months)
        match = pit_safe[pit_safe["observation_date"] == target]
        if match.empty or pd.isna(match.iloc[0]["value"]):
            out.append(None)
        else:
            out.append(selected_value - match.iloc[0]["value"])
    return out[0], out[1], out[2]


def _daily_deltas(
    pit_safe: pd.DataFrame,
    selected_idx: int,
    selected_value: float,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Row-offset deltas: shift(21) / shift(63) / shift(126)."""
    if pd.isna(selected_value):
        return None, None, None

    out: list[Optional[float]] = []
    for shift in (21, 63, 126):
        target_idx = selected_idx - shift
        if target_idx < 0:
            out.append(None)
        else:
            val = pit_safe.loc[target_idx, "value"]
            if pd.isna(val):
                out.append(None)
            else:
                out.append(selected_value - val)
    return out[0], out[1], out[2]


def _direction(delta_1m: Optional[float]) -> Optional[str]:
    """up / down / flat from delta_1m. NULL if delta is NULL."""
    if delta_1m is None or pd.isna(delta_1m):
        return None
    if delta_1m == 0:
        return "flat"
    return "up" if delta_1m > 0 else "down"


def _regime(
    delta_3m: Optional[float], delta_6m: Optional[float]
) -> Optional[str]:
    """tightening / easing / neutral. NULL if either delta is NULL."""
    if delta_3m is None or delta_6m is None:
        return None
    if pd.isna(delta_3m) or pd.isna(delta_6m):
        return None
    if delta_3m > 0 and delta_6m > 0:
        return "tightening"
    if delta_3m < 0 and delta_6m < 0:
        return "easing"
    return "neutral"


def _zscore_12m(
    pit_safe: pd.DataFrame,
    selected_idx: int,
    selected_value: float,
    is_daily: bool,
) -> Optional[float]:
    """12-month rolling z-score.

    Window: 252 rows for daily indicators, 12 rows for monthly.
    Returns None when selected_value is NULL, history is insufficient,
    or std is zero/NaN.
    """
    if selected_value is None or pd.isna(selected_value):
        return None
    window = 252 if is_daily else 12
    values = pit_safe["value"].iloc[: selected_idx + 1]
    if len(values) < window:
        return None
    trailing = values.iloc[-window:]
    m = trailing.mean()
    s = trailing.std()
    if pd.isna(s) or s == 0:
        return None
    return float((selected_value - m) / s)


# ── Integration helpers (loaders, calendar builder, writer) ───

def _iter_month_starts(start: date, end: date):
    current = start.replace(day=1)
    end_month = end.replace(day=1)
    while current <= end_month:
        yield current
        current = (pd.Timestamp(current) + pd.DateOffset(months=1)).date()


def _file_month_in_range(
    path: Path,
    start_date: Optional[date],
    end_date: Optional[date],
) -> bool:
    if start_date is None and end_date is None:
        return True

    year = None
    month = None
    for part in path.parts:
        if part.startswith("year="):
            year = int(part.split("=", 1)[1])
        elif part.startswith("month="):
            month = int(part.split("=", 1)[1])
    if year is None or month is None:
        return True

    file_month = date(year, month, 1)
    if start_date is not None and file_month < start_date.replace(day=1):
        return False
    if end_date is not None and file_month > end_date.replace(day=1):
        return False
    return True


def _list_silver_macro_files(
    silver_macro_root: Path,
    start_date: Optional[date],
    end_date: Optional[date],
) -> list[Path]:
    if start_date is None or end_date is None:
        return [
            path
            for path in sorted(silver_macro_root.rglob("*.parquet"))
            if _file_month_in_range(path, start_date, end_date)
            and not any(part.startswith("_tmp_run=") for part in path.parts)
        ]

    files: list[Path] = []
    for month_start in _iter_month_starts(start_date, end_date):
        month_dir = (
            silver_macro_root
            / f"year={month_start.year:04d}"
            / f"month={month_start.month:02d}"
        )
        files.extend(
            path
            for path in month_dir.glob("*.parquet")
            if not any(part.startswith("_tmp_run=") for part in path.parts)
        )
    return sorted(set(files))


def load_silver_macro(
    silver_macro_root: Path,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> pd.DataFrame:
    """Silver macro features에서 Gold 입력 컬럼만 로드.

    Returns DataFrame with columns: indicator_id, date, value.
    """
    files = _list_silver_macro_files(silver_macro_root, start_date, end_date)
    if not files:
        logger.warning(
            "[GoldMacro] No Silver macro parquet under %s", silver_macro_root
        )
        return pd.DataFrame(columns=["indicator_id", "date", "value"])
    df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    if start_date is not None:
        df = df[df["date"] >= start_date]
    if end_date is not None:
        df = df[df["date"] <= end_date]
    return df[["indicator_id", "date", "value"]].copy()


def build_release_calendar(
    df_silver_macro: pd.DataFrame,
    df_silver_econ_events: pd.DataFrame,
    df_silver_fred_vintages: pd.DataFrame,
) -> pd.DataFrame:
    """Silver Calendar → Gold df_calendar via 3-tier fallback cascade.

    Contract: gold_design_contract.md §8b / calendar_design_contract.md §8a-§8c

    Cascade priority:
      1) econ_events: release_date = release_date_utc
      2) fred_vintages (is_first_vintage=True): release_date = vintage_date
      3) assumed_t+1: release_date = observation_date + 1 day

    Returns DataFrame with columns:
      indicator_id, observation_date, release_date, release_source, is_assumption_based
    """
    out_cols = [
        "indicator_id", "observation_date", "release_date",
        "release_source", "is_assumption_based",
    ]

    # All (indicator_id, observation_date) candidates from Silver macro
    candidates = (
        df_silver_macro[["indicator_id", "date"]]
        .drop_duplicates()
        .rename(columns={"date": "observation_date"})
        .copy()
    )
    if candidates.empty:
        return pd.DataFrame(columns=out_cols)

    # Ensure date types
    candidates["observation_date"] = pd.to_datetime(
        candidates["observation_date"]
    ).dt.date

    # ── Tier 1: econ_events ──
    tier1 = pd.DataFrame(columns=out_cols)
    if not df_silver_econ_events.empty:
        econ = df_silver_econ_events[
            ["indicator_id", "observation_date", "release_date_utc"]
        ].drop_duplicates(subset=["indicator_id", "observation_date"], keep="first")
        econ["observation_date"] = pd.to_datetime(econ["observation_date"]).dt.date
        econ["release_date_utc"] = pd.to_datetime(econ["release_date_utc"]).dt.date

        merged_t1 = candidates.merge(
            econ, on=["indicator_id", "observation_date"], how="inner",
        )
        if not merged_t1.empty:
            tier1 = pd.DataFrame({
                "indicator_id": merged_t1["indicator_id"],
                "observation_date": merged_t1["observation_date"],
                "release_date": merged_t1["release_date_utc"],
                "release_source": "econ_events",
                "is_assumption_based": False,
            })

    # Remaining candidates after Tier 1
    if not tier1.empty:
        matched_t1 = set(
            zip(tier1["indicator_id"], tier1["observation_date"])
        )
        remaining = candidates[
            ~candidates.apply(
                lambda r: (r["indicator_id"], r["observation_date"]) in matched_t1,
                axis=1,
            )
        ]
    else:
        remaining = candidates

    # ── Tier 2: fred_vintages (is_first_vintage=True) ──
    tier2 = pd.DataFrame(columns=out_cols)
    if not remaining.empty and not df_silver_fred_vintages.empty:
        vintages = df_silver_fred_vintages[
            df_silver_fred_vintages["is_first_vintage"] == True  # noqa: E712
        ][["indicator_id", "observation_date", "vintage_date"]].drop_duplicates(
            subset=["indicator_id", "observation_date"], keep="first",
        )
        vintages["observation_date"] = pd.to_datetime(
            vintages["observation_date"]
        ).dt.date
        vintages["vintage_date"] = pd.to_datetime(
            vintages["vintage_date"]
        ).dt.date

        merged_t2 = remaining.merge(
            vintages, on=["indicator_id", "observation_date"], how="inner",
        )
        if not merged_t2.empty:
            tier2 = pd.DataFrame({
                "indicator_id": merged_t2["indicator_id"],
                "observation_date": merged_t2["observation_date"],
                "release_date": merged_t2["vintage_date"],
                "release_source": "fred_vintages",
                "is_assumption_based": False,
            })

    # Remaining candidates after Tier 2
    if not tier2.empty:
        matched_t2 = set(
            zip(tier2["indicator_id"], tier2["observation_date"])
        )
        remaining2 = remaining[
            ~remaining.apply(
                lambda r: (r["indicator_id"], r["observation_date"]) in matched_t2,
                axis=1,
            )
        ]
    else:
        remaining2 = remaining

    # ── Tier 3: assumed_t+1 ──
    tier3 = pd.DataFrame(columns=out_cols)
    if not remaining2.empty:
        tier3 = pd.DataFrame({
            "indicator_id": remaining2["indicator_id"].values,
            "observation_date": remaining2["observation_date"].values,
            "release_date": [
                d + timedelta(days=1) for d in remaining2["observation_date"]
            ],
            "release_source": "assumed_t_plus_1",
            "is_assumption_based": True,
        })

    result = pd.concat([tier1, tier2, tier3], ignore_index=True)
    return result[out_cols].reset_index(drop=True)


def write_gold_macro_features(
    df: pd.DataFrame,
    gold_root: Path,
    run_id: str,
) -> None:
    """Gold macro features를 parquet로 저장 (멱등, partition overwrite).

    경로: gold_root/year=YYYY/month=MM/gold_macro_features_YYYYMM.parquet
    """
    if df.empty:
        logger.warning("[GoldMacro] Nothing to write.")
        return

    df = df.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"])

    tmp_root = gold_root / f"_tmp_run={run_id}"

    years_months = sorted(
        set(zip(df["trade_date"].dt.year, df["trade_date"].dt.month))
    )
    for year, month in years_months:
        part = df[
            (df["trade_date"].dt.year == year)
            & (df["trade_date"].dt.month == month)
        ]
        if part.empty:
            continue

        tmp_dir = tmp_root / f"year={year:04d}" / f"month={month:02d}"
        final_dir = gold_root / f"year={year:04d}" / f"month={month:02d}"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        final_dir.mkdir(parents=True, exist_ok=True)

        tmp_file = tmp_dir / f"gold_macro_features_{year:04d}{month:02d}.parquet"
        final_file = final_dir / f"gold_macro_features_{year:04d}{month:02d}.parquet"

        part.to_parquet(tmp_file, index=False)

        if final_file.exists():
            final_file.unlink()
        tmp_file.replace(final_file)

        logger.info("[GoldMacro] Saved: %s", final_file)

    if tmp_root.exists():
        shutil.rmtree(tmp_root)
        logger.info("[GoldMacro] Cleaned tmp: %s", tmp_root)
