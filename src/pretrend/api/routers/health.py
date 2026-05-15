from __future__ import annotations

from fastapi import APIRouter

from pretrend.api.schemas import HealthResponse


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", alembic="unknown")
