from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pretrend.observability.regime.axis import build_axis_features
from pretrend.observability.regime.horizon.builder import build_axis_horizon_state
from pretrend.observability.regime.position.engine import build_market_position
from pretrend.observability.regime.transition.engine import build_next_step_signal


DEFAULT_LOOKBACK_DAYS = 730
RUN_ID = "observability_regime_feature_builder_v1"

MARKET_STATE_COLUMNS = [
    "trade_date",
    "long_phase",
    "mid_regime",
    "short_signal",
    "long_phase_confidence",
    "mid_regime_confidence",
    "short_signal_confidence",
    "run_universe",
    "risk_gate",
    "state_age_days",
    "sojourn_prob_5d",
    "sojourn_prob_10d",
    "sojourn_prob_20d",
    "sojourn_prob_60d",
    "sojourn_prob_120d",
    "transition_hazard_5d",
    "transition_hazard_10d",
    "transition_hazard_20d",
    "transition_hazard_60d",
    "transition_hazard_120d",
]

TRANSITION_COLUMNS = [
    "state_age_days",
    "sojourn_prob_5d",
    "sojourn_prob_10d",
    "sojourn_prob_20d",
    "sojourn_prob_60d",
    "sojourn_prob_120d",
    "transition_hazard_5d",
    "transition_hazard_10d",
    "transition_hazard_20d",
    "transition_hazard_60d",
    "transition_hazard_120d",
]

ROTATION_COLUMNS = ["trade_date", "asset_group", "asset_name", "group_state_now"]

GOLD_EOD_COLUMNS = [
    "symbol",
    "trade_date",
    "adj_close",
    "volume",
    "ret_1d",
    "ret_5d",
    "ret_20d",
    "vol_20d",
    "vol_60d",
    "atr_14",
    "rsi_14",
    "intraday_range",
    "volume_zscore_20d",
    "asset_group",
    "asset_name",
]

GOLD_MACRO_COLUMNS = [
    "indicator_id",
    "trade_date",
    "selected_value",
    "selected_release_date",
    "regime",
    "delta_1m",
    "delta_3m",
    "delta_6m",
    "zscore_12m",
    "release_source",
    "direction",
]


