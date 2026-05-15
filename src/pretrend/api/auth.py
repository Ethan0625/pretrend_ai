from __future__ import annotations

from typing import Annotated

from fastapi import Header, HTTPException, status

from pretrend.api.settings import get_api_settings


async def require_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    if x_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
        )
    if x_api_key != get_api_settings().api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key invalid",
        )
