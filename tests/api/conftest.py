from __future__ import annotations

import importlib
from collections.abc import AsyncGenerator

import httpx
import pytest

from pretrend.api.db import get_session
from .helpers import FakeSession


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
def monkeypatch_api_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = "test-key-xxx"
    monkeypatch.setenv("PRETREND_API_KEY", key)
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("POSTGRES_PORT", "1234")
    monkeypatch.setenv("POSTGRES_USER", "pretrend")
    monkeypatch.setenv("POSTGRES_PASSWORD", "CHANGE_ME")
    monkeypatch.setenv("POSTGRES_DB", "pretrend_obs")
    return key


@pytest.fixture()
def api_app(monkeypatch_api_key: str):
    config_module = importlib.import_module("pretrend.config")
    config_module.get_settings.cache_clear()
    settings_module = importlib.import_module("pretrend.api.settings")
    settings_module.get_api_settings.cache_clear()
    main_module = importlib.import_module("pretrend.api.main")
    return main_module.create_app()


@pytest.fixture()
async def async_client(api_app) -> AsyncGenerator[httpx.AsyncClient, None]:
    transport = httpx.ASGITransport(app=api_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture()
def api_headers(monkeypatch_api_key: str) -> dict[str, str]:
    return {"X-API-Key": monkeypatch_api_key}


@pytest.fixture()
def override_session(api_app):
    def _override(fake_session: FakeSession) -> FakeSession:
        async def _get_session():
            yield fake_session

        api_app.dependency_overrides[get_session] = _get_session
        return fake_session

    return _override
