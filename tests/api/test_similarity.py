from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from pretrend.models import SimilarityGold, SimilarityRegime
from .helpers import FakeResult, FakeSession


def _neighbor(model, rank: int):
    return model(
        query_date=date(2026, 5, 14),
        neighbor_date=date(2025, 5, rank),
        rank=rank,
        score=1.0 - rank * 0.01,
        gap_days=365 + rank,
        built_at=datetime(2026, 5, 14, tzinfo=timezone.utc),
    )


@pytest.mark.anyio
async def test_similarity_regime_view(async_client, override_session, api_headers) -> None:
    override_session(FakeSession(FakeResult(scalars=[_neighbor(SimilarityRegime, 1)])))

    response = await async_client.get(
        "/api/v1/similarity?query_date=2026-05-14&view=regime",
        headers=api_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["view"] == "regime"
    assert body["neighbors"][0]["rank"] == 1


@pytest.mark.anyio
async def test_similarity_gold_view(async_client, override_session, api_headers) -> None:
    override_session(FakeSession(FakeResult(scalars=[_neighbor(SimilarityGold, 1)])))

    response = await async_client.get(
        "/api/v1/similarity?query_date=2026-05-14&view=gold",
        headers=api_headers,
    )

    assert response.status_code == 200
    assert response.json()["view"] == "gold"


@pytest.mark.anyio
async def test_similarity_top_n(async_client, override_session, api_headers) -> None:
    rows = [_neighbor(SimilarityRegime, rank) for rank in range(1, 6)]
    override_session(FakeSession(FakeResult(scalars=rows)))

    response = await async_client.get(
        "/api/v1/similarity?query_date=2026-05-14&view=regime&top_n=5",
        headers=api_headers,
    )

    assert response.status_code == 200
    assert len(response.json()["neighbors"]) == 5


@pytest.mark.anyio
async def test_similarity_top_n_limit(async_client, api_headers) -> None:
    response = await async_client.get(
        "/api/v1/similarity?query_date=2026-05-14&view=regime&top_n=200",
        headers=api_headers,
    )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_similarity_invalid_view(async_client, api_headers) -> None:
    response = await async_client.get(
        "/api/v1/similarity?query_date=2026-05-14&view=other",
        headers=api_headers,
    )

    assert response.status_code == 422
