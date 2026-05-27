from __future__ import annotations

from datetime import date, datetime, timezone

import numpy as np
import pytest

from pretrend.models import GoldMarketStateSimilarityFeature
from pretrend.observability.similarity.events import cosine_similarity_score
from .helpers import FakeResult, FakeSession


def _row(
    trade_date: date,
    *,
    short_signal_code: int,
    transition_hazard_10d: float,
) -> GoldMarketStateSimilarityFeature:
    return GoldMarketStateSimilarityFeature(
        trade_date=trade_date,
        short_signal_code=short_signal_code,
        transition_hazard_10d=transition_hazard_10d,
        built_at=datetime(2026, 5, 14, tzinfo=timezone.utc),
    )


@pytest.mark.anyio
async def test_similarity_events_returns_20_items_sorted(
    async_client,
    override_session,
    api_headers,
) -> None:
    override_session(
        FakeSession(
            FakeResult(
                scalars=[
                    _row(date(2008, 9, 15), short_signal_code=1, transition_hazard_10d=0.2),
                    _row(date(2020, 3, 16), short_signal_code=-1, transition_hazard_10d=0.8),
                    _row(date(2026, 5, 14), short_signal_code=1, transition_hazard_10d=0.25),
                ]
            )
        )
    )

    response = await async_client.get(
        "/api/v1/similarity/events?query_date=2026-05-14",
        headers=api_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["query_date"] == "2026-05-14"
    assert len(body["data"]) == 20

    scores = [row["similarity_score"] for row in body["data"]]
    numeric_scores = [score for score in scores if score is not None]
    assert numeric_scores == sorted(numeric_scores, reverse=True)
    assert scores == numeric_scores + [None] * (len(scores) - len(numeric_scores))


@pytest.mark.anyio
async def test_similarity_events_uses_anchor_fallback(
    async_client,
    override_session,
    api_headers,
) -> None:
    override_session(
        FakeSession(
            FakeResult(
                scalars=[
                    _row(date(2003, 4, 4), short_signal_code=1, transition_hazard_10d=0.2),
                    _row(date(2026, 5, 14), short_signal_code=1, transition_hazard_10d=0.25),
                ]
            )
        )
    )

    response = await async_client.get(
        "/api/v1/similarity/events?query_date=2026-05-14",
        headers=api_headers,
    )

    assert response.status_code == 200
    sars = next(row for row in response.json()["data"] if row["event_name"] == "사스 공포")
    assert sars["anchor_date"] == "2003-04-03"
    assert sars["actual_date"] == "2003-04-04"


@pytest.mark.anyio
async def test_similarity_events_missing_query_returns_404(
    async_client,
    override_session,
    api_headers,
) -> None:
    override_session(FakeSession(FakeResult(scalars=[])))

    response = await async_client.get(
        "/api/v1/similarity/events?query_date=2026-05-14",
        headers=api_headers,
    )

    assert response.status_code == 404
    assert response.json()["resource"] == "regime"


@pytest.mark.anyio
async def test_similarity_events_auth_required(async_client) -> None:
    response = await async_client.get("/api/v1/similarity/events?query_date=2026-05-14")

    assert response.status_code == 401


def test_similarity_event_score_clamps_negative_cosine_to_zero() -> None:
    score = cosine_similarity_score(
        np.array([1.0, 0.0]),
        np.array([-1.0, 0.0]),
    )

    assert score == 0.0
