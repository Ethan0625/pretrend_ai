from __future__ import annotations

from datetime import date

import pandas as pd

from pretrend.observability.regime.transition.history_io import save_next_step_history_incremental
from pretrend.observability.regime.transition.io import load_next_step_for_runtime
from pretrend.pipeline.strategy_engine.io import write_snapshot_atomic


def test_load_next_step_for_runtime_merges_snapshot_and_history(tmp_path):
    strategy_root = tmp_path / "strategy"
    # snapshot (decision_date partition)
    snap = pd.DataFrame(
        [
            {"trade_date": date(2026, 2, 21), "bias_20d": "RISK_ON_BIAS", "source_run_id": "snap"},
        ]
    )
    write_snapshot_atomic(
        snap,
        strategy_root,
        "next_step_signal",
        decision_date=date(2026, 2, 23),
        run_id="r1",
    )

    # history (older)
    hist = pd.DataFrame(
        [
            {"trade_date": date(2026, 2, 20), "bias_20d": "NEUTRAL_BIAS", "source_run_id": "hist"},
        ]
    )
    save_next_step_history_incremental(
        hist,
        strategy_root,
        decision_date_ref=date(2026, 2, 22),
        run_id="r2",
    )

    out = load_next_step_for_runtime(strategy_root)
    assert len(out) == 2
    assert set(out["trade_date"]) == {date(2026, 2, 20), date(2026, 2, 21)}
