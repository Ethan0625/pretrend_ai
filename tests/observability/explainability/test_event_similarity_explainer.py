from __future__ import annotations

import json
from datetime import date, datetime, timezone

from sqlalchemy import Engine, text

from pretrend.observability.explainability.cache import store
from pretrend.observability.explainability.event_similarity_explainer import (
    PROMPT_VERSION,
    USE_CASE,
    explain_similarity_events,
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
        "summary": "현재 관측 상태는 일부 역사 이벤트와 유사한 변동성 조건을 보입니다.",
        "events": [
            {
                "event_name": "리먼 파산",
                "anchor_date": "2008-09-15",
                "actual_date": "2008-09-15",
                "similarity_score": 0.81,
                "match_reasons": ["전환 위험과 단기 신호가 함께 높아진 관측 구간입니다."],
            }
        ],
        "disclaimer": "본 결과는 과거 유사성 관측이며 예측이 아닙니다.",
    }


def test_explain_similarity_events_cache_hit(pg_engine: Engine, clean_cache: None) -> None:
    store(pg_engine, USE_CASE, date(2026, 5, 12), "mock", PROMPT_VERSION, _report())
    provider = FakeProvider(_report())

    report = explain_similarity_events(date(2026, 5, 12), pg_engine, provider)

    assert report.events[0].event_name == "리먼 파산"
    assert provider.calls == 0


def test_explain_similarity_events_cache_miss_calls_provider(
    pg_engine: Engine,
    clean_cache: None,
) -> None:
    _upsert_feature(pg_engine, date(2008, 9, 15), short_signal_code=-1, transition_hazard_10d=0.8)
    _upsert_feature(pg_engine, date(2026, 5, 12), short_signal_code=-1, transition_hazard_10d=0.75)
    provider = FakeProvider(_report())

    report = explain_similarity_events(date(2026, 5, 12), pg_engine, provider)

    assert report.summary
    assert provider.calls == 1
    with pg_engine.connect() as conn:
        count = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM explainability_cache
                WHERE use_case = 'similarity_events'
                  AND query_date = '2026-05-12'
                """
            )
        ).scalar_one()
    assert count == 1


def _upsert_feature(
    engine: Engine,
    trade_date: date,
    *,
    short_signal_code: int,
    transition_hazard_10d: float,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO gold_market_state_similarity_feature
                  (trade_date, short_signal_code, transition_hazard_10d, built_at)
                VALUES
                  (:trade_date, :short_signal_code, :transition_hazard_10d, :built_at)
                ON CONFLICT (trade_date)
                DO UPDATE SET
                  short_signal_code = EXCLUDED.short_signal_code,
                  transition_hazard_10d = EXCLUDED.transition_hazard_10d,
                  built_at = EXCLUDED.built_at
                """
            ),
            {
                "trade_date": trade_date,
                "short_signal_code": short_signal_code,
                "transition_hazard_10d": transition_hazard_10d,
                "built_at": datetime(2026, 5, 12, tzinfo=timezone.utc),
            },
        )
