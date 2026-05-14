from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pretrend.observability.similarity.columns import (
    REGIME_SIMILARITY_FEATURE_COLUMNS,
)
from pretrend.observability.similarity.producer import SIMILARITY_ASSET_NAMES


REGIME_VIEW_COLUMNS = list(REGIME_SIMILARITY_FEATURE_COLUMNS)

GOLD_EOD_NUMERIC_FEATURES = [
    "ret_5d",
    "ret_20d",
    "vol_20d",
    "vol_60d",
    "ma_ratio_5_20",
    "rsi_14",
    "volume_zscore_20d",
]

GOLD_MACRO_INDICATORS = [
    "CPI_US_ALL_ITEMS_SA",
    "CPI_US_CORE_SA",
    "US_UNEMPLOYMENT_RATE",
    "US_FED_FUNDS_RATE",
    "US_TREASURY_10Y_YIELD",
]

GOLD_MACRO_NUMERIC_FEATURES = [
    "delta_1m",
    "delta_3m",
    "delta_6m",
    "zscore_12m",
]

EXCLUDED_GOLD_ASSET_NAMES = {"CBOE_VOLATILITY_INDEX", "CBOE_SKEW_INDEX"}
EXCLUDED_GOLD_ASSET_GROUPS = {"VOLATILITY_INDEX"}

GOLD_EOD_COLUMNS = [
    f"eod_{asset_name.lower()}_{feature}"
    for asset_name in SIMILARITY_ASSET_NAMES
    for feature in GOLD_EOD_NUMERIC_FEATURES
]

GOLD_MACRO_COLUMNS = [
    f"macro_{indicator.lower()}_{feature}"
    for indicator in GOLD_MACRO_INDICATORS
    for feature in GOLD_MACRO_NUMERIC_FEATURES
] + [
    f"macro_{indicator.lower()}_{feature}"
    for indicator in GOLD_MACRO_INDICATORS
    for feature in ["regime_code", "direction_code", "is_assumption_based"]
]

GOLD_VIEW_COLUMNS = GOLD_EOD_COLUMNS + GOLD_MACRO_COLUMNS

MACRO_REGIME_CODE = {
    "easing": 1,
    "neutral": 0,
    "tightening": -1,
}

MACRO_DIRECTION_CODE = {
    "up": 1,
    "flat": 0,
    "down": -1,
}


def normalize_zscore(
    df: pd.DataFrame,
    ref_mean: pd.Series,
    ref_std: pd.Series,
) -> pd.DataFrame:
    mean = pd.to_numeric(ref_mean.reindex(df.columns), errors="coerce").fillna(0.0)
    std = pd.to_numeric(ref_std.reindex(df.columns), errors="coerce").fillna(1.0)
    std = std.mask(std == 0, 1.0)
    numeric = df.apply(pd.to_numeric, errors="coerce")
    return numeric.fillna(mean).sub(mean).div(std).fillna(0.0)


def build_regime_view_features(engine: Engine, trade_dates: list[date]) -> pd.DataFrame:
    if not trade_dates:
        return pd.DataFrame(columns=REGIME_VIEW_COLUMNS)

    columns_sql = ", ".join(REGIME_VIEW_COLUMNS)
    sql = f"""
        SELECT trade_date, {columns_sql}
        FROM gold_market_state_similarity_feature
        ORDER BY trade_date
        """
    all_rows = _read_sql_frame(engine, sql)
    if all_rows.empty:
        return pd.DataFrame(columns=REGIME_VIEW_COLUMNS)

    all_rows["trade_date"] = pd.to_datetime(all_rows["trade_date"]).dt.date
    all_rows = all_rows.set_index("trade_date")
    feature_rows = all_rows[REGIME_VIEW_COLUMNS].apply(pd.to_numeric, errors="coerce")
    normalized = normalize_zscore(
        feature_rows,
        feature_rows.mean(skipna=True),
        feature_rows.std(skipna=True, ddof=0),
    )
    requested = [trade_date for trade_date in trade_dates if trade_date in normalized.index]
    return normalized.loc[requested, REGIME_VIEW_COLUMNS]


