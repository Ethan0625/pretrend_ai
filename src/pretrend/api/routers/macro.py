from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pretrend.api.auth import require_api_key
from pretrend.api.db import get_session
from pretrend.api.routers._utils import not_found, row_to_dict, validate_timeline_range
from pretrend.api.schemas import MacroFeature, MacroResponse, MacroTimelineResponse
from pretrend.models import GoldMacroFeature


router = APIRouter(
    prefix="/api/v1/macro",
    tags=["macro"],
    dependencies=[Depends(require_api_key)],
)


@router.get("", response_model=MacroResponse)
@router.get("/", response_model=MacroResponse, include_in_schema=False)
async def get_macro(
    trade_date: date,
    indicator_id: str,
    session: AsyncSession = Depends(get_session),
) -> MacroResponse:
    result = await session.execute(
        select(GoldMacroFeature).where(
            GoldMacroFeature.trade_date == trade_date,
            GoldMacroFeature.indicator_id == indicator_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise not_found(
            "macro",
            {"trade_date": trade_date.isoformat(), "indicator_id": indicator_id},
        )
    return MacroResponse(data=MacroFeature(**row_to_dict(row)))


@router.get("/timeline", response_model=MacroTimelineResponse)
async def get_macro_timeline(
    indicator_id: str,
    start: date,
    end: date,
    session: AsyncSession = Depends(get_session),
) -> MacroTimelineResponse:
    validate_timeline_range(start, end)
    result = await session.execute(
        select(GoldMacroFeature)
        .where(
            GoldMacroFeature.indicator_id == indicator_id,
            GoldMacroFeature.trade_date >= start,
            GoldMacroFeature.trade_date <= end,
        )
        .order_by(GoldMacroFeature.trade_date)
    )
    return MacroTimelineResponse(
        indicator_id=indicator_id,
        start=start,
        end=end,
        data=[MacroFeature(**row_to_dict(row)) for row in result.scalars().all()],
    )
