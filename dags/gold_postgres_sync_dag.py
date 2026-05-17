from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, Dict

try:
    import pendulum
except ModuleNotFoundError:  # pragma: no cover - pytest env smoke import fallback
    pendulum = None


_FALLBACK_TASKS: dict[str, Any] = {}


try:
    from airflow.decorators import dag, task
except ModuleNotFoundError:  # pragma: no cover - pytest env smoke import fallback
    def dag(*args, **kwargs):
        def _decorator(fn):
            def _factory():
                _FALLBACK_TASKS.clear()
                fn()
                return SimpleNamespace(
                    dag_id=kwargs.get("dag_id"),
                    schedule=kwargs.get("schedule"),
                    schedule_interval=kwargs.get("schedule_interval")
                    or kwargs.get("schedule"),
                    catchup=kwargs.get("catchup"),
                    max_active_runs=kwargs.get("max_active_runs"),
                    default_args=kwargs.get("default_args", {}),
                    tags=kwargs.get("tags", []),
                    task_ids=set(_FALLBACK_TASKS),
                    task_dict=dict(_FALLBACK_TASKS),
                )

            return _factory

        return _decorator

    def task(*args, **kwargs):
        def _decorator(fn):
            task_id = kwargs.get("task_id") or fn.__name__

            def _task(*_args, **_kwargs):
                task_obj = SimpleNamespace(
                    task_id=task_id,
                    upstream_task_ids=set(),
                    downstream_task_ids=set(),
                )
                for upstream in _args:
                    upstream_task_id = getattr(upstream, "task_id", None)
                    if upstream_task_id:
                        task_obj.upstream_task_ids.add(upstream_task_id)
                        upstream.downstream_task_ids.add(task_id)
                _FALLBACK_TASKS[task_id] = task_obj
                return task_obj

            _task.__name__ = fn.__name__
            _task.__doc__ = fn.__doc__
            return _task

        return _decorator


DAG_ID = "gold_postgres_sync_dag"
SCHEDULE = "0 11 * * *"
TAGS = ["observability", "sync"]

DEFAULT_ARGS: Dict[str, Any] = {
    "owner": "pretrend",
    "retries": 3,
    "retry_delay": timedelta(minutes=10),
    "depends_on_past": False,
}


def _start_date():
    if pendulum is not None:
        return pendulum.datetime(2026, 5, 13, tz="Asia/Seoul")
    return datetime(2026, 5, 13)


@dag(
    dag_id=DAG_ID,
    description="Parquet Gold to Postgres mirror sync (incremental UPSERT)",
    default_args=DEFAULT_ARGS,
    start_date=_start_date(),
    schedule=SCHEDULE,
    catchup=False,
    max_active_runs=1,
    tags=TAGS,
)
def gold_postgres_sync():
    @task(task_id="ensure_data_lake_bootstrap")
    def ensure_data_lake_bootstrap_task() -> dict[str, Any]:
        from pretrend.ops.backfill_once import run_backfill_once

        return run_backfill_once()

    @task(task_id="sync_macro")
    def sync_macro_task(_bootstrap_summary: dict[str, Any]) -> dict[str, Any]:
        from pretrend.pipeline.sync.gold_postgres import sync_gold_macro

        return sync_gold_macro()

    @task(task_id="sync_eod")
    def sync_eod_task(_bootstrap_summary: dict[str, Any]) -> dict[str, Any]:
        from pretrend.pipeline.sync.gold_postgres import sync_gold_eod

        return sync_gold_eod()

    bootstrap_summary = ensure_data_lake_bootstrap_task()
    sync_macro_task(bootstrap_summary)
    sync_eod_task(bootstrap_summary)


gold_postgres_sync_dag = gold_postgres_sync()
