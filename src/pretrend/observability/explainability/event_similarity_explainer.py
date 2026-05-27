from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pretrend.observability.explainability.cache import lookup, store
from pretrend.observability.explainability.llm_client import (
    LLMProvider,
    check_invariant_or_raise,
    check_report_invariant_or_raise,
    explainability_timeout_s,
    get_provider,
)
from pretrend.observability.similarity.columns import REGIME_SIMILARITY_FEATURE_COLUMNS
from pretrend.observability.similarity.events import compute_event_similarity_rows
from pretrend.observability.similarity.producer import _get_engine


PROMPT_VERSION = "v1"
USE_CASE = "similarity_events"
SYSTEM_PROMPT = "당신은 시장 구조 관측 시스템의 설명자입니다. 출력은 한국어 JSON만 허용됩니다."


class EventSimilarityExplanation(BaseModel):
    event_name: str
    anchor_date: date
    actual_date: date | None = None
    similarity_score: float | None = None
    match_reasons: list[str]


class EventSimilarityReport(BaseModel):
    query_date: date
    summary: str
    events: list[EventSimilarityExplanation]
    disclaimer: str


def explain_similarity_events(
    query_date: date,
    engine: Engine | None = None,
    provider: LLMProvider | None = None,
    force_refresh: bool = False,
) -> EventSimilarityReport:
    db_engine = engine or _get_engine()
    llm = provider or get_provider()

    if not force_refresh:
        cached = lookup(db_engine, USE_CASE, query_date, llm.model_id, PROMPT_VERSION)
        if cached is not None:
            return EventSimilarityReport.model_validate(cached)

    payload = _load_event_similarity_payload(db_engine, query_date)
    raw = llm.call(
        SYSTEM_PROMPT,
        _user_prompt(payload),
        max_tokens=1200,
        temperature=0.1,
        timeout_s=explainability_timeout_s(),
    )
    check_invariant_or_raise(raw)
    report = EventSimilarityReport.model_validate_json(raw)
    report.events = [
        event
        for event in report.events
        if event.similarity_score is not None and event.similarity_score > 0.0
    ][:5]
    report_json = report.model_dump(mode="json")
    check_report_invariant_or_raise(report_json)
    store(db_engine, USE_CASE, query_date, llm.model_id, PROMPT_VERSION, report_json)
    return report


def _load_event_similarity_payload(engine: Engine, query_date: date) -> dict:
    columns = ["trade_date", *REGIME_SIMILARITY_FEATURE_COLUMNS]
    column_sql = ", ".join(columns)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT {column_sql}
                FROM gold_market_state_similarity_feature
                ORDER BY trade_date
                """
            )
        ).mappings().all()

    records = [SimpleNamespace(**dict(row)) for row in rows]
    query_row, event_rows = compute_event_similarity_rows(query_date, records)
    query_feature = {
        "short_signal_code": getattr(query_row, "short_signal_code", None) if query_row else None,
        "transition_hazard_10d": getattr(query_row, "transition_hazard_10d", None) if query_row else None,
        "risk_gate_flag": getattr(query_row, "risk_gate_flag", None) if query_row else None,
        "run_universe_flag": getattr(query_row, "run_universe_flag", None) if query_row else None,
    }
    return {
        "query_date": query_date.isoformat(),
        "source": "gold_market_state_similarity_feature",
        "query_feature": query_feature,
        "events": [
            {
                "event_name": event.name,
                "anchor_date": event.anchor_date.isoformat(),
                "actual_date": actual_date.isoformat() if actual_date else None,
                "similarity_score": score,
            }
            for event, actual_date, score in event_rows
        ],
    }


def _user_prompt(payload: dict) -> str:
    return (
        "다음 역사 이벤트 유사도 입력을 기반으로 EventSimilarityReport JSON을 작성하세요.\n"
        "반드시 아래 JSON schema의 top-level key만 사용하세요. key를 한국어로 바꾸거나 추가하지 마세요.\n"
        "{"
        '"query_date":"YYYY-MM-DD",'
        '"summary":"현재 관측 상태가 어떤 역사 이벤트들과 유사한지 2~4문장으로 설명",'
        '"events":[{"event_name":"이벤트명","anchor_date":"YYYY-MM-DD","actual_date":"YYYY-MM-DD 또는 null","similarity_score":0.0,"match_reasons":["관측 근거 문장"]}],'
        '"disclaimer":"관측 해석이며 투자 조언이 아니라는 문장"'
        "}\n"
        "events는 similarity_score가 높은 이벤트 중 최대 5개만 사용하세요. "
        "actual_date가 null이거나 similarity_score가 null 또는 0.0 이하인 이벤트는 제외하세요. "
        "설명은 현재 관측 feature와 역사 이벤트의 유사성에만 한정하세요. "
        "예측, 추천, 목표가격, 매수/매도 신호 표현은 금지합니다.\n"
        f"INPUT_JSON:\n{json.dumps(payload, ensure_ascii=False, default=str)}"
    )
