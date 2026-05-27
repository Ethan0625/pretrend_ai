from __future__ import annotations

from datetime import date, datetime, timezone

import httpx
import pytest

from pretrend.api.db import get_session
from pretrend.models import ExplainabilityCache, GoldMarketStateSimilarityFeature
from .helpers import FakeResult, FakeSession


def _row(use_case: str, report: dict | None = None) -> ExplainabilityCache:
    return ExplainabilityCache(
        use_case=use_case,
        query_date=date(2026, 5, 14),
        model_id="vscode_codex",
        prompt_version="p27_v1",
        report_json=report or {"summary": "관측 설명"},
        output_hash="hash",
        built_at=datetime(2026, 5, 14, tzinfo=timezone.utc),
    )


@pytest.mark.anyio
async def test_explain_regime_cache_hit(async_client, override_session, api_headers) -> None:
    override_session(FakeSession(FakeResult(scalar=_row("regime"))))

    response = await async_client.get(
        "/api/v1/regime/explain?trade_date=2026-05-14",
        headers=api_headers,
    )

    assert response.status_code == 200
    assert response.json()["use_case"] == "regime"


@pytest.mark.anyio
async def test_explain_similarity_cache_hit(async_client, override_session, api_headers) -> None:
    override_session(FakeSession(FakeResult(scalar=_row("similarity_regime"))))

    response = await async_client.get(
        "/api/v1/similarity/explain?query_date=2026-05-14&view=regime",
        headers=api_headers,
    )

    assert response.status_code == 200
    assert response.json()["use_case"] == "similarity_regime"


@pytest.mark.anyio
async def test_explain_similarity_events_cache_hit(async_client, override_session, api_headers) -> None:
    override_session(
        FakeSession(
            FakeResult(scalar=_row("similarity_events")),
            FakeResult(scalars=[]),
        )
    )

    response = await async_client.get(
        "/api/v1/similarity/events/explain?query_date=2026-05-14",
        headers=api_headers,
    )

    assert response.status_code == 200
    assert response.json()["use_case"] == "similarity_events"


@pytest.mark.anyio
async def test_explain_similarity_events_overlays_canonical_scores(
    async_client,
    override_session,
    api_headers,
) -> None:
    report = {
        "summary": "현재 관측 상태는 리먼 파산과 유사합니다.",
        "events": [
            {
                "event_name": "리먼 파산",
                "anchor_date": "2008-09-15",
                "actual_date": "2008-09-15",
                "similarity_score": 0.12,
                "match_reasons": ["관측 feature가 유사합니다."],
            }
        ],
        "disclaimer": "관측 해석이며 투자 조언이 아닙니다.",
    }
    override_session(
        FakeSession(
            FakeResult(scalar=_row("similarity_events", report)),
            FakeResult(
                scalars=[
                    GoldMarketStateSimilarityFeature(
                        trade_date=date(2008, 9, 15),
                        short_signal_code=1,
                        transition_hazard_10d=0.2,
                        built_at=datetime(2026, 5, 14, tzinfo=timezone.utc),
                    ),
                    GoldMarketStateSimilarityFeature(
                        trade_date=date(2026, 5, 14),
                        short_signal_code=1,
                        transition_hazard_10d=0.2,
                        built_at=datetime(2026, 5, 14, tzinfo=timezone.utc),
                    ),
                    GoldMarketStateSimilarityFeature(
                        trade_date=date(2020, 3, 16),
                        short_signal_code=-1,
                        transition_hazard_10d=0.8,
                        built_at=datetime(2026, 5, 14, tzinfo=timezone.utc),
                    ),
                ]
            ),
        )
    )

    response = await async_client.get(
        "/api/v1/similarity/events/explain?query_date=2026-05-14",
        headers=api_headers,
    )

    assert response.status_code == 200
    event = response.json()["report"]["events"][0]
    assert event["similarity_score"] == 1.0


@pytest.mark.anyio
async def test_explain_macro_cache_hit(async_client, override_session, api_headers) -> None:
    override_session(FakeSession(FakeResult(scalar=_row("macro"))))

    response = await async_client.get(
        "/api/v1/macro/explain?trade_date=2026-05-14",
        headers=api_headers,
    )

    assert response.status_code == 200
    assert response.json()["use_case"] == "macro"


@pytest.mark.anyio
async def test_explain_cache_miss_returns_404(async_client, override_session, api_headers) -> None:
    override_session(FakeSession(FakeResult(scalar=None), FakeResult(scalar=date(2026, 5, 13))))

    response = await async_client.get(
        "/api/v1/regime/explain?trade_date=2026-05-14",
        headers=api_headers,
    )

    assert response.status_code == 404
    body = response.json()
    assert body["detail"] == "Not found"
    assert body["reason"] == "not_yet_built"
    assert body["latest_available"] == "2026-05-13"
    assert body["query"] == {"use_case": "regime", "query_date": "2026-05-14"}


@pytest.mark.anyio
async def test_explain_invariant_violation_returns_500(
    api_app,
    api_headers,
) -> None:
    bad_term = "pred" + "icted_score"
    fake_session = FakeSession(FakeResult(scalar=_row("regime", {"metric": bad_term})))

    async def _override_session():
        yield fake_session

    api_app.dependency_overrides[get_session] = _override_session
    transport = httpx.ASGITransport(app=api_app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/regime/explain?trade_date=2026-05-14",
            headers=api_headers,
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
