from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from pretrend.config import get_settings
from pretrend.observability.explainability.cache import invalidate, lookup, store


@pytest.fixture(scope="module")
def pg_engine() -> Engine:
    try:
        database_url = get_settings().database_url
    except ValidationError as exc:
        pytest.skip(f"postgres settings unavailable for explainability tests: {exc}")
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            exists = conn.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = 'explainability_cache'
                    """
                )
            ).scalar_one_or_none()
    except SQLAlchemyError as exc:
        pytest.skip(f"postgres unavailable for explainability tests: {exc}")
    if exists != "explainability_cache":
        pytest.skip("explainability_cache table is not migrated")
    return engine


@pytest.fixture()
def clean_cache(pg_engine: Engine) -> None:
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE explainability_cache"))


def test_lookup_miss_returns_none(pg_engine: Engine, clean_cache: None) -> None:
    assert lookup(pg_engine, "regime", date(2026, 5, 12), "mock", "v1") is None


def test_store_then_lookup_hit(pg_engine: Engine, clean_cache: None) -> None:
    report = {"query_date": "2026-05-12", "disclaimer": "관측입니다."}
    store(pg_engine, "regime", date(2026, 5, 12), "mock", "v1", report)

    assert lookup(pg_engine, "regime", date(2026, 5, 12), "mock", "v1") == report


def test_store_upsert_same_pk(pg_engine: Engine, clean_cache: None) -> None:
    store(pg_engine, "regime", date(2026, 5, 12), "mock", "v1", {"a": 1})
    store(pg_engine, "regime", date(2026, 5, 12), "mock", "v1", {"a": 2})

    assert lookup(pg_engine, "regime", date(2026, 5, 12), "mock", "v1") == {"a": 2}


def test_invalidate_by_prompt_version(pg_engine: Engine, clean_cache: None) -> None:
    store(pg_engine, "regime", date(2026, 5, 12), "mock", "v1", {"a": 1})

    assert invalidate(pg_engine, prompt_version="v1") == 1
    assert lookup(pg_engine, "regime", date(2026, 5, 12), "mock", "v1") is None
