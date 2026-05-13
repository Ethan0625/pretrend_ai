from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from pretrend.pipeline.paper.io import load_decision_partition, save_decision_partition


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


def test_save_decision_partition_with_mode_path_structure(tmp_path: Path) -> None:
    df = pd.DataFrame([{"a": 1}])

    out = save_decision_partition(
        df,
        tmp_path,
        date(2026, 2, 27),
        "ledger",
        execution_mode="SIM",
    )

    assert out is not None
    assert out.parent.name == "decision_date=2026-02-27"
    assert out.parent.parent.name == "execution_mode=SIM"
    assert out == tmp_path / "execution_mode=SIM" / "decision_date=2026-02-27" / "ledger_20260227.parquet"


def test_load_decision_partition_mode_first_then_legacy(tmp_path: Path) -> None:
    legacy_df = pd.DataFrame([{"k": "legacy"}])
    mode_df = pd.DataFrame([{"k": "mode"}])

    save_decision_partition(legacy_df, tmp_path, date(2026, 2, 27), "ledger")
    save_decision_partition(mode_df, tmp_path, date(2026, 2, 27), "ledger", execution_mode="SIM")

    loaded = load_decision_partition(tmp_path, date(2026, 2, 27), execution_mode="SIM")
    assert not loaded.empty
    assert loaded.iloc[0]["k"] == "mode"

    loaded_legacy = load_decision_partition(tmp_path, date(2026, 2, 27), execution_mode="MOCK")
    assert not loaded_legacy.empty
    assert loaded_legacy.iloc[0]["k"] == "legacy"
