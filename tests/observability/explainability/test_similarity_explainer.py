from __future__ import annotations

import json
from datetime import date

import pytest
from sqlalchemy import Engine, text

from pretrend.observability.explainability.cache import store
from pretrend.observability.explainability.llm_client import InvariantViolationError
from pretrend.observability.explainability.similarity_explainer import (
    PROMPT_VERSION,
    explain_similarity,
)


class FakeProvider:
    model_id = "mock"

    def __init__(self, response: dict | str) -> None:
        self.response = response
        self.calls = 0

    def health_check(self, *, timeout_s: int = 10) -> bool:
        return True

    def call(self, *args, **kwargs) -> str:
        self.calls += 1
        return self.response if isinstance(self.response, str) else json.dumps(self.response)


def _report() -> dict:
    return {
        "query_date": "2026-05-12",
        "view": "regime",
        "summary": "과거 유사 구간이 관측됩니다.",
        "neighbors": [],
        "disclaimer": "본 결과는 과거 유사성 관측이며 예측이 아닙니다.",
    }


def test_explain_similarity_cache_hit(pg_engine: Engine, clean_cache: None) -> None:
    store(pg_engine, "similarity_regime", date(2026, 5, 12), "mock", PROMPT_VERSION, _report())
    provider = FakeProvider(_report())

    report = explain_similarity(date(2026, 5, 12), "regime", pg_engine, provider)

    assert report.summary == "과거 유사 구간이 관측됩니다."
    assert provider.calls == 0


def test_explain_similarity_cache_miss_calls_provider(pg_engine: Engine, clean_cache: None) -> None:
    provider = FakeProvider(_report())

    report = explain_similarity(date(2026, 5, 12), "regime", pg_engine, provider)

    assert report.view == "regime"
    assert provider.calls == 1


def test_explain_similarity_invariant_violation_raises(
    pg_engine: Engine,
    clean_cache: None,
) -> None:
    provider = FakeProvider('{"predicted_": "bad"}')

    with pytest.raises(InvariantViolationError):
        explain_similarity(date(2026, 5, 12), "regime", pg_engine, provider)

    with pg_engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM explainability_cache")).scalar_one()
    assert count == 0
