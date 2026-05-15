from __future__ import annotations

from datetime import date

import pytest

from pretrend.models import GoldMacroFeature
from .helpers import FakeResult, FakeSession


def _row(trade_date: date) -> GoldMacroFeature:
    return GoldMacroFeature(
        indicator_id="CPI",
        trade_date=trade_date,
        selected_observation_date=date(2026, 4, 30),
        selected_value=3.1,
        selected_release_date=date(2026, 5, 1),
        delta_1m=0.1,
        direction="up",
        regime="tightening",
        zscore_12m=0.5,
        release_source="econ_events",
        is_assumption_based=False,
    )


@pytest.mark.anyio
async def test_macro_single(async_client, override_session, api_headers) -> None:
    override_session(FakeSession(FakeResult(scalar=_row(date(2026, 5, 14)))))

    response = await async_client.get(
        "/api/v1/macro?trade_date=2026-05-14&indicator_id=CPI",
        headers=api_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["indicator_id"] == "CPI"


@pytest.mark.anyio
async def test_macro_timeline(async_client, override_session, api_headers) -> None:
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
        "/api/v1/macro/timeline?indicator_id=CPI&start=2026-05-13&end=2026-05-14",
        headers=api_headers,
    )

    assert response.status_code == 200
    assert len(response.json()["data"]) == 2


@pytest.mark.anyio
async def test_macro_timeline_rejects_large_range(async_client, api_headers) -> None:
    response = await async_client.get(
        "/api/v1/macro/timeline?indicator_id=CPI&start=2024-01-01&end=2026-05-14",
        headers=api_headers,
    )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_macro_missing_returns_404(async_client, override_session, api_headers) -> None:
    override_session(FakeSession(FakeResult(scalar=None)))

    response = await async_client.get(
        "/api/v1/macro?trade_date=2026-05-14&indicator_id=CPI",
        headers=api_headers,
    )

    assert response.status_code == 404


@pytest.mark.anyio
async def test_macro_auth_required(async_client) -> None:
    response = await async_client.get("/api/v1/macro?trade_date=2026-05-14&indicator_id=CPI")

    assert response.status_code == 401
