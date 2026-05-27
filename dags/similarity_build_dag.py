from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from typing import Any, Dict

try:
    import pendulum
except ModuleNotFoundError:  # pragma: no cover - pytest env smoke import fallback
    pendulum = None


_FALLBACK_TASKS: dict[str, Any] = {}


class _FallbackTask(SimpleNamespace):
    def __rshift__(self, other):
        self.downstream_task_ids.add(other.task_id)
        other.upstream_task_ids.add(self.task_id)
        return other


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
                task_obj = _FallbackTask(
                    task_id=task_id,
                    upstream_task_ids=set(),
                    downstream_task_ids=set(),
                )
                _FALLBACK_TASKS[task_id] = task_obj
                return task_obj

            _task.__name__ = fn.__name__
            _task.__doc__ = fn.__doc__
            return _task

        return _decorator


DAG_ID = "similarity_build_dag"
SCHEDULE = "0 12 * * *"
TAGS = ["observability", "similarity"]

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


def _today_kst() -> date:
    if pendulum is not None:
        return pendulum.now("Asia/Seoul").date()
    return datetime.now().date()


def _parse_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def _dag_run_conf(context: dict[str, Any]) -> dict[str, Any]:
    dag_run = context.get("dag_run")
    conf = getattr(dag_run, "conf", None)
    return conf if isinstance(conf, dict) else {}


def _resolve_query_range(context: dict[str, Any] | None = None) -> tuple[date, date]:
    conf = _dag_run_conf(context or {})
    if conf.get("query_start") and conf.get("query_end"):
        return _parse_date(conf["query_start"]), _parse_date(conf["query_end"])

    query_end = _today_kst() - timedelta(days=1)
    query_start = query_end - timedelta(days=5)
    return query_start, query_end


def _current_context() -> dict[str, Any]:
    try:
        from airflow.operators.python import get_current_context
    except ModuleNotFoundError:  # pragma: no cover - pytest env fallback
        return {}
    return get_current_context()


@dag(
    dag_id=DAG_ID,
    description="Multi-view market structure similarity build (regime / gold)",
    default_args=DEFAULT_ARGS,
    start_date=_start_date(),
    schedule=SCHEDULE,
    catchup=False,
    max_active_runs=1,
    tags=TAGS,
)
def similarity_build():
    @task(task_id="build_market_state_features")
    def build_market_state_features_task() -> dict[str, Any]:
        from pretrend.observability.similarity.runtime_source import (
            build_market_state_similarity_features_from_db,
        )

        query_start, query_end = _resolve_query_range(_current_context())
        return build_market_state_similarity_features_from_db(query_start, query_end)

    @task(task_id="build_regime")
    def build_regime_task() -> dict[str, Any]:
        from pretrend.observability.similarity.builder import build_similarity_regime

        query_start, query_end = _resolve_query_range(_current_context())
        return build_similarity_regime(query_start, query_end)

    @task(task_id="build_gold")
    def build_gold_task() -> dict[str, Any]:
        from pretrend.observability.similarity.builder import build_similarity_gold

        query_start, query_end = _resolve_query_range(_current_context())
        return build_similarity_gold(query_start, query_end)

    market_state_features = build_market_state_features_task()
    regime_similarity = build_regime_task()
    build_gold_task()
    market_state_features >> regime_similarity


similarity_build_dag = similarity_build()
