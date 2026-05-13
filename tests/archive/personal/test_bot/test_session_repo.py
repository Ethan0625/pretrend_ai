import sqlite3
from pathlib import Path

import pytest

from bot.task_store import SessionRecord, SessionRepo, init_db


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "test_orchestrator.db"
    init_db(p)
    return p


def test_init_db_creates_sessions_table(db_path: Path):
    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

    assert "sessions" in tables


def test_session_repo_upsert_and_get(db_path: Path):
    repo = SessionRepo(db_path)
    record = SessionRecord(
        role="classifier",
        provider="openai",
        session_id="sess_123",
        created_at="2026-03-23T00:00:00+00:00",
    )

    repo.upsert(record)
    fetched = repo.get("classifier")

    assert fetched is not None
    assert fetched.role == "classifier"
    assert fetched.provider == "openai"
    assert fetched.session_id == "sess_123"
    assert fetched.status == "active"
    assert fetched.last_used_at is None


def test_session_repo_upsert_replaces_existing_role(db_path: Path):
    repo = SessionRepo(db_path)
    repo.upsert(
        SessionRecord(
            role="leader",
            provider="anthropic",
            session_id="sess_old",
            created_at="2026-03-23T00:00:00+00:00",
            last_used_at="2026-03-23T00:10:00+00:00",
            status="active",
        )
    )

    repo.upsert(
        SessionRecord(
            role="leader",
            provider="anthropic",
            session_id="sess_new",
            created_at="2026-03-23T01:00:00+00:00",
            status="broken",
        )
    )

    fetched = repo.get("leader")
    assert fetched is not None
    assert fetched.session_id == "sess_new"
    assert fetched.created_at == "2026-03-23T01:00:00+00:00"
    assert fetched.status == "broken"
    assert fetched.last_used_at is None


def test_session_repo_touch_updates_last_used_at(db_path: Path):
    repo = SessionRepo(db_path)
    repo.upsert(
        SessionRecord(
            role="vice_leader",
            provider="openai",
            session_id="sess_vice",
            created_at="2026-03-23T00:00:00+00:00",
        )
    )

    repo.touch("vice_leader")

    fetched = repo.get("vice_leader")
    assert fetched is not None
    assert fetched.last_used_at is not None


def test_session_repo_set_status(db_path: Path):
    repo = SessionRepo(db_path)
    repo.upsert(
        SessionRecord(
            role="leader",
            provider="anthropic",
            session_id="sess_1",
            created_at="2026-03-23T00:00:00+00:00",
        )
    )

    repo.set_status("leader", "broken")

    fetched = repo.get("leader")
    assert fetched is not None
    assert fetched.status == "broken"
