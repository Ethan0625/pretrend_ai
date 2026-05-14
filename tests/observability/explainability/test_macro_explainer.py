from __future__ import annotations

import json
from datetime import date

import pytest
from sqlalchemy import Engine, text

from pretrend.observability.explainability.cache import store
from pretrend.observability.explainability.llm_client import InvariantViolationError
from pretrend.observability.explainability.macro_explainer import (
    PROMPT_VERSION,
    explain_macro,
)
from tests.observability.explainability.test_cache import clean_cache, pg_engine


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
        "indicators": [
            {
                "indicator_id": "CPI",
                "current_value": 1.0,
                "delta_3m": 0.1,
                "regime": "tightening",
                "narrative": "상승 압력이 관측됩니다.",
            }
        ],
        "disclaimer": "본 설명은 과거 vintage 기반 관측이며 미래 예측이 아닙니다.",
    }


def test_explain_macro_cache_hit(pg_engine: Engine, clean_cache: None) -> None:
    store(pg_engine, "macro", date(2026, 5, 12), "mock", PROMPT_VERSION, _report())
    provider = FakeProvider(_report())

    report = explain_macro(date(2026, 5, 12), pg_engine, provider)

    assert report.indicators[0].indicator_id == "CPI"
    assert provider.calls == 0


def test_explain_macro_cache_miss_calls_provider(pg_engine: Engine, clean_cache: None) -> None:
    provider = FakeProvider(_report())

    report = explain_macro(date(2026, 5, 12), pg_engine, provider)

    assert report.indicators
    assert provider.calls == 1


def test_explain_macro_invariant_violation_raises(
    pg_engine: Engine,
    clean_cache: None,
) -> None:
    provider = FakeProvider('{"trading_signal": "bad"}')

    with pytest.raises(InvariantViolationError):
        explain_macro(date(2026, 5, 12), pg_engine, provider)

    with pg_engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM explainability_cache")).scalar_one()
    assert count == 0
