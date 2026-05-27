from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pretrend.api.auth import require_api_key
from pretrend.api.db import get_session
from pretrend.api.routers._utils import not_found
from pretrend.api.schemas import (
    EventSimilarityItem,
    EventSimilarityResponse,
    SimilarityNeighbor,
    SimilarityResponse,
)
from pretrend.models import SimilarityGold, SimilarityRegime
from pretrend.observability.similarity.events import compute_event_similarities


router = APIRouter(
    prefix="/api/v1/similarity",
    tags=["similarity"],
    dependencies=[Depends(require_api_key)],
)


@router.get("", response_model=SimilarityResponse)
@router.get("/", response_model=SimilarityResponse, include_in_schema=False)
async def get_similarity(
    query_date: date,
    view: Literal["regime", "gold"],
    top_n: int = Query(default=10, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> SimilarityResponse:
    model = SimilarityRegime if view == "regime" else SimilarityGold
    result = await session.execute(
        select(model)
        .where(model.query_date == query_date)
        .order_by(model.rank)
        .limit(top_n)
    )
    rows = result.scalars().all()
    if not rows:
        raise not_found(
            "similarity",
            {"query_date": query_date.isoformat(), "view": view},
        )
    return SimilarityResponse(
        query_date=query_date,
        view=view,
        neighbors=[
            SimilarityNeighbor(
                neighbor_date=row.neighbor_date,
                rank=row.rank,
                score=row.score,
                gap_days=row.gap_days,
            )
            for row in rows
        ],
    )


@router.get("/events", response_model=EventSimilarityResponse)
async def get_similarity_events(
    query_date: date,
    session: AsyncSession = Depends(get_session),
) -> EventSimilarityResponse:
    query_row, event_rows = await compute_event_similarities(query_date, session)
    if query_row is None:
        raise not_found("regime", {"trade_date": query_date.isoformat()})
    return EventSimilarityResponse(
        query_date=query_date,
        data=[
            EventSimilarityItem(
                event_name=event.name,
                anchor_date=event.anchor_date,
                actual_date=actual_date,
                similarity_score=score,
            )
            for event, actual_date, score in event_rows
        ],
    )
