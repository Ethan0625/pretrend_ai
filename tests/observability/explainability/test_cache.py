from __future__ import annotations

from datetime import date

from sqlalchemy import Engine

from pretrend.observability.explainability.cache import invalidate, lookup, store


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
