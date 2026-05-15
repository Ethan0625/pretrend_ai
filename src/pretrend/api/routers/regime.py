from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pretrend.api.auth import require_api_key
from pretrend.api.db import get_session
from pretrend.api.routers._utils import not_found, row_to_dict
from pretrend.api.schemas import RegimeResponse
from pretrend.models import GoldMarketStateSimilarityFeature


router = APIRouter(
    prefix="/api/v1/regime",
    tags=["regime"],
    dependencies=[Depends(require_api_key)],
)


@router.get("", response_model=RegimeResponse)
@router.get("/", response_model=RegimeResponse, include_in_schema=False)
async def get_regime(
    trade_date: date,
    session: AsyncSession = Depends(get_session),
) -> RegimeResponse:
    result = await session.execute(
        select(GoldMarketStateSimilarityFeature).where(
            GoldMarketStateSimilarityFeature.trade_date == trade_date
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise not_found("regime", {"trade_date": trade_date.isoformat()})
    return RegimeResponse(
        trade_date=row.trade_date,
        feature=row_to_dict(row, exclude={"trade_date", "built_at"}),
        built_at=row.built_at,
    )
