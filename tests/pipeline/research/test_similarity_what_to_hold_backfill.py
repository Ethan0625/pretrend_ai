from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from pretrend.pipeline.research.similarity_what_to_hold_backfill import (
    backfill_what_to_hold_for_similarity,
    build_missing_what_to_hold,
    load_policy_selection_history,
)


def test_build_missing_what_to_hold_reuses_universe_logic() -> None:
    policy = pd.DataFrame(
        [
            {
                "trade_date": date(2006, 1, 3),
                "decision_date": date(2026, 1, 1),
                "long_phase": "LATE_CYCLE",
                "mid_regime": "RISK_ON",
                "run_universe": True,
            }
        ]
    )
    gold_eod = pd.DataFrame(
        [
            {
                "trade_date": date(2006, 1, 3),
                "symbol": "SPY",
                "asset_group": "INDEX",
                "ret_20d": 0.02,
            },
            {
                "trade_date": date(2006, 1, 3),
                "symbol": "XLK",
                "asset_group": "SECTOR",
                "ret_20d": 0.05,
            },
            {
                "trade_date": date(2006, 1, 3),
                "symbol": "XLV",
                "asset_group": "SECTOR",
                "ret_20d": -0.01,
            },
        ]
    )

    out = build_missing_what_to_hold(
        policy,
        gold_eod,
        start_date=date(2006, 1, 3),
        end_date=date(2006, 1, 3),
    )

    assert set(out["symbol"]) == {"SPY", "XLK", "XLV"}
    assert out["decision_date"].nunique() == 1
    assert out.loc[out["symbol"] == "SPY", "relative_strength"].iloc[0] == 0.0
    assert out.loc[out["symbol"] == "XLK", "relative_strength"].iloc[0] > 0


def test_load_policy_selection_history_keeps_latest_trade_date(tmp_path: Path) -> None:
    root = tmp_path / "strategy"
    _write_stage(
        root,
        "policy_selection",
        pd.DataFrame(
            [
                {
                    "trade_date": date(2006, 1, 3),
                    "long_phase": "RECOVERY",
                    "mid_regime": "RISK_OFF",
                    "run_universe": True,
                }
            ]
        ),
        date(2026, 1, 1),
    )
    _write_stage(
        root,
        "policy_selection",
        pd.DataFrame(
            [
                {
                    "trade_date": date(2006, 1, 3),
                    "long_phase": "LATE_CYCLE",
                    "mid_regime": "RISK_ON",
                    "run_universe": True,
                }
            ]
        ),
        date(2026, 1, 2),
    )

    out = load_policy_selection_history(root)

    assert len(out) == 1
    assert out.iloc[0]["long_phase"] == "LATE_CYCLE"
    assert out.iloc[0]["decision_date"] == date(2026, 1, 2)


def test_backfill_what_to_hold_writes_idempotent_snapshots(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    strategy_root = data_root / "strategy"
    gold_eod_root = data_root / "gold" / "eod" / "eod_features"
    _write_stage(
        strategy_root,
        "policy_selection",
        pd.DataFrame(
            [
                {
                    "trade_date": date(2006, 1, 3),
                    "long_phase": "LATE_CYCLE",
                    "mid_regime": "RISK_ON",
                    "run_universe": True,
                },
                {
                    "trade_date": date(2006, 1, 4),
                    "long_phase": "LATE_CYCLE",
                    "mid_regime": "RISK_ON",
                    "run_universe": True,
                },
            ]
        ),
        date(2026, 1, 1),
    )
    _write_gold_eod(gold_eod_root)

    first = backfill_what_to_hold_for_similarity(
        date(2006, 1, 3),
        date(2006, 1, 4),
        data_root=data_root,
        update_features=False,
    )
    second = backfill_what_to_hold_for_similarity(
        date(2006, 1, 3),
        date(2006, 1, 4),
        data_root=data_root,
        update_features=False,
    )

    files = list((strategy_root / "what_to_hold").rglob("*.parquet"))
    group_files = list((strategy_root / "group_transition_signal").rglob("*.parquet"))
    history_files = list((strategy_root / "group_transition_history").rglob("*.parquet"))

    assert first["generated_dates"] == 2
    assert first["written_partitions"] == 2
    assert second["generated_dates"] == 0
    assert second["written_partitions"] == 0
    assert len(files) == 2
    assert len(group_files) == 1
    assert len(history_files) == 1


def _write_stage(root: Path, stage: str, df: pd.DataFrame, decision_date: date) -> None:
    out_dir = root / stage / f"decision_date={decision_date.isoformat()}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{stage}_{decision_date.strftime('%Y%m%d')}.parquet"
    df.to_parquet(out, index=False)


def _write_gold_eod(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    for trade_date in [date(2006, 1, 3), date(2006, 1, 4)]:
        rows.extend(
            [
                {
                    "trade_date": trade_date,
                    "symbol": "SPY",
                    "asset_group": "INDEX",
                    "ret_20d": 0.02,
                },
                {
                    "trade_date": trade_date,
                    "symbol": "XLK",
                    "asset_group": "SECTOR",
                    "ret_20d": 0.05,
                },
                {
                    "trade_date": trade_date,
                    "symbol": "XLV",
                    "asset_group": "SECTOR",
                    "ret_20d": -0.01,
                },
            ]
        )
    pd.DataFrame(rows).to_parquet(root / "eod_features.parquet", index=False)
