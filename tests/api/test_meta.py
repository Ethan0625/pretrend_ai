from __future__ import annotations

from datetime import date

import pytest

from .helpers import FakeResult, FakeSession


def _meta_session() -> FakeSession:
    return FakeSession(
        FakeResult(scalar="0005"),
        FakeResult(one=(3, date(2026, 5, 11))),
        FakeResult(one=(4, date(2026, 5, 12))),
        FakeResult(one=(5, date(2026, 5, 13))),
        FakeResult(one=(6, date(2026, 5, 14))),
        FakeResult(one=(7, date(2026, 5, 14))),
        FakeResult(all_rows=[("regime", 2), ("macro", 1)]),
    )


@pytest.mark.anyio
async def test_meta_returns_alembic(async_client, override_session, api_headers) -> None:
    override_session(_meta_session())

    response = await async_client.get("/api/v1/meta", headers=api_headers)

    assert response.status_code == 200
    assert response.json()["alembic"] == "0005"


@pytest.mark.anyio
async def test_meta_returns_empty_table_info(async_client, override_session, api_headers) -> None:
    override_session(
        FakeSession(
            FakeResult(scalar="unknown"),
            FakeResult(one=(0, None)),
            FakeResult(one=(0, None)),
            FakeResult(one=(0, None)),
            FakeResult(one=(0, None)),
            FakeResult(one=(0, None)),
            FakeResult(all_rows=[]),
        )
    )

    response = await async_client.get("/api/v1/meta", headers=api_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["tables"]["gold_macro_features"]["row_count"] == 0
    assert body["tables"]["gold_macro_features"]["max_trade_date"] is None
    assert body["explainability_use_cases"] == {}


@pytest.mark.anyio
async def test_meta_returns_row_counts_and_dates(async_client, override_session, api_headers) -> None:
    override_session(_meta_session())

    response = await async_client.get("/api/v1/meta", headers=api_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["tables"]["gold_eod_features"]["row_count"] == 4
    assert body["tables"]["similarity_regime"]["max_query_date"] == "2026-05-14"
    assert body["explainability_use_cases"] == {"regime": 2, "macro": 1}


@pytest.mark.anyio
async def test_meta_auth_required(async_client) -> None:
    response = await async_client.get("/api/v1/meta")

    assert response.status_code == 401


@pytest.mark.anyio
async def test_meta_schema_shape(async_client, override_session, api_headers) -> None:
    override_session(_meta_session())

    response = await async_client.get("/api/v1/meta", headers=api_headers)

    assert response.status_code == 200
    body = response.json()
    assert sorted(body.keys()) == ["alembic", "explainability_use_cases", "tables"]
    assert "gold_market_state_similarity_feature" in body["tables"]
