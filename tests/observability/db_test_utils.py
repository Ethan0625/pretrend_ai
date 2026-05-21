from __future__ import annotations

import os
import re
from pathlib import Path
from collections.abc import Iterable

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError


SAFE_TEST_DATABASE_RE = re.compile(r"^pretrend_test[A-Za-z0-9_]*$")


def isolated_test_engine(required_tables: Iterable[str] = ()) -> Engine:
    database_url = _test_database_url()
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            if required_tables:
                rows = conn.execute(
                    text(
                        """
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = ANY(:tables)
                        """
                    ),
                    {"tables": sorted(required_tables)},
                ).scalars()
                existing = set(rows)
    except SQLAlchemyError as exc:
        pytest.skip(f"isolated test postgres unavailable: {exc}")

    missing = set(required_tables) - existing if required_tables else set()
    if missing:
        pytest.fail(f"isolated test DB tables are not migrated: {sorted(missing)}")
    return engine


def _test_database_url() -> str:
    raw_url = os.getenv("PRETREND_TEST_DATABASE_URL") or _dotenv_value(
        "PRETREND_TEST_DATABASE_URL"
    )
    if not raw_url:
        pytest.skip("set PRETREND_TEST_DATABASE_URL to an isolated migrated test DB")

    url = make_url(raw_url)
    database_name = url.database or ""
    if not SAFE_TEST_DATABASE_RE.match(database_name):
        pytest.fail(
            "PRETREND_TEST_DATABASE_URL must point to an isolated test DB "
            f"named pretrend_test*, got {database_name!r}"
        )
    return raw_url


def _dotenv_value(key: str) -> str | None:
    env_path = Path(".env")
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        current_key, value = raw.split("=", 1)
        if current_key.strip() == key:
            return value.strip().strip("'\"")
    return None
