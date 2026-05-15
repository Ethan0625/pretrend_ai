from __future__ import annotations

import json
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pretrend.api.auth import require_api_key
from pretrend.api.db import get_session
from pretrend.api.routers._utils import not_found
from pretrend.api.schemas import ExplainResponse
from pretrend.models import ExplainabilityCache
from pretrend.observability.explainability.llm_client import check_invariant_or_raise


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


@router.get("/api/v1/macro/explain", response_model=ExplainResponse)
async def explain_macro(
    trade_date: date,
    session: AsyncSession = Depends(get_session),
) -> ExplainResponse:
    return await _load_explain(session, "macro", trade_date)


async def _load_explain(
    session: AsyncSession,
    use_case: Literal["similarity_regime", "similarity_gold", "regime", "macro"],
    query_date: date,
) -> ExplainResponse:
    result = await session.execute(
        select(ExplainabilityCache)
        .where(
            ExplainabilityCache.use_case == use_case,
            ExplainabilityCache.query_date == query_date,
        )
        .order_by(ExplainabilityCache.built_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise not_found(
            "explainability_cache",
            {"use_case": use_case, "query_date": query_date.isoformat()},
        )
    check_invariant_or_raise(json.dumps(row.report_json, ensure_ascii=False, sort_keys=True))
    return ExplainResponse(
        use_case=row.use_case,
        query_date=row.query_date,
        model_id=row.model_id,
        prompt_version=row.prompt_version,
        report=row.report_json,
        built_at=row.built_at,
    )
