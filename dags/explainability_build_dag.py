from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta
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
                _FALLBACK_TASKS[task_id] = task_obj
                return task_obj

            _task.__name__ = fn.__name__
            _task.__doc__ = fn.__doc__
            return _task

        return _decorator


DAG_ID = "explainability_build_dag"
SCHEDULE = "0 13 * * *"
TAGS = ["observability", "explainability"]
DEFAULT_PROVIDER = "mock"

DEFAULT_ARGS: Dict[str, Any] = {
    "owner": "pretrend",
    "retries": 3,
    "retry_delay": timedelta(minutes=10),
    "depends_on_past": False,
}


class MockProvider:
    model_id = "mock"

    def health_check(self, *, timeout_s: int = 10) -> bool:
        return True

    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        timeout_s: int,
    ) -> str:
        query_date = _extract_query_date(user_prompt)
        if "SimilarityReport" in user_prompt:
            view = "gold" if "VIEW: gold" in user_prompt else "regime"
            return json.dumps(
                {
                    "query_date": query_date,
                    "view": view,
                    "summary": "입력된 유사 구간의 공통 관측 특징을 요약했습니다.",
                    "neighbors": [],
                    "disclaimer": "이 설명은 관측 데이터 해석이며 투자 조언이 아닙니다.",
                },
                ensure_ascii=False,
            )
        if "RegimeReport" in user_prompt:
            return json.dumps(
                {
                    "query_date": query_date,
                    "ahs_summary": "현재 축별 상태를 관측 기준으로 정리했습니다.",
                    "market_position": "시장 위치는 입력 feature 기준으로 해석했습니다.",
                    "transition": "전환 여부는 입력된 전이 feature만 반영했습니다.",
                    "disclaimer": "이 설명은 관측 데이터 해석이며 투자 조언이 아닙니다.",
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "query_date": query_date,
                "indicators": [],
                "disclaimer": "이 설명은 관측 데이터 해석이며 투자 조언이 아닙니다.",
            },
            ensure_ascii=False,
        )


def _extract_query_date(user_prompt: str) -> str:
    match = re.search(r'"query_date":\s*"([0-9]{4}-[0-9]{2}-[0-9]{2})"', user_prompt)
    if match:
        return match.group(1)
    return (_today_kst() - timedelta(days=1)).isoformat()


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


def _resolve_query_dates(context: dict[str, Any] | None = None) -> list[date]:
    conf = _dag_run_conf(context or {})
    if conf.get("query_date"):
        return [_parse_date(conf["query_date"])]

    query_end = _today_kst() - timedelta(days=1)
    days_back = max(int(conf.get("days_back", 1)), 1)
    query_start = query_end - timedelta(days=days_back - 1)
    return [query_start + timedelta(days=offset) for offset in range(days_back)]


def _resolve_provider(context: dict[str, Any] | None = None):
    conf = _dag_run_conf(context or {})
    provider_name = conf.get("provider")
    provider_key = str(provider_name).strip() if provider_name is not None else ""
    if not provider_key:
        provider_key = (
            os.getenv("PRETREND_EXPLAINABILITY_PROVIDER", "").strip()
            or os.getenv("PRETREND_LLM_PROVIDER", "").strip()
            or DEFAULT_PROVIDER
        )
    if provider_key.lower() == "mock":
        provider = MockProvider()
    else:
        from pretrend.observability.explainability.llm_client import get_provider

        provider = get_provider(provider_key)

    if not provider.health_check():
        raise RuntimeError(f"explainability provider health check failed: {provider.model_id}")
    return provider


def _current_context() -> dict[str, Any]:
    try:
        from airflow.operators.python import get_current_context
    except ModuleNotFoundError:  # pragma: no cover - pytest env fallback
        return {}
    return get_current_context()


@dag(
    dag_id=DAG_ID,
    description="Multi-use-case LLM explainability (similarity / regime / macro)",
    default_args=DEFAULT_ARGS,
    start_date=_start_date(),
    schedule=SCHEDULE,
    catchup=False,
    max_active_runs=1,
    tags=TAGS,
)
def explainability_build():
    @task(task_id="build_similarity")
    def build_similarity_task() -> dict[str, Any]:
        from pretrend.observability.explainability.similarity_explainer import (
            explain_similarity,
        )

        context = _current_context()
        provider = _resolve_provider(context)
        query_dates = _resolve_query_dates(context)
        for query_date in query_dates:
            explain_similarity(query_date, "regime", provider=provider)
            explain_similarity(query_date, "gold", provider=provider)
        return {"dates": [d.isoformat() for d in query_dates], "views": ["regime", "gold"]}

    @task(task_id="build_regime")
    def build_regime_task() -> dict[str, Any]:
        from pretrend.observability.explainability.regime_explainer import explain_regime

        context = _current_context()
        provider = _resolve_provider(context)
        query_dates = _resolve_query_dates(context)
        for query_date in query_dates:
            explain_regime(query_date, provider=provider)
        return {"dates": [d.isoformat() for d in query_dates]}

    @task(task_id="build_macro")
    def build_macro_task() -> dict[str, Any]:
        from pretrend.observability.explainability.macro_explainer import explain_macro

        context = _current_context()
        provider = _resolve_provider(context)
        query_dates = _resolve_query_dates(context)
        for query_date in query_dates:
            explain_macro(query_date, provider=provider)
        return {"dates": [d.isoformat() for d in query_dates]}

    build_similarity_task()
    build_regime_task()
    build_macro_task()


explainability_build_dag = explainability_build()
