from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from pretrend.pipeline.paper.io import save_decision_partition


def test_save_decision_partition_atomic(tmp_path: Path) -> None:
    df = pd.DataFrame([{"a": 1}, {"a": 2}])

    out = save_decision_partition(df, tmp_path, date(2026, 2, 27), "paper_daily")

    assert out is not None
    assert out.exists()
    assert out.name == "paper_daily_20260227.parquet"
    # tmp file must not remain after atomic move.
    assert not any(tmp_path.rglob("*_tmp_*.parquet"))


def test_save_decision_partition_empty_returns_none(tmp_path: Path) -> None:
    out = save_decision_partition(pd.DataFrame(), tmp_path, date(2026, 2, 27), "paper_daily")

    assert out is None
    assert not any(tmp_path.rglob("*.parquet"))


def test_save_decision_partition_path_structure(tmp_path: Path) -> None:
    df = pd.DataFrame([{"a": 1}])

    out = save_decision_partition(df, tmp_path, date(2026, 2, 27), "ledger")

    assert out is not None
    assert out.parent.name == "decision_date=2026-02-27"
    assert out == tmp_path / "decision_date=2026-02-27" / "ledger_20260227.parquet"
