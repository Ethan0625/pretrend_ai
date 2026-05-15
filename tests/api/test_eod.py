from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from pretrend.models import GoldEodFeature
from .helpers import FakeResult, FakeSession


def _row(trade_date: date) -> GoldEodFeature:
    return GoldEodFeature(
        symbol="SPY",
        trade_date=trade_date,
        open=500.0,
        high=505.0,
        low=499.0,
        close=504.0,
        adj_close=504.0,
        volume=1000,
        currency="USD",
        ret_1d=0.01,
        ret_5d=0.02,
        ret_20d=0.03,
        vol_20d=0.12,
        vol_60d=0.15,
        is_trading_day=True,
        is_missing_imputed=False,
        is_outlier=False,
        is_partial_day=False,
        asset_group="equity",
        asset_name="S&P 500 ETF",
        run_id_gold="test-run",
        ingestion_ts_gold=datetime(2026, 5, 14, tzinfo=timezone.utc),
    )


@pytest.mark.anyio
async def test_eod_single(async_client, override_session, api_headers) -> None:
    override_session(FakeSession(FakeResult(scalar=_row(date(2026, 5, 14)))))

    response = await async_client.get(
        "/api/v1/eod?symbol=SPY&trade_date=2026-05-14",
        headers=api_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["symbol"] == "SPY"


@pytest.mark.anyio
async def test_eod_timeline(async_client, override_session, api_headers) -> None:
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
        "/api/v1/eod/timeline?symbol=SPY&start=2026-05-13&end=2026-05-14",
        headers=api_headers,
    )

    assert response.status_code == 200
    assert len(response.json()["data"]) == 2


@pytest.mark.anyio
async def test_eod_timeline_rejects_large_range(async_client, api_headers) -> None:
    response = await async_client.get(
        "/api/v1/eod/timeline?symbol=SPY&start=2024-01-01&end=2026-05-14",
        headers=api_headers,
    )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_eod_missing_returns_404(async_client, override_session, api_headers) -> None:
    override_session(FakeSession(FakeResult(scalar=None)))

    response = await async_client.get(
        "/api/v1/eod?symbol=SPY&trade_date=2026-05-14",
        headers=api_headers,
    )

    assert response.status_code == 404


@pytest.mark.anyio
async def test_eod_auth_required(async_client) -> None:
    response = await async_client.get("/api/v1/eod?symbol=SPY&trade_date=2026-05-14")

    assert response.status_code == 401
