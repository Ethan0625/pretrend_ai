from __future__ import annotations

import pytest
from sqlalchemy import Engine, create_engine, text

from pretrend.config import get_settings


@pytest.fixture(scope="module")
def pg_engine() -> Engine:
    try:
        database_url = get_settings().database_url
    except Exception as exc:
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
    except Exception as exc:
        pytest.skip(f"postgres unavailable for explainability tests: {exc}")
    if exists != "explainability_cache":
        pytest.skip("explainability_cache table is not migrated")
    yield engine
    engine.dispose()


@pytest.fixture()
def clean_cache(pg_engine: Engine) -> None:
    try:
        with pg_engine.begin() as conn:
            conn.execute(text("TRUNCATE explainability_cache"))
    except Exception as exc:
        pytest.skip(f"postgres unavailable for explainability tests: {exc}")
