from __future__ import annotations

from pathlib import Path

from pretrend.pipeline.utils.result_registry import append_registry_entry, query_registry


def _entry(**kwargs):
    base = {
        "pipeline": "backtest",
        "artifact_path": "result/backtest/v2/a.parquet",
        "preset": "v2",
        "start_date": "2006-01-03",
        "end_date": "2024-06-03",
        "decision_date_ref": "2026-02-23",
        "code_version": "abc",
        "data_version": "d1",
        "metrics_hash": "h1",
        "created_at": "2026-02-25T10:00:00",
    }
    base.update(kwargs)
    return base


def test_append_and_query_registry(tmp_path):
    root = tmp_path / "registry"
    append_registry_entry(root, _entry())
    df = query_registry(root, pipeline="backtest")
    assert len(df) == 1
    assert df.iloc[0]["preset"] == "v2"


def test_duplicate_key_keeps_latest(tmp_path):
    root = tmp_path / "registry"
    append_registry_entry(root, _entry(metrics_hash="h1", created_at="2026-02-25T10:00:00"))
    append_registry_entry(root, _entry(metrics_hash="h2", created_at="2026-02-25T10:10:00"))
    df = query_registry(root, pipeline="backtest")
    assert len(df) == 1
    assert df.iloc[0]["metrics_hash"] == "h2"
