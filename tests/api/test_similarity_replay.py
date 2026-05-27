from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from pretrend.models import GoldEodFeature, GoldMarketStateSimilarityFeature, SimilarityRegime
from .helpers import FakeResult, FakeSession


def _regime_row(
    trade_date: date,
    *,
    short_signal_code: int = 1,
    transition_hazard_10d: float = 0.25,
) -> GoldMarketStateSimilarityFeature:
    return GoldMarketStateSimilarityFeature(
        trade_date=trade_date,
        short_signal_code=short_signal_code,
        transition_hazard_10d=transition_hazard_10d,
        built_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
    )


def _eod_row(
    symbol: str,
    trade_date: date,
    adj_close: float,
    *,
    asset_name: str | None = None,
) -> GoldEodFeature:
    return GoldEodFeature(
        symbol=symbol,
        trade_date=trade_date,
        open=adj_close,
        high=adj_close,
        low=adj_close,
        close=adj_close,
        adj_close=adj_close,
        volume=1_000_000,
        currency="USD",
        is_trading_day=True,
        is_missing_imputed=False,
        is_outlier=False,
        is_partial_day=False,
        asset_group="INDEX",
        asset_name=asset_name or symbol,
        run_id_gold="test",
        ingestion_ts_gold=datetime(2026, 5, 26, tzinfo=timezone.utc),
    )


