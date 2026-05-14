from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy.engine import Engine

from pretrend.observability.regime.rotation.engine import build_group_transition_signal
from pretrend.observability.regime.rotation.history_io import (
    save_group_transition_history_incremental,
)
from pretrend.observability.regime.rotation.io import load_universe_for_group_transition
from pretrend.observability.similarity.runtime_source import (
    build_market_state_similarity_features_from_runtime,
)
from pretrend.pipeline.backtest._utils import load_strategy_snapshot
from pretrend.pipeline.strategy_engine.io import write_snapshot_atomic
from pretrend.pipeline.strategy_engine.universe.engine import build_universe


DEFAULT_DATA_ROOT = Path("data")
GOLD_EOD_UNIVERSE_COLUMNS = ["symbol", "trade_date", "asset_group", "ret_20d"]


def load_policy_selection_history(strategy_root: Path | str) -> pd.DataFrame:
    df = load_strategy_snapshot(Path(strategy_root), "policy_selection")
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    out = _to_date(out, "trade_date")
    out = _to_date(out, "decision_date")
    out = out.dropna(subset=["trade_date"])
    sort_cols = [c for c in ["trade_date", "decision_date", "source_run_id"] if c in out.columns]
    return out.sort_values(sort_cols).drop_duplicates("trade_date", keep="last").reset_index(drop=True)


def load_gold_eod_for_universe(
    gold_eod_root: Path | str,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    root = Path(gold_eod_root)
    files = list(root.rglob("*.parquet"))
    if not files:
        return pd.DataFrame(columns=GOLD_EOD_UNIVERSE_COLUMNS)

    frames: list[pd.DataFrame] = []
    for file in files:
        chunk = pd.read_parquet(file)
        keep = [column for column in GOLD_EOD_UNIVERSE_COLUMNS if column in chunk.columns]
        if set(GOLD_EOD_UNIVERSE_COLUMNS).issubset(keep):
            frames.append(chunk[GOLD_EOD_UNIVERSE_COLUMNS])

    if not frames:
        return pd.DataFrame(columns=GOLD_EOD_UNIVERSE_COLUMNS)

    out = pd.concat(frames, ignore_index=True)
    out = _to_date(out, "trade_date")
    out = out.dropna(subset=["symbol", "trade_date", "ret_20d"])
    out = out[(out["trade_date"] >= start_date) & (out["trade_date"] <= end_date)]
    return out.reset_index(drop=True)


def build_missing_what_to_hold(
    policy_selection: pd.DataFrame,
    gold_eod: pd.DataFrame,
    *,
    start_date: date,
    end_date: date,
    existing_what_to_hold: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if policy_selection is None or policy_selection.empty:
        return _empty_what_to_hold()
    if gold_eod is None or gold_eod.empty:
        return _empty_what_to_hold()

    policy = policy_selection.copy()
    policy = _to_date(policy, "trade_date")
    policy = policy.dropna(subset=["trade_date"])
    policy = policy[(policy["trade_date"] >= start_date) & (policy["trade_date"] <= end_date)]

    existing_dates = _existing_decision_dates(existing_what_to_hold)
    if existing_dates:
        policy = policy[~policy["trade_date"].isin(existing_dates)]
    if policy.empty:
        return _empty_what_to_hold()

    eod = gold_eod.copy()
    eod = _to_date(eod, "trade_date")
    eod = eod[(eod["trade_date"] >= start_date) & (eod["trade_date"] <= end_date)]
    if eod.empty:
        return _empty_what_to_hold()

    out = build_universe(policy, eod)
    if out.empty:
        return _empty_what_to_hold()
    out = _to_date(out, "decision_date")
    return out.sort_values(["decision_date", "symbol"]).reset_index(drop=True)


def backfill_what_to_hold_for_similarity(
    start_date: date,
    end_date: date,
    *,
    engine: Engine | None = None,
    data_root: Path | str | None = None,
    strategy_root: Path | str | None = None,
    gold_eod_root: Path | str | None = None,
    run_id: str = "p26_3c_what_to_hold_backfill",
    write_snapshots: bool = True,
    update_group_transition: bool = True,
    update_features: bool = True,
) -> dict[str, Any]:
    data_root_path = Path(data_root) if data_root is not None else DEFAULT_DATA_ROOT
    strategy_path = (
        Path(strategy_root)
        if strategy_root is not None
        else data_root_path / "strategy"
    )
    gold_eod_path = (
        Path(gold_eod_root)
        if gold_eod_root is not None
        else data_root_path / "gold" / "eod" / "eod_features"
    )

    policy = load_policy_selection_history(strategy_path)
    existing = load_universe_for_group_transition(strategy_path)
    gold_eod = load_gold_eod_for_universe(gold_eod_path, start_date, end_date)
    generated = build_missing_what_to_hold(
        policy,
        gold_eod,
        start_date=start_date,
        end_date=end_date,
        existing_what_to_hold=existing,
    )

    written_partitions = 0
    if write_snapshots and not generated.empty:
        for decision_date, chunk in generated.groupby("decision_date", sort=True):
            write_snapshot_atomic(
                chunk.reset_index(drop=True),
                strategy_path,
                "what_to_hold",
                decision_date,
                run_id,
            )
            written_partitions += 1

    group_transition_rows = 0
    if update_group_transition:
        universe = load_universe_for_group_transition(strategy_path)
        if not universe.empty:
            group_transition = build_group_transition_signal(universe, run_id=run_id)
            group_transition_rows = len(group_transition)
            if write_snapshots and not group_transition.empty:
                write_snapshot_atomic(
                    group_transition,
                    strategy_path,
                    "group_transition_signal",
                    end_date,
                    run_id,
                )
                save_group_transition_history_incremental(
                    group_transition,
                    strategy_path,
                    decision_date_ref=end_date,
                    run_id=run_id,
                )

    feature_result: dict[str, Any] | None = None
    if update_features:
        feature_result = build_market_state_similarity_features_from_runtime(
            start_date,
            end_date,
            engine=engine,
            strategy_root=strategy_path,
        )

    return {
        "generated_rows": len(generated),
        "generated_dates": int(generated["decision_date"].nunique()) if not generated.empty else 0,
        "written_partitions": written_partitions,
        "group_transition_rows": group_transition_rows,
        "feature_result": feature_result,
    }


def _existing_decision_dates(existing_what_to_hold: pd.DataFrame | None) -> set[date]:
    if existing_what_to_hold is None or existing_what_to_hold.empty:
        return set()
    existing = existing_what_to_hold.copy()
    for column in ["decision_date", "rebalance_date", "trade_date"]:
        if column in existing.columns:
            existing = _to_date(existing, column)
            return set(existing[column].dropna().tolist())
    return set()


def _to_date(df: pd.DataFrame, column: str) -> pd.DataFrame:
    if column in df.columns:
        df[column] = pd.to_datetime(df[column], errors="coerce").dt.date
    return df


def _empty_what_to_hold() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "decision_date",
            "symbol",
            "asset_group",
            "relative_strength",
            "is_candidate",
        ]
    )
