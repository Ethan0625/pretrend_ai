from __future__ import annotations

import json
from datetime import date

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pretrend.observability.explainability.cache import lookup, store
from pretrend.observability.explainability.llm_client import (
    LLMProvider,
    check_invariant_or_raise,
    check_report_invariant_or_raise,
    get_provider,
)
from pretrend.observability.similarity.producer import _get_engine


PROMPT_VERSION = "v1"
SYSTEM_PROMPT = "당신은 시장 구조 관측 시스템의 설명자입니다. 출력은 한국어 JSON만 허용됩니다."


class RegimeReport(BaseModel):
    query_date: date
    ahs_summary: str
    market_position: str
    transition: str
    disclaimer: str


def explain_regime(
    query_date: date,
    engine: Engine | None = None,
    provider: LLMProvider | None = None,
    force_refresh: bool = False,
) -> RegimeReport:
    db_engine = engine or _get_engine()
    llm = provider or get_provider()
    use_case = "regime"

    if not force_refresh:
        cached = lookup(db_engine, use_case, query_date, llm.model_id, PROMPT_VERSION)
        if cached is not None:
            return RegimeReport.model_validate(cached)

    payload = _load_regime_payload(db_engine, query_date)
    raw = llm.call(
        SYSTEM_PROMPT,
        _user_prompt(payload),
        max_tokens=1000,
        temperature=0.1,
        timeout_s=60,
    )
    check_invariant_or_raise(raw)
    report = RegimeReport.model_validate_json(raw)
    report_json = report.model_dump(mode="json")
    check_report_invariant_or_raise(report_json)
    store(db_engine, use_case, query_date, llm.model_id, PROMPT_VERSION, report_json)
    return report


def _load_regime_payload(engine: Engine, query_date: date) -> dict:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT *
                FROM gold_market_state_similarity_feature
                WHERE trade_date = :query_date
                """
            ),
            {"query_date": query_date},
        ).mappings().first()
    return {"query_date": query_date.isoformat(), "market_state": dict(row) if row else {}}


def _user_prompt(payload: dict) -> str:
    return (
        "다음 regime 입력을 기반으로 RegimeReport JSON을 작성하세요. "
        "예측, 추천, 목표가격, 매수/매도 신호 표현은 금지합니다.\n"
        f"INPUT_JSON:\n{json.dumps(payload, ensure_ascii=False, default=str)}"
    )
