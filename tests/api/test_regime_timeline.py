from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from pretrend.models import GoldMarketStateSimilarityFeature
from .helpers import FakeResult, FakeSession


def _row(trade_date: date) -> GoldMarketStateSimilarityFeature:
    return GoldMarketStateSimilarityFeature(
        trade_date=trade_date,
        short_signal_code=1,
        transition_hazard_10d=0.3,
        built_at=datetime(2026, 5, 14, tzinfo=timezone.utc),
    )


@pytest.mark.anyio
async def test_regime_timeline_returns_rows(async_client, override_session, api_headers) -> None:
    override_session(
        FakeSession(
            FakeResult(
                scalars=[
                    _row(date(2026, 5, 13)),
                    _row(date(2026, 5, 14)),
                ]
            )
        )
    )

    response = await async_client.get(
        "/api/v1/regime/timeline?start=2026-05-01&end=2026-05-14",
        headers=api_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["start"] == "2026-05-01"
    assert body["end"] == "2026-05-14"
    assert [row["trade_date"] for row in body["data"]] == ["2026-05-13", "2026-05-14"]
    assert body["data"][0]["feature"]["transition_hazard_10d"] == 0.3


@pytest.mark.anyio
async def test_regime_timeline_empty_range_returns_empty_data(
    async_client,
    override_session,
    api_headers,
) -> None:
    override_session(FakeSession(FakeResult(scalars=[])))

    response = await async_client.get(
        "/api/v1/regime/timeline?start=1999-01-01&end=1999-01-31",
        headers=api_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"] == []


@pytest.mark.anyio
async def test_regime_timeline_rejects_large_range(async_client, api_headers) -> None:
    response = await async_client.get(
        "/api/v1/regime/timeline?start=2024-01-01&end=2026-01-02",
        headers=api_headers,
    )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_regime_timeline_rejects_end_before_start(async_client, api_headers) -> None:
    response = await async_client.get(
        "/api/v1/regime/timeline?start=2026-05-14&end=2026-05-13",
        headers=api_headers,
    )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_regime_timeline_auth_required(async_client) -> None:
    response = await async_client.get(
        "/api/v1/regime/timeline?start=2026-05-01&end=2026-05-14"
    )

    assert response.status_code == 401
