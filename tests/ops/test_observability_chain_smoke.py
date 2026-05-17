from __future__ import annotations

import json
from datetime import date
from typing import Any

import pandas as pd
import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError


pytestmark = [pytest.mark.db, pytest.mark.slow, pytest.mark.invariant]

REQUIRED_TABLES = {
    "gold_market_state_similarity_feature",
    "similarity_regime",
    "explainability_cache",
}


class FakeSimilarityProvider:
    model_id = "mock_ofs_202"

    def __init__(self) -> None:
        self.calls = 0
        self.prompts: list[str] = []

    def health_check(self, *, timeout_s: int = 10) -> bool:
        return True

    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        timeout_s: int,
    ) -> str:
        self.calls += 1
        self.prompts.append(user_prompt)
        return json.dumps(
            {
                "query_date": "2026-03-01",
                "view": "regime",
                "summary": "합성 regime 이력에서 유사한 과거 구간을 관측했습니다.",
                "neighbors": [
                    {
                        "neighbor_date": "2026-01-20",
                        "score": 0.95,
                        "rank": 1,
                        "match_reasons": ["synthetic regime overlap"],
                    }
                ],
                "disclaimer": "관측 설명이며 예측이나 매매 판단이 아닙니다.",
            },
            ensure_ascii=False,
        )


@pytest.fixture(scope="module")
def pg_engine() -> Engine:
    try:
        from pretrend.config import get_settings

        database_url = get_settings().database_url
    except Exception as exc:
        pytest.skip(f"postgres settings unavailable for OFS-202 smoke: {exc}")

    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = ANY(:tables)
                    """
                ),
                {"tables": sorted(REQUIRED_TABLES)},
            ).scalars()
            existing = set(rows)
    except SQLAlchemyError as exc:
        pytest.skip(f"postgres unavailable for OFS-202 smoke: {exc}")

    missing = REQUIRED_TABLES - existing
    if missing:
        pytest.skip(f"OFS-202 tables are not migrated: {sorted(missing)}")
    return engine


@pytest.fixture()
def clean_observability_chain_tables(pg_engine: Engine) -> None:
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE explainability_cache"))
        conn.execute(text("TRUNCATE similarity_regime"))
        conn.execute(text("TRUNCATE gold_market_state_similarity_feature"))


def test_ofs_202_similarity_to_explainability_chain_smoke(
    pg_engine: Engine,
    clean_observability_chain_tables: None,
) -> None:
    """OFS-202: similarity features, similarity rows, and explainability cache stay connected."""

    from pretrend.observability.explainability.similarity_explainer import explain_similarity
    from pretrend.observability.similarity.builder import build_similarity_regime
    from pretrend.observability.similarity.producer import build_market_state_similarity_features

    query_date = date(2026, 3, 1)
    producer_result = build_market_state_similarity_features(
        date(2026, 1, 1),
        query_date,
        engine=pg_engine,
        market_state_df=_market_state_rows(),
        rotation_df=_rotation_rows(),
    )
    similarity_result = build_similarity_regime(query_date, query_date, pg_engine)
    provider = FakeSimilarityProvider()
    report = explain_similarity(query_date, "regime", pg_engine, provider, force_refresh=True)

    assert producer_result["rows_upserted"] == 3
    assert similarity_result["query_count"] == 1
    assert similarity_result["rows_upserted"] >= 1
    assert report.query_date == query_date
    assert report.neighbors
    assert provider.calls == 1
    assert '"neighbors"' in provider.prompts[0]

    with pg_engine.connect() as conn:
        counts = conn.execute(
            text(
                """
                SELECT
                  (SELECT COUNT(*) FROM gold_market_state_similarity_feature),
                  (SELECT COUNT(*) FROM similarity_regime WHERE query_date = :query_date),
                  (SELECT COUNT(*) FROM explainability_cache
                   WHERE use_case = 'similarity_regime'
                     AND query_date = :query_date
                     AND model_id = :model_id)
                """
            ),
            {"query_date": query_date, "model_id": provider.model_id},
        ).one()
    assert tuple(counts) == (3, similarity_result["rows_upserted"], 1)


def _market_state_rows() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for idx, trade_date in enumerate(
        [date(2026, 1, 1), date(2026, 1, 20), date(2026, 3, 1)]
    ):
        rows.append(
            {
                "trade_date": trade_date,
                "long_phase": ["RECOVERY", "EXPANSION", "RECOVERY"][idx],
                "mid_regime": ["RISK_ON", "NEUTRAL", "RISK_ON"][idx],
                "short_signal": ["RELIEF", "STABLE", "RELIEF"][idx],
                "long_phase_confidence": 0.7 + idx * 0.05,
                "mid_regime_confidence": 0.6 + idx * 0.05,
                "short_signal_confidence": 0.5 + idx * 0.05,
                "run_universe": True,
                "risk_gate": idx != 1,
                "state_age_days": 5 + idx,
                "sojourn_prob_5d": 0.8 - idx * 0.05,
                "sojourn_prob_10d": 0.7 - idx * 0.05,
                "sojourn_prob_20d": 0.6 - idx * 0.05,
                "sojourn_prob_60d": 0.5 - idx * 0.05,
                "sojourn_prob_120d": 0.4 - idx * 0.05,
                "transition_hazard_5d": 0.1 + idx * 0.02,
                "transition_hazard_10d": 0.2 + idx * 0.02,
                "transition_hazard_20d": 0.3 + idx * 0.02,
                "transition_hazard_60d": 0.4 + idx * 0.02,
                "transition_hazard_120d": 0.5 + idx * 0.02,
            }
        )
    return pd.DataFrame(rows)


def _rotation_rows() -> pd.DataFrame:
    rows = []
    for trade_date in [date(2026, 1, 1), date(2026, 1, 20), date(2026, 3, 1)]:
        rows.extend(
            [
                {
                    "trade_date": trade_date,
                    "asset_group": "SECTOR",
                    "asset_name": "ENERGY",
                    "group_state_now": "STRONG",
                },
                {
                    "trade_date": trade_date,
                    "asset_group": "SECTOR",
                    "asset_name": "HEALTH_CARE",
                    "group_state_now": "WEAK",
                },
            ]
        )
    return pd.DataFrame(rows)
