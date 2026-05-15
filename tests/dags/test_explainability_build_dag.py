from __future__ import annotations

import importlib
from datetime import date
from types import SimpleNamespace


def _dag_module():
    return importlib.import_module("dags.explainability_build_dag")


def test_dag_imports_without_airflow() -> None:
    module = _dag_module()
    assert module.explainability_build_dag is not None


def test_dag_schedule() -> None:
    module = _dag_module()
    dag = module.explainability_build_dag
    schedule = getattr(dag, "schedule", None) or getattr(
        dag,
        "schedule_interval",
        None,
    )
    assert module.SCHEDULE == "0 13 * * *"
    assert str(schedule) == "0 13 * * *"


def test_dag_id() -> None:
    module = _dag_module()
    assert module.explainability_build_dag.dag_id == "explainability_build_dag"


def test_dag_tasks_exist() -> None:
    module = _dag_module()
    dag = module.explainability_build_dag
    task_ids = set(getattr(dag, "task_ids", set()))
    if not task_ids and hasattr(dag, "task_dict"):
        task_ids = set(dag.task_dict)
    assert {"build_similarity", "build_regime", "build_macro"}.issubset(task_ids)


def test_dag_tasks_independent() -> None:
    module = _dag_module()
    dag = module.explainability_build_dag
    task_dict = getattr(dag, "task_dict", {})
    build_similarity = task_dict["build_similarity"]
    build_regime = task_dict["build_regime"]
    build_macro = task_dict["build_macro"]
    assert build_similarity.upstream_task_ids == set()
    assert build_regime.upstream_task_ids == set()
    assert build_macro.upstream_task_ids == set()
    assert build_regime.task_id not in build_similarity.downstream_task_ids
    assert build_macro.task_id not in build_similarity.downstream_task_ids
    assert build_similarity.task_id not in build_regime.downstream_task_ids
    assert build_macro.task_id not in build_regime.downstream_task_ids


def test_manual_conf_query_date() -> None:
    module = _dag_module()
    context = {"dag_run": SimpleNamespace(conf={"query_date": "2026-01-31"})}
    assert module._resolve_query_dates(context) == [date(2026, 1, 31)]


def test_manual_conf_days_back() -> None:
    module = _dag_module()
    context = {"dag_run": SimpleNamespace(conf={"days_back": 3})}
    today = module._today_kst()
    assert module._resolve_query_dates(context) == [
        today - module.timedelta(days=3),
        today - module.timedelta(days=2),
        today - module.timedelta(days=1),
    ]


def test_mock_provider_health_check() -> None:
    module = _dag_module()
    context = {"dag_run": SimpleNamespace(conf={"provider": "mock"})}
    provider = module._resolve_provider(context)
    assert provider.model_id == "mock"
    assert provider.health_check()


def test_default_provider_is_mock() -> None:
    module = _dag_module()
    context = {"dag_run": SimpleNamespace(conf={})}
    provider = module._resolve_provider(context)
    assert provider.model_id == "mock"
    assert provider.health_check()


def test_blank_provider_is_mock() -> None:
    module = _dag_module()
    context = {"dag_run": SimpleNamespace(conf={"provider": " "})}
    provider = module._resolve_provider(context)
    assert provider.model_id == "mock"
    assert provider.health_check()
