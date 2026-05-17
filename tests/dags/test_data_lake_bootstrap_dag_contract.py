from __future__ import annotations

import importlib

import pytest


pytest.importorskip("airflow")


def _task_dict(dag):
    return getattr(dag, "task_dict", {})


def test_ofs_002_macro_pipeline_waits_for_bootstrap_guard() -> None:
    """OFS-002: marker 없는 data lake에서는 macro job 전에 bootstrap guard가 먼저 돈다."""
    module = importlib.import_module("dags.macro_pipeline_dag")
    task_dict = _task_dict(module.macro_pipeline_dag)

    bootstrap = task_dict["ensure_data_lake_bootstrap"]
    run_macro = task_dict["run_macro_job"]

    assert "ensure_data_lake_bootstrap" in run_macro.upstream_task_ids
    assert "run_macro_job" in bootstrap.downstream_task_ids


def test_ofs_002_eod_pipeline_waits_for_bootstrap_guard_before_bronze() -> None:
    """OFS-002: marker 없는 data lake에서는 EOD Bronze 전에 bootstrap guard가 먼저 돈다."""
    module = importlib.import_module("dags.eod_pipeline_dag")
    task_dict = _task_dict(module.eod_pipeline_dag)

    bootstrap = task_dict["ensure_data_lake_bootstrap"]
    bronze = task_dict["run_eod_bronze_ingest"]
    silver = task_dict["run_eod_silver_features"]
    gold = task_dict["run_eod_gold_features"]

    assert "ensure_data_lake_bootstrap" in bronze.upstream_task_ids
    assert "run_eod_bronze_ingest" in bootstrap.downstream_task_ids
    assert "run_eod_bronze_ingest" in silver.upstream_task_ids
    assert "run_eod_silver_features" in gold.upstream_task_ids
