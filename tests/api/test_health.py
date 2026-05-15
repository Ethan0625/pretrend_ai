from __future__ import annotations

import pytest


@pytest.mark.anyio
async def test_health_returns_200_ok(async_client) -> None:
    response = await async_client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert isinstance(body["alembic"], str)


@pytest.mark.anyio
async def test_health_no_api_key_required(async_client) -> None:
    response = await async_client.get("/health")

    assert response.status_code == 200
