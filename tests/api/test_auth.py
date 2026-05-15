from __future__ import annotations

import importlib

import httpx
import pytest
from fastapi import Depends
from pydantic import ValidationError

from pretrend.api.auth import require_api_key


@pytest.fixture()
def protected_app(api_app):
    @api_app.get("/api/v1/protected", dependencies=[Depends(require_api_key)])
    async def protected() -> dict[str, str]:
        return {"status": "ok"}

    return api_app


@pytest.mark.anyio
async def test_health_no_auth_required(async_client) -> None:
    response = await async_client.get("/health")

    assert response.status_code == 200


@pytest.mark.anyio
async def test_missing_key_returns_401(protected_app) -> None:
    transport = httpx.ASGITransport(app=protected_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/protected")

    assert response.status_code == 401
    assert response.json() == {"detail": "API key required"}


@pytest.mark.anyio
async def test_invalid_key_returns_401(protected_app) -> None:
    transport = httpx.ASGITransport(app=protected_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/protected", headers={"X-API-Key": "bad"})

    assert response.status_code == 401
    assert response.json() == {"detail": "API key invalid"}


@pytest.mark.anyio
async def test_valid_key_passes(protected_app, monkeypatch_api_key: str) -> None:
    transport = httpx.ASGITransport(app=protected_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/protected",
            headers={"X-API-Key": monkeypatch_api_key},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_env_var_missing_startup_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.delenv("PRETREND_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    settings_module = importlib.import_module("pretrend.api.settings")
    settings_module.get_api_settings.cache_clear()

    with pytest.raises(ValidationError):
        settings_module.APISettings()


@pytest.mark.anyio
async def test_x_api_key_header_form(protected_app, monkeypatch_api_key: str) -> None:
    transport = httpx.ASGITransport(app=protected_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/protected",
            headers={"x-api-key": monkeypatch_api_key},
        )

    assert response.status_code == 200
