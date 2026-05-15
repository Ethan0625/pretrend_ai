from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pretrend.api.auth import require_api_key
from pretrend.api.db import get_session
from pretrend.api.routers._utils import not_found, row_to_dict, validate_timeline_range
from pretrend.api.schemas import EodFeature, EodResponse, EodTimelineResponse
from pretrend.models import GoldEodFeature


router = APIRouter(
    prefix="/api/v1/eod",
    tags=["eod"],
    dependencies=[Depends(require_api_key)],
)


@router.get("", response_model=EodResponse)
@router.get("/", response_model=EodResponse, include_in_schema=False)
async def get_eod(
    symbol: str,
    trade_date: date,
    session: AsyncSession = Depends(get_session),
) -> EodResponse:
    result = await session.execute(
        select(GoldEodFeature).where(
            GoldEodFeature.symbol == symbol,
            GoldEodFeature.trade_date == trade_date,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise not_found(
            "eod",
            {"symbol": symbol, "trade_date": trade_date.isoformat()},
        )
    return EodResponse(data=EodFeature(**row_to_dict(row)))


@router.get("/timeline", response_model=EodTimelineResponse)
async def get_eod_timeline(
    symbol: str,
    start: date,
    end: date,
    session: AsyncSession = Depends(get_session),
) -> EodTimelineResponse:
    validate_timeline_range(start, end)
    result = await session.execute(
        select(GoldEodFeature)
        .where(
            GoldEodFeature.symbol == symbol,
            GoldEodFeature.trade_date >= start,
            GoldEodFeature.trade_date <= end,
        )
        .order_by(GoldEodFeature.trade_date)
    )
    return EodTimelineResponse(
        symbol=symbol,
        start=start,
        end=end,
        data=[EodFeature(**row_to_dict(row)) for row in result.scalars().all()],
    )
