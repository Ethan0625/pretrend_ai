from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from pretrend.models import GoldMarketStateSimilarityFeature
from .helpers import FakeResult, FakeSession


def _row() -> GoldMarketStateSimilarityFeature:
    return GoldMarketStateSimilarityFeature(
        trade_date=date(2026, 5, 14),
        long_phase_expansion=1,
        mid_regime_code=0,
        short_signal_code=-1,
        long_phase_confidence=0.7,
        built_at=datetime(2026, 5, 14, tzinfo=timezone.utc),
    )


@pytest.mark.anyio
async def test_regime_returns_feature(async_client, override_session, api_headers) -> None:
    override_session(FakeSession(FakeResult(scalar=_row())))

    response = await async_client.get(
        "/api/v1/regime?trade_date=2026-05-14",
        headers=api_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["trade_date"] == "2026-05-14"
    assert body["feature"]["long_phase_expansion"] == 1
    assert body["feature"]["short_signal_code"] == -1


@pytest.mark.anyio
async def test_regime_missing_returns_404(async_client, override_session, api_headers) -> None:
    override_session(FakeSession(FakeResult(scalar=None)))

    response = await async_client.get(
        "/api/v1/regime?trade_date=2026-05-14",
        headers=api_headers,
    )

    assert response.status_code == 404
    assert response.json()["resource"] == "regime"


@pytest.mark.anyio
async def test_regime_invalid_date_returns_422(async_client, api_headers) -> None:
    response = await async_client.get(
        "/api/v1/regime?trade_date=bad-date",
        headers=api_headers,
    )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_regime_auth_required(async_client) -> None:
    response = await async_client.get("/api/v1/regime?trade_date=2026-05-14")

    assert response.status_code == 401


@pytest.mark.anyio
async def test_regime_schema_shape(async_client, override_session, api_headers) -> None:
    override_session(FakeSession(FakeResult(scalar=_row())))

    response = await async_client.get(
        "/api/v1/regime?trade_date=2026-05-14",
        headers=api_headers,
    )

    assert response.status_code == 200
    assert sorted(response.json().keys()) == ["built_at", "feature", "trade_date"]
