from __future__ import annotations

import json
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pretrend.api.auth import require_api_key
from pretrend.api.db import get_session
from pretrend.api.schemas import ExplainResponse
from pretrend.models import ExplainabilityCache
from pretrend.observability.explainability.llm_client import check_invariant_or_raise
from pretrend.observability.similarity.events import compute_event_similarities


router = APIRouter(tags=["explain"], dependencies=[Depends(require_api_key)])


@router.get("/api/v1/regime/explain", response_model=ExplainResponse)
async def explain_regime(
    trade_date: date,
    session: AsyncSession = Depends(get_session),
) -> ExplainResponse:
    return await _load_explain(session, "regime", trade_date)


@router.get("/api/v1/similarity/explain", response_model=ExplainResponse)
async def explain_similarity(
    query_date: date,
    view: Literal["regime", "gold"],
    session: AsyncSession = Depends(get_session),
) -> ExplainResponse:
    use_case = "similarity_regime" if view == "regime" else "similarity_gold"
    return await _load_explain(session, use_case, query_date)


@router.get("/api/v1/similarity/events/explain", response_model=ExplainResponse)
async def explain_similarity_events(
    query_date: date,
    session: AsyncSession = Depends(get_session),
) -> ExplainResponse:
    return await _load_explain(session, "similarity_events", query_date)


@router.get("/api/v1/macro/explain", response_model=ExplainResponse)
async def explain_macro(
    trade_date: date,
    session: AsyncSession = Depends(get_session),
) -> ExplainResponse:
    return await _load_explain(session, "macro", trade_date)


async def _load_explain(
    session: AsyncSession,
    use_case: Literal["similarity_regime", "similarity_gold", "similarity_events", "regime", "macro"],
    query_date: date,
) -> ExplainResponse:
    result = await session.execute(
        select(ExplainabilityCache)
        .where(
            ExplainabilityCache.use_case == use_case,
            ExplainabilityCache.query_date == query_date,
        )
        .order_by(
            case((ExplainabilityCache.model_id == "mock", 1), else_=0),
            ExplainabilityCache.built_at.desc(),
        )
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        latest_result = await session.execute(
            select(func.max(ExplainabilityCache.query_date)).where(
                ExplainabilityCache.use_case == use_case
            )
        )
        latest = latest_result.scalar_one_or_none()
        raise HTTPException(
            status_code=404,
            detail={
                "detail": "Not found",
                "resource": "explainability_cache",
                "query": {"use_case": use_case, "query_date": query_date.isoformat()},
                "reason": "not_yet_built",
                "latest_available": latest.isoformat() if latest else None,
            },
        )
    report_json = row.report_json
    if use_case == "similarity_events":
        report_json = await _with_canonical_event_scores(session, query_date, report_json)
    check_invariant_or_raise(json.dumps(report_json, ensure_ascii=False, sort_keys=True))
    return ExplainResponse(
        use_case=row.use_case,
        query_date=row.query_date,
        model_id=row.model_id,
        prompt_version=row.prompt_version,
        report=report_json,
        built_at=row.built_at,
    )


async def _with_canonical_event_scores(
    session: AsyncSession,
    query_date: date,
    report_json: dict,
) -> dict:
    query_row, event_rows = await compute_event_similarities(query_date, session)
    if query_row is None:
        return report_json
    canonical = {
        event.name: {
            "anchor_date": event.anchor_date.isoformat(),
            "actual_date": actual_date.isoformat() if actual_date else None,
            "similarity_score": score,
        }
        for event, actual_date, score in event_rows
        if score is not None
    }
    if not canonical or not isinstance(report_json.get("events"), list):
        return report_json
    updated = dict(report_json)
    updated_events = []
    for event_report in report_json["events"]:
        if not isinstance(event_report, dict):
            updated_events.append(event_report)
            continue
        event_name = str(event_report.get("event_name", ""))
        if event_name not in canonical:
            updated_events.append(event_report)
            continue
        updated_event = dict(event_report)
        updated_event.update(canonical[event_name])
        updated_events.append(updated_event)
    updated["events"] = updated_events
    return updated
