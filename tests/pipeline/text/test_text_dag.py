from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_module():
    pytest.importorskip("pendulum")
    pytest.importorskip("airflow")
    repo_root = Path(__file__).resolve().parents[3]
    mod_path = repo_root / "dags" / "text_pipeline_dag.py"
    spec = importlib.util.spec_from_file_location("text_pipeline_dag_mod", mod_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_text_pipeline_dag_has_gold_llm_task():
    text_pipeline_dag = _load_module().text_pipeline_dag
    task_ids = [t.task_id for t in text_pipeline_dag.tasks]
    assert "run_text_gold_llm_build" in task_ids


def test_text_pipeline_dag_gold_llm_after_gold():
    text_pipeline_dag = _load_module().text_pipeline_dag
    gold_task = text_pipeline_dag.get_task("run_text_gold_build")
    llm_task = text_pipeline_dag.get_task("run_text_gold_llm_build")
    assert gold_task.task_id in [t.task_id for t in llm_task.upstream_list]
