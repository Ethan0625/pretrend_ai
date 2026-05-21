from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy.engine import Engine

from pretrend.observability.regime.rotation.io import load_universe_for_group_transition
from pretrend.observability.regime.transition.io import load_next_step_for_runtime
from pretrend.observability.similarity.producer import (
    build_market_state_similarity_features,
)
from pretrend.pipeline.config.eod_observability import LABEL_BY_SYMBOL_V1
from pretrend.pipeline.utils.snapshot import load_strategy_snapshot


DEFAULT_DATA_ROOT = Path("data")

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


def load_market_state_runtime_source(
    query_start: date,
    query_end: date,
    strategy_root: Path | str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    root = Path(strategy_root) if strategy_root is not None else _default_strategy_root()
    axis = _load_snapshot(root, "axis_horizon_state")
    position = _load_snapshot(root, "market_position")
    next_step = load_next_step_for_runtime(
        root,
        start_date=query_start,
        end_date=query_end,
    )
    universe = load_universe_for_group_transition(root)

    market_state = _build_market_state_source(
        axis,
        position,
        next_step,
        query_start=query_start,
        query_end=query_end,
    )
    rotation = _build_rotation_source(
        universe,
        query_start=query_start,
        query_end=query_end,
    )
    return market_state, rotation


def build_market_state_similarity_features_from_runtime(
    query_start: date,
    query_end: date,
    engine: Engine | None = None,
    strategy_root: Path | str | None = None,
) -> dict[str, Any]:
    market_state, rotation = load_market_state_runtime_source(
        query_start,
        query_end,
        strategy_root=strategy_root,
    )
    result = build_market_state_similarity_features(
        query_start,
        query_end,
        engine=engine,
        market_state_df=market_state,
        rotation_df=rotation,
    )
    return {
        **result,
        "source_market_state_rows": len(market_state),
        "source_rotation_rows": len(rotation),
    }


def _load_snapshot(strategy_root: Path, stage_name: str) -> pd.DataFrame:
    df = load_strategy_snapshot(strategy_root, stage_name)
    return df.copy() if df is not None and not df.empty else pd.DataFrame()


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
    out = axis.copy()
    out = _latest_per_trade_date(out)
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
    out = position.copy()
    out = _latest_per_trade_date(out)
    for column in columns:
        if column not in out.columns:
            out[column] = None
    return out[columns]


def _normalize_next_step(next_step: pd.DataFrame) -> pd.DataFrame:
    columns = ["trade_date", *TRANSITION_COLUMNS]
    if next_step is None or next_step.empty or "trade_date" not in next_step.columns:
        return pd.DataFrame(columns=columns)
    out = next_step.copy()
    out = _latest_per_trade_date(out)
    for column in columns:
        if column not in out.columns:
            out[column] = None
    return out[columns]


def _build_rotation_source(
    universe: pd.DataFrame,
    *,
    query_start: date,
    query_end: date,
) -> pd.DataFrame:
    columns = ["trade_date", "asset_group", "asset_name", "group_state_now"]
    if universe is None or universe.empty or "symbol" not in universe.columns:
        return pd.DataFrame(columns=columns)

    out = universe.copy()
    out["trade_date"] = _resolve_universe_trade_date(out)
    out = _filter_date_range(out, query_start, query_end)
    if out.empty:
        return pd.DataFrame(columns=columns)

    out["symbol"] = out["symbol"].astype(str).str.upper()
    out["asset_name"] = out["symbol"].map(
        lambda symbol: LABEL_BY_SYMBOL_V1.get(symbol, {}).get("asset_name")
    )
    out["asset_group"] = out["symbol"].map(
        lambda symbol: LABEL_BY_SYMBOL_V1.get(symbol, {}).get("asset_group")
    )
    out = out.dropna(subset=["trade_date", "asset_name", "asset_group"])
    if out.empty:
        return pd.DataFrame(columns=columns)

    out["relative_strength"] = pd.to_numeric(
        out.get("relative_strength"),
        errors="coerce",
    )
    grouped = (
        out.groupby(["trade_date", "asset_group", "asset_name"], as_index=False)[
            "relative_strength"
        ]
        .mean()
        .sort_values(["trade_date", "asset_group", "asset_name"])
    )
    grouped["group_state_now"] = grouped["relative_strength"].map(_rotation_state)
    return grouped[columns].reset_index(drop=True)


def _default_strategy_root() -> Path:
    data_root = os.getenv("PRETREND_DATA_ROOT") or os.getenv("PRETREND_DATA_DIR")
    return Path(data_root) / "strategy" if data_root else DEFAULT_DATA_ROOT / "strategy"


def _resolve_universe_trade_date(universe: pd.DataFrame) -> pd.Series:
    values = pd.Series(pd.NaT, index=universe.index)
    for column in ["rebalance_date", "decision_date", "trade_date"]:
        if column in universe.columns:
            normalized = pd.to_datetime(universe[column], errors="coerce")
            values = values.fillna(normalized)
    return values.dt.date


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
