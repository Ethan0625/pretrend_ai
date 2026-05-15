from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pretrend.api.auth import require_api_key
from pretrend.api.db import get_session
from pretrend.api.schemas import MetaResponse, MetaTableInfo
from pretrend.models import (
    ExplainabilityCache,
    GoldEodFeature,
    GoldMacroFeature,
    SimilarityGold,
    SimilarityRegime,
)
from pretrend.models.gold_market_state_similarity_feature import (
    GoldMarketStateSimilarityFeature,
)


router = APIRouter(
    prefix="/api/v1",
    tags=["meta"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/meta", response_model=MetaResponse)
async def get_meta(session: AsyncSession = Depends(get_session)) -> MetaResponse:
    alembic_result = await session.execute(text("SELECT version_num FROM alembic_version"))
    alembic = str(alembic_result.scalar_one_or_none() or "unknown")

    tables = {
        "gold_macro_features": await _table_info(session, GoldMacroFeature, "trade_date"),
        "gold_eod_features": await _table_info(session, GoldEodFeature, "trade_date"),
        "gold_market_state_similarity_feature": await _table_info(
            session,
            GoldMarketStateSimilarityFeature,
            "trade_date",
        ),
        "similarity_regime": await _table_info(session, SimilarityRegime, "query_date"),
        "similarity_gold": await _table_info(session, SimilarityGold, "query_date"),
    }
    use_cases_result = await session.execute(
        select(ExplainabilityCache.use_case, func.count()).group_by(ExplainabilityCache.use_case)
    )
    use_cases = {str(use_case): int(count) for use_case, count in use_cases_result.all()}
    return MetaResponse(alembic=alembic, tables=tables, explainability_use_cases=use_cases)


async def _table_info(session: AsyncSession, model, date_column_name: str) -> MetaTableInfo:
    date_column = getattr(model, date_column_name)
    result = await session.execute(select(func.count(), func.max(date_column)))
    row_count, max_date = result.one()
    kwargs = {"row_count": int(row_count or 0)}
    if date_column_name == "query_date":
        kwargs["max_query_date"] = max_date
    else:
        kwargs["max_trade_date"] = max_date
    return MetaTableInfo(**kwargs)