def build_gold_view_features(engine: Engine, trade_dates: list[date]) -> pd.DataFrame:
    if not trade_dates:
        return pd.DataFrame(columns=GOLD_VIEW_COLUMNS)

    eod = _read_sql_frame(
        engine,
        """
            SELECT trade_date, asset_group, asset_name,
                   ret_5d, ret_20d, vol_20d, vol_60d, ma_ratio_5_20,
                   rsi_14, volume_zscore_20d
            FROM gold_eod_features
            ORDER BY trade_date, asset_name
            """,
    )
    macro = _read_sql_frame(
        engine,
        """
            SELECT trade_date, indicator_id,
                   delta_1m, delta_3m, delta_6m, zscore_12m,
                   regime, direction, is_assumption_based
            FROM gold_macro_features
            ORDER BY trade_date, indicator_id
            """,
    )

    frame = _build_gold_raw_frame(eod, macro)
    if frame.empty:
        return pd.DataFrame(columns=GOLD_VIEW_COLUMNS)

    normalized = normalize_zscore(
        frame[GOLD_VIEW_COLUMNS],
        frame[GOLD_VIEW_COLUMNS].mean(skipna=True),
        frame[GOLD_VIEW_COLUMNS].std(skipna=True, ddof=0),
    )
    requested = [trade_date for trade_date in trade_dates if trade_date in normalized.index]
    return normalized.loc[requested, GOLD_VIEW_COLUMNS]


def _build_gold_raw_frame(eod: pd.DataFrame, macro: pd.DataFrame) -> pd.DataFrame:
    dates = _collect_gold_dates(eod, macro)
    if not dates:
        return pd.DataFrame(columns=GOLD_VIEW_COLUMNS)

    frame = pd.DataFrame(index=pd.Index(dates, name="trade_date"), columns=GOLD_VIEW_COLUMNS)
    if not eod.empty:
        _assign_eod_features(frame, eod)
    if not macro.empty:
        _assign_macro_features(frame, macro)
    return frame.sort_index()


def _read_sql_frame(engine: Engine, sql: str) -> pd.DataFrame:
    with engine.connect() as conn:
        result = conn.execute(text(sql))
        return pd.DataFrame(result.fetchall(), columns=result.keys())


def _collect_gold_dates(eod: pd.DataFrame, macro: pd.DataFrame) -> list[date]:
    values: set[date] = set()
    for source in [eod, macro]:
        if source.empty or "trade_date" not in source.columns:
            continue
        values.update(pd.to_datetime(source["trade_date"]).dt.date)
    return sorted(values)


def _assign_eod_features(frame: pd.DataFrame, eod: pd.DataFrame) -> None:
    out = eod.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"]).dt.date
    out["asset_name"] = out["asset_name"].astype(str).str.upper()
    out["asset_group"] = out["asset_group"].astype(str).str.upper()
    out = out[~out["asset_group"].isin(EXCLUDED_GOLD_ASSET_GROUPS)]
    out = out[~out["asset_name"].isin(EXCLUDED_GOLD_ASSET_NAMES)]
    out = out[out["asset_name"].isin(SIMILARITY_ASSET_NAMES)]
    if out.empty:
        return

    grouped = out.groupby(["trade_date", "asset_name"], as_index=False)[
        GOLD_EOD_NUMERIC_FEATURES
    ].mean()
    for row in grouped.to_dict(orient="records"):
        for feature in GOLD_EOD_NUMERIC_FEATURES:
            column = f"eod_{row['asset_name'].lower()}_{feature}"
            frame.at[row["trade_date"], column] = row[feature]


def _assign_macro_features(frame: pd.DataFrame, macro: pd.DataFrame) -> None:
    out = macro.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"]).dt.date
    out["indicator_id"] = out["indicator_id"].astype(str).str.upper()
    out = out[out["indicator_id"].isin(GOLD_MACRO_INDICATORS)]
    if out.empty:
        return

    out = out.sort_values(["trade_date", "indicator_id"]).drop_duplicates(
        ["trade_date", "indicator_id"],
        keep="last",
    )
    for row in out.to_dict(orient="records"):
        indicator = row["indicator_id"].lower()
        for feature in GOLD_MACRO_NUMERIC_FEATURES:
            frame.at[row["trade_date"], f"macro_{indicator}_{feature}"] = row[feature]
        frame.at[row["trade_date"], f"macro_{indicator}_regime_code"] = _map_text_code(
            row.get("regime"),
            MACRO_REGIME_CODE,
        )
        frame.at[row["trade_date"], f"macro_{indicator}_direction_code"] = _map_text_code(
            row.get("direction"),
            MACRO_DIRECTION_CODE,
        )
        frame.at[row["trade_date"], f"macro_{indicator}_is_assumption_based"] = _map_bool(
            row.get("is_assumption_based")
        )


def _map_text_code(value: Any, mapping: dict[str, int]) -> int | None:
    if value is None or pd.isna(value):
        return None
    return mapping.get(str(value).strip().lower())


def _map_bool(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    normalized = str(value).strip().lower()
    if normalized in {"true", "t", "1", "yes", "y"}:
        return 1
    if normalized in {"false", "f", "0", "no", "n"}:
        return 0
    return None