@pytest.mark.anyio
async def test_similarity_replay_returns_event_eod_trajectories(
    async_client,
    override_session,
    api_headers,
) -> None:
    override_session(
        FakeSession(
            FakeResult(
                scalars=[
                    _regime_row(date(2008, 9, 15)),
                    _regime_row(date(2020, 3, 16), short_signal_code=-1, transition_hazard_10d=0.8),
                    _regime_row(date(2026, 5, 26)),
                ]
            ),
            FakeResult(
                scalars=[
                    _eod_row("SPY", date(2008, 9, 12), 90.0, asset_name="SP500"),
                    _eod_row("SPY", date(2008, 9, 15), 100.0, asset_name="SP500"),
                    _eod_row("SPY", date(2008, 9, 16), 95.0, asset_name="SP500"),
                    _eod_row("SPY", date(2026, 5, 23), 90.0, asset_name="SP500"),
                    _eod_row("SPY", date(2026, 5, 26), 100.0, asset_name="SP500"),
                    _eod_row("SPY", date(2026, 5, 27), 95.0, asset_name="SP500"),
                    _eod_row("QQQ", date(2008, 9, 15), 50.0, asset_name="NASDAQ100"),
                    _eod_row("QQQ", date(2008, 9, 16), 55.0, asset_name="NASDAQ100"),
                    _eod_row("QQQ", date(2026, 5, 26), 50.0, asset_name="NASDAQ100"),
                    _eod_row("QQQ", date(2026, 5, 27), 55.0, asset_name="NASDAQ100"),
                ]
            ),
        )
    )

    response = await async_client.get(
        "/api/v1/similarity/replay?query_date=2026-05-26&view=events&top_n=1&compare_days=3&forward_days=1&top_assets=2&symbol=SPY&ranking_symbols=SPY,QQQ",
        headers=api_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["query_date"] == "2026-05-26"
    assert body["view"] == "events"
    assert body["symbol"] == "SPY"
    assert body["asset_name"] == "SP500"
    assert body["compare_days"] == 3
    assert body["forward_days"] == 1
    assert body["trajectories"][0]["event_name"] == "리먼 파산"
    assert body["trajectories"][0]["actual_date"] == "2008-09-15"
    assert body["trajectories"][0]["rank"] == 1
    assert body["trajectories"][0]["state_similarity_score"] == 1.0
    assert body["trajectories"][0]["trajectory_similarity_score"] == pytest.approx(1.0)
    assert body["trajectories"][0]["compare_start"] == "2008-09-12"
    assert body["trajectories"][0]["compare_end"] == "2008-09-15"
    assert body["trajectories"][0]["window_end"] == "2008-09-16"

    historical = body["trajectories"][0]["historical_path"]
    assert historical["symbol"] == "SPY"
    assert historical["asset_name"] == "SP500"
    assert historical["base_date"] == "2008-09-15"
    assert historical["base_adj_close"] == 100.0
    assert [row["day_offset"] for row in historical["points"]] == [-3, 0, 1]
    assert [row["normalized_return"] for row in historical["points"]] == pytest.approx(
        [-0.1, 0.0, -0.05]
    )

    current = body["trajectories"][0]["current_path"]
    assert [row["day_offset"] for row in current["points"]] == [-3, 0]
    assert [row["normalized_return"] for row in current["points"]] == pytest.approx(
        [-0.1, 0.0]
    )
    overlays = body["trajectories"][0]["overlay_assets"]
    assert len(overlays) <= 2
    assert overlays[0]["symbol"] == "SPY"
    assert [row["day_offset"] for row in overlays[0]["historical_path"]["points"]] == [-3, 0, 1]
    ranking = body["trajectories"][0]["asset_rankings"]
    spy_rank = next(item for item in ranking if item["symbol"] == "SPY")
    assert spy_rank["asset_name"] == "SP500"
    assert spy_rank["trajectory_similarity_score"] == pytest.approx(1.0)


@pytest.mark.anyio
async def test_similarity_replay_before_zero_starts_at_event_anchor(
    async_client,
    override_session,
    api_headers,
) -> None:
    override_session(
        FakeSession(
            FakeResult(
                scalars=[
                    _regime_row(date(2008, 9, 15)),
                    _regime_row(date(2020, 3, 16), short_signal_code=-1, transition_hazard_10d=0.8),
                    _regime_row(date(2026, 5, 26)),
                ]
            ),
            FakeResult(
                scalars=[
                    _eod_row("SPY", date(2008, 9, 12), 90.0),
                    _eod_row("SPY", date(2008, 9, 15), 100.0),
                    _eod_row("SPY", date(2008, 9, 16), 105.0),
                    _eod_row("SPY", date(2026, 5, 26), 100.0),
                    _eod_row("SPY", date(2026, 5, 27), 105.0),
                ]
            ),
        )
    )

    response = await async_client.get(
        "/api/v1/similarity/replay?query_date=2026-05-26&view=events&top_n=1&compare_days=0&forward_days=1&symbol=SPY&ranking_symbols=SPY",
        headers=api_headers,
    )

    assert response.status_code == 200
    points = response.json()["trajectories"][0]["historical_path"]["points"]
    assert [row["trade_date"] for row in points] == ["2008-09-15", "2008-09-16"]
    assert [row["normalized_return"] for row in points] == pytest.approx([0.0, 0.05])


@pytest.mark.anyio
async def test_similarity_replay_supports_regime_neighbor_windows(
    async_client,
    override_session,
    api_headers,
) -> None:
    override_session(
        FakeSession(
            FakeResult(
                scalars=[
                    SimilarityRegime(
                        query_date=date(2026, 5, 26),
                        neighbor_date=date(2008, 9, 15),
                        rank=1,
                        score=0.9,
                        gap_days=6463,
                        built_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
                    )
                ]
            ),
            FakeResult(
                scalars=[
                    _eod_row("SPY", date(2008, 9, 14), 102.0),
                    _eod_row("SPY", date(2008, 9, 15), 100.0),
                    _eod_row("SPY", date(2008, 9, 16), 98.0),
                    _eod_row("SPY", date(2026, 5, 25), 102.0),
                    _eod_row("SPY", date(2026, 5, 26), 100.0),
                    _eod_row("SPY", date(2026, 5, 27), 98.0),
                ]
            ),
        )
    )

    response = await async_client.get(
        "/api/v1/similarity/replay?query_date=2026-05-26&view=regime&top_n=1&compare_days=1&forward_days=1&symbol=SPY&ranking_symbols=SPY",
        headers=api_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["view"] == "regime"
    assert body["trajectories"][0]["label"] == "2008-09-15"
    assert body["trajectories"][0]["state_similarity_score"] == 0.9
    assert body["trajectories"][0]["trajectory_similarity_score"] == pytest.approx(1.0)


@pytest.mark.anyio
async def test_similarity_replay_missing_query_returns_latest_available(
    async_client,
    override_session,
    api_headers,
) -> None:
    override_session(
        FakeSession(
            FakeResult(scalars=[]),
            FakeResult(scalar=date(2026, 5, 26)),
        )
    )

    response = await async_client.get(
        "/api/v1/similarity/replay?query_date=2026-05-27&view=events",
        headers=api_headers,
    )

    assert response.status_code == 404
    body = response.json()
    assert body["detail"] == "Not found"
    assert body["resource"] == "similarity_replay"
    assert body["reason"] == "not_yet_built"
    assert body["latest_available"] == "2026-05-26"
    assert body["query"] == {"query_date": "2026-05-27", "view": "events"}


@pytest.mark.anyio
async def test_similarity_replay_rejects_large_window(async_client, api_headers) -> None:
    response = await async_client.get(
        "/api/v1/similarity/replay?query_date=2026-05-26&view=events&compare_days=180&forward_days=186",
        headers=api_headers,
    )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_similarity_replay_rejects_unknown_view(async_client, api_headers) -> None:
    response = await async_client.get(
        "/api/v1/similarity/replay?query_date=2026-05-26&view=unknown",
        headers=api_headers,
    )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_similarity_replay_top_n_limit(async_client, api_headers) -> None:
    response = await async_client.get(
        "/api/v1/similarity/replay?query_date=2026-05-26&view=events&top_n=11",
        headers=api_headers,
    )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_similarity_replay_ranking_symbol_limit(async_client, api_headers) -> None:
    symbols = ",".join(f"S{i}" for i in range(61))
    response = await async_client.get(
        f"/api/v1/similarity/replay?query_date=2026-05-26&view=events&ranking_symbols={symbols}",
        headers=api_headers,
    )

    assert response.status_code == 422