def build_market_state_df_from_gold(
    engine: Engine,
    query_start: date,
    query_end: date,
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> pd.DataFrame:
    """Build market-state similarity source rows from Gold serving tables."""
    read_start = _read_start(query_start, lookback_days)
    eod = read_gold_eod_features(engine, read_start, query_end)
    macro = read_gold_macro_features(engine, read_start, query_end)
    if eod.empty and macro.empty:
        return pd.DataFrame(columns=MARKET_STATE_COLUMNS)

    bundle = build_axis_features(macro, eod)
    axis_horizon_state = build_axis_horizon_state(bundle, run_id=RUN_ID)
    market_position = build_market_position(axis_horizon_state, run_id=RUN_ID)
    next_step = build_next_step_signal(
        axis_horizon_state,
        market_position,
        run_id=RUN_ID,
    )

    return _build_market_state_source(
        axis_horizon_state,
        market_position,
        next_step,
        query_start=query_start,
        query_end=query_end,
    )


def build_rotation_df_from_gold(
    engine: Engine,
    query_start: date,
    query_end: date,
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> pd.DataFrame:
    """Build asset rotation source rows from Gold EOD asset metadata."""
    read_start = _read_start(query_start, lookback_days)
    eod = read_gold_eod_features(engine, read_start, query_end)
    if eod.empty:
        return pd.DataFrame(columns=ROTATION_COLUMNS)

    required = {"symbol", "trade_date", "ret_20d", "asset_group", "asset_name"}
    if not required.issubset(eod.columns):
        return pd.DataFrame(columns=ROTATION_COLUMNS)

    out = eod[["symbol", "trade_date", "ret_20d", "asset_group", "asset_name"]].copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"], errors="coerce").dt.date
    out["symbol"] = out["symbol"].astype(str).str.upper()
    out["asset_group"] = out["asset_group"].astype("string").str.upper()
    out["asset_name"] = out["asset_name"].astype("string").str.upper()
    out["ret_20d"] = pd.to_numeric(out["ret_20d"], errors="coerce")
    out = out.dropna(subset=["trade_date", "symbol", "asset_group", "asset_name", "ret_20d"])
    if out.empty:
        return pd.DataFrame(columns=ROTATION_COLUMNS)

    spy = (
        out[out["symbol"] == "SPY"][["trade_date", "ret_20d"]]
        .drop_duplicates("trade_date", keep="last")
        .rename(columns={"ret_20d": "spy_ret_20d"})
    )
    out = out.merge(spy, on="trade_date", how="left")
    out["relative_strength"] = out["ret_20d"] - out["spy_ret_20d"]
    out = _filter_date_range(out, query_start, query_end)
    out = out.dropna(subset=["relative_strength"])
    if out.empty:
        return pd.DataFrame(columns=ROTATION_COLUMNS)

    grouped = (
        out.groupby(["trade_date", "asset_group", "asset_name"], as_index=False)[
            "relative_strength"
        ]
        .mean()
        .sort_values(["trade_date", "asset_group", "asset_name"])
    )
    grouped["group_state_now"] = grouped["relative_strength"].map(_rotation_state)
    return grouped[ROTATION_COLUMNS].reset_index(drop=True)


def read_gold_eod_features(engine: Engine, start: date, end: date) -> pd.DataFrame:
    columns = ", ".join(GOLD_EOD_COLUMNS)
    df = _read_sql(
        engine,
        f"""
        SELECT {columns}
        FROM gold_eod_features
        WHERE trade_date BETWEEN :start_date AND :end_date
        ORDER BY trade_date, symbol
        """,
        {"start_date": start, "end_date": end},
    )
    return _normalize_dates(df, ["trade_date"])


def read_gold_macro_features(engine: Engine, start: date, end: date) -> pd.DataFrame:
    columns = ", ".join(GOLD_MACRO_COLUMNS)
    df = _read_sql(
        engine,
        f"""
        SELECT {columns}
        FROM gold_macro_features
        WHERE trade_date BETWEEN :start_date AND :end_date
        ORDER BY trade_date, indicator_id
        """,
        {"start_date": start, "end_date": end},
    )
    return _normalize_dates(df, ["trade_date", "selected_release_date"])


def _read_sql(engine: Engine, sql: str, params: dict[str, Any]) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql_query(text(sql), conn, params=params)


def _read_start(query_start: date, lookback_days: int) -> date:
    return query_start - timedelta(days=max(0, int(lookback_days)))


def _normalize_dates(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = df.copy()
    for column in columns:
        if column in out.columns:
            out[column] = pd.to_datetime(out[column], errors="coerce").dt.date
    return out


def _build_market_state_source(
    axis: pd.DataFrame,
    position: pd.DataFrame,
    next_step: pd.DataFrame,
    *,
    query_start: date,
    query_end: date,
) -> pd.DataFrame:
    state = _normalize_axis_state(axis)
    pos = _normalize_position(position)
    transitions = _normalize_next_step(next_step)

    frames = [df for df in [state, pos, transitions] if not df.empty]
    if not frames:
        return pd.DataFrame(columns=MARKET_STATE_COLUMNS)

    out = frames[0]
    for frame in frames[1:]:
        out = out.merge(frame, on="trade_date", how="outer", suffixes=("", "_pos"))
        for column in ["long_phase", "mid_regime", "short_signal"]:
            alt = f"{column}_pos"
            if alt in out.columns:
                out[column] = out[column].combine_first(out[alt])
                out = out.drop(columns=[alt])

    out = _filter_date_range(out, query_start, query_end)
    for column in MARKET_STATE_COLUMNS:
        if column not in out.columns:
            out[column] = None
    return out[MARKET_STATE_COLUMNS].sort_values("trade_date").reset_index(drop=True)


def _normalize_axis_state(axis: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "trade_date",
        "long_phase",
        "mid_regime",
        "short_signal",
        "long_phase_confidence",
        "mid_regime_confidence",
        "short_signal_confidence",
    ]
    if axis is None or axis.empty or "trade_date" not in axis.columns:
        return pd.DataFrame(columns=columns)
    out = _latest_per_trade_date(axis)
    for column in columns:
        if column not in out.columns:
            out[column] = None
    return out[columns]


def _normalize_position(position: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "trade_date",
        "long_phase",
        "mid_regime",
        "short_signal",
        "run_universe",
        "risk_gate",
    ]
    if position is None or position.empty or "trade_date" not in position.columns:
        return pd.DataFrame(columns=columns)
    out = _latest_per_trade_date(position)
    for column in columns:
        if column not in out.columns:
            out[column] = None
    return out[columns]


def _normalize_next_step(next_step: pd.DataFrame) -> pd.DataFrame:
    columns = ["trade_date", *TRANSITION_COLUMNS]
    if next_step is None or next_step.empty or "trade_date" not in next_step.columns:
        return pd.DataFrame(columns=columns)
    out = _latest_per_trade_date(next_step)
    for column in columns:
        if column not in out.columns:
            out[column] = None
    return out[columns]


def _latest_per_trade_date(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"], errors="coerce").dt.date
    out = out.dropna(subset=["trade_date"])
    sort_cols = ["trade_date"]
    for column in ["decision_date_ref", "decision_date", "source_run_id"]:
        if column in out.columns:
            if column in {"decision_date_ref", "decision_date"}:
                out[column] = pd.to_datetime(out[column], errors="coerce").dt.date
            sort_cols.append(column)
    return out.sort_values(sort_cols).drop_duplicates("trade_date", keep="last")


def _filter_date_range(df: pd.DataFrame, query_start: date, query_end: date) -> pd.DataFrame:
    if df.empty or "trade_date" not in df.columns:
        return df
    out = df.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"], errors="coerce").dt.date
    out = out.dropna(subset=["trade_date"])
    return out[(out["trade_date"] >= query_start) & (out["trade_date"] <= query_end)]


def _rotation_state(value: float) -> str | None:
    if pd.isna(value):
        return None
    if float(value) > 0:
        return "STRONG"
    if float(value) < 0:
        return "WEAK"
    return "NEUTRAL"
