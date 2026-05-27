from __future__ import annotations

import pytest
from sqlalchemy import Engine, text

from tests.observability.db_test_utils import isolated_test_engine


@pytest.fixture(scope="module")
def pg_engine() -> Engine:
    return isolated_test_engine({"explainability_cache", "gold_market_state_similarity_feature"})


@pytest.fixture()
def clean_cache(pg_engine: Engine) -> None:
    try:
        with pg_engine.begin() as conn:
            conn.execute(text("TRUNCATE explainability_cache"))
    except Exception as exc:
        pytest.skip(f"postgres unavailable for explainability tests: {exc}")
