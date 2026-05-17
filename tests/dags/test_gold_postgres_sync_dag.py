from __future__ import annotations

import importlib


def _dag_module():
    return importlib.import_module("dags.gold_postgres_sync_dag")


def test_dag_imports_without_airflow() -> None:
    module = _dag_module()
    assert module.gold_postgres_sync_dag is not None


def test_dag_schedule() -> None:
    module = _dag_module()
    dag = module.gold_postgres_sync_dag
    schedule = getattr(dag, "schedule", None) or getattr(
        dag,
        "schedule_interval",
        None,
    )
    assert module.SCHEDULE == "0 11 * * *"
    assert str(schedule) == "0 11 * * *"


def test_dag_id() -> None:
    module = _dag_module()
    assert module.gold_postgres_sync_dag.dag_id == "gold_postgres_sync_dag"


def test_dag_tasks_exist() -> None:
    module = _dag_module()
    dag = module.gold_postgres_sync_dag
    task_ids = set(getattr(dag, "task_ids", set()))
    if not task_ids and hasattr(dag, "task_dict"):
        task_ids = set(dag.task_dict)
    assert {"ensure_data_lake_bootstrap", "sync_macro", "sync_eod"}.issubset(task_ids)


def test_sync_tasks_wait_for_bootstrap_guard() -> None:
    module = _dag_module()
    dag = module.gold_postgres_sync_dag
    task_dict = getattr(dag, "task_dict", {})
    bootstrap = task_dict["ensure_data_lake_bootstrap"]
    sync_macro = task_dict["sync_macro"]
    sync_eod = task_dict["sync_eod"]
    assert "ensure_data_lake_bootstrap" in sync_macro.upstream_task_ids
    assert "ensure_data_lake_bootstrap" in sync_eod.upstream_task_ids
    assert {"sync_macro", "sync_eod"}.issubset(bootstrap.downstream_task_ids)
    assert "sync_eod" not in sync_macro.downstream_task_ids
    assert "sync_macro" not in sync_eod.downstream_task_ids
