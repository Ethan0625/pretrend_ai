from __future__ import annotations

from datetime import date

import pandas as pd

from pretrend.pipeline.strategy_engine.next_step.history_io import (
    load_next_step_history,
    save_next_step_history_full,
    save_next_step_history_incremental,
)


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": date(2026, 2, 20),
                "bias_1m": "RISK_ON_BIAS",
                "transition_hazard_10d": 0.25,
                "source_run_id": "run_a",
            },
            {
                "trade_date": date(2026, 2, 21),
                "bias_1m": "NEUTRAL_BIAS",
                "transition_hazard_10d": 0.35,
                "source_run_id": "run_a",
            },
        ]
    )


def test_save_incremental_and_load(tmp_path):
    strategy_root = tmp_path / "strategy"
    saved = save_next_step_history_incremental(
        _sample_df(),
        strategy_root,
        decision_date_ref=date(2026, 2, 23),
        run_id="r1",
    )
    assert saved == 2

    out = load_next_step_history(strategy_root)
    assert len(out) == 2
    assert {"trade_date", "decision_date_ref"}.issubset(out.columns)


def test_incremental_idempotent_by_key(tmp_path):
    strategy_root = tmp_path / "strategy"
    df = _sample_df()
    save_next_step_history_incremental(df, strategy_root, decision_date_ref=date(2026, 2, 23), run_id="r1")
    save_next_step_history_incremental(df, strategy_root, decision_date_ref=date(2026, 2, 23), run_id="r1")
    out = load_next_step_history(strategy_root)
    # key=(trade_date, decision_date_ref) dedupe
    assert len(out) == 2


def test_full_refresh_replaces_previous(tmp_path):
    strategy_root = tmp_path / "strategy"
    save_next_step_history_incremental(
        _sample_df(),
        strategy_root,
        decision_date_ref=date(2026, 2, 23),
        run_id="r1",
    )

    new_df = pd.DataFrame(
        [
            {
                "trade_date": date(2026, 3, 1),
                "bias_1m": "RISK_OFF_BIAS",
                "source_run_id": "run_b",
            }
        ]
    )
    save_next_step_history_full(
        new_df,
        strategy_root,
        decision_date_ref=date(2026, 3, 2),
        run_id="r2",
    )
    out = load_next_step_history(strategy_root)
    assert len(out) == 1
    assert out.iloc[0]["trade_date"] == date(2026, 3, 1)
