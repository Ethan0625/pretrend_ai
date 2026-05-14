from __future__ import annotations

import json
from datetime import date
from typing import Literal

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


class SimilarityNeighbor(BaseModel):
    neighbor_date: date
    score: float
    rank: int
    match_reasons: list[str]


class SimilarityReport(BaseModel):
    query_date: date
    view: Literal["regime", "gold"]
    summary: str
    neighbors: list[SimilarityNeighbor]
    disclaimer: str


def explain_similarity(
    query_date: date,
    view: Literal["regime", "gold"],
    engine: Engine | None = None,
    provider: LLMProvider | None = None,
    force_refresh: bool = False,
) -> SimilarityReport:
    db_engine = engine or _get_engine()
    llm = provider or get_provider()
    use_case = f"similarity_{view}"

    if not force_refresh:
        cached = lookup(db_engine, use_case, query_date, llm.model_id, PROMPT_VERSION)
        if cached is not None:
            return SimilarityReport.model_validate(cached)

    payload = _load_similarity_payload(db_engine, query_date, view)
    raw = llm.call(
        SYSTEM_PROMPT,
        _user_prompt(view, payload),
        max_tokens=1200,
        temperature=0.1,
        timeout_s=60,
    )
    check_invariant_or_raise(raw)
    report = SimilarityReport.model_validate_json(raw)
    report_json = report.model_dump(mode="json")
    check_report_invariant_or_raise(report_json)
    store(db_engine, use_case, query_date, llm.model_id, PROMPT_VERSION, report_json)
    return report


def _load_similarity_payload(engine: Engine, query_date: date, view: str) -> dict:
    table = "similarity_regime" if view == "regime" else "similarity_gold"
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT neighbor_date, score, rank, gap_days
                FROM {table}
                WHERE query_date = :query_date
                ORDER BY rank
                LIMIT 10
                """
            ),
            {"query_date": query_date},
        ).mappings().all()
    return {
        "query_date": query_date.isoformat(),
        "view": view,
        "neighbors": [dict(row) for row in rows],
    }


def _user_prompt(view: str, payload: dict) -> str:
    return (
        "다음 similarity 입력을 기반으로 SimilarityReport JSON을 작성하세요. "
        "예측, 추천, 목표가격, 매수/매도 신호 표현은 금지합니다.\n"
        f"VIEW: {view}\n"
        f"INPUT_JSON:\n{json.dumps(payload, ensure_ascii=False, default=str)}"
    )
