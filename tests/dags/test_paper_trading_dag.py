from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_module():
    pytest.importorskip("pendulum")
    repo_root = Path(__file__).resolve().parents[2]
    mod_path = repo_root / "dags" / "paper_trading_dag.py"
    spec = importlib.util.spec_from_file_location("paper_trading_dag_mod", mod_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_paper_trading_dag_has_expected_tasks() -> None:
    paper_trading_dag = _load_module().paper_trading_dag
    task_ids = set(paper_trading_dag.task_ids)
    assert "build_paper_execution" in task_ids
    assert "build_paper_result_payload" in task_ids
    assert "send_paper_result_telegram" in task_ids
