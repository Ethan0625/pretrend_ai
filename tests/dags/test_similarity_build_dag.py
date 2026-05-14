from __future__ import annotations

import importlib
from datetime import date
from types import SimpleNamespace


def _dag_module():
    return importlib.import_module("dags.similarity_build_dag")


def test_dag_imports_without_airflow() -> None:
    module = _dag_module()
    assert module.similarity_build_dag is not None


def test_dag_schedule() -> None:
    module = _dag_module()
    dag = module.similarity_build_dag
    schedule = getattr(dag, "schedule", None) or getattr(
        dag,
        "schedule_interval",
        None,
    )
    assert module.SCHEDULE == "0 12 * * *"
    assert str(schedule) == "0 12 * * *"


def test_dag_id() -> None:
    module = _dag_module()
    assert module.similarity_build_dag.dag_id == "similarity_build_dag"


def test_dag_tasks_exist() -> None:
    module = _dag_module()
    dag = module.similarity_build_dag
    task_ids = set(getattr(dag, "task_ids", set()))
    if not task_ids and hasattr(dag, "task_dict"):
        task_ids = set(dag.task_dict)
    assert {"build_regime", "build_gold"}.issubset(task_ids)


def test_dag_tasks_independent() -> None:
    module = _dag_module()
    dag = module.similarity_build_dag
    task_dict = getattr(dag, "task_dict", {})
    build_regime = task_dict["build_regime"]
    build_gold = task_dict["build_gold"]
    assert build_regime.upstream_task_ids == set()
    assert build_gold.upstream_task_ids == set()
    assert "build_gold" not in build_regime.downstream_task_ids
    assert "build_regime" not in build_gold.downstream_task_ids


def test_manual_conf_query_range() -> None:
    module = _dag_module()
    context = {
        "dag_run": SimpleNamespace(
            conf={"query_start": "2026-01-01", "query_end": "2026-01-31"}
        )
    }
    assert module._resolve_query_range(context) == (
        date(2026, 1, 1),
        date(2026, 1, 31),
    )
