import sqlite3
from pathlib import Path

import pytest

from bot.task_store import (
    ConversationRepo,
    ConversationSummaryRecord,
    init_db,
)


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "test_orchestrator.db"
    init_db(p)
    return p


def test_init_db_creates_conversation_tables(db_path: Path):
    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }

    assert "conversation_log" in tables
    assert "conversation_summary" in tables
    assert "idx_convlog_created" in indexes


def test_conversation_repo_append_log_and_recent_logs(db_path: Path):
    repo = ConversationRepo(db_path)

    repo.append_log("user", "첫 번째")
    repo.append_log("leader", "두 번째")
    repo.append_log("vice_leader", "세 번째")

    logs = repo.recent_logs(limit=2)

    assert [log.content for log in logs] == ["두 번째", "세 번째"]
    assert [log.role for log in logs] == ["leader", "vice_leader"]
    assert all(log.id is not None for log in logs)


def test_conversation_repo_recent_logs_returns_chronological_order(db_path: Path):
    repo = ConversationRepo(db_path)

    for idx in range(5):
        repo.append_log("user", f"msg-{idx}")

    logs = repo.recent_logs(limit=3)

    assert [log.content for log in logs] == ["msg-2", "msg-3", "msg-4"]


def test_conversation_repo_upsert_summary_and_get_summary(db_path: Path):
    repo = ConversationRepo(db_path)
    record = ConversationSummaryRecord(
        role="leader",
        summary="현재 대화 요약",
        anchors='[".agent/task/P10-1_session_db.md"]',
        created_at="2026-03-23T00:00:00+00:00",
        updated_at="2026-03-23T00:00:00+00:00",
    )

    repo.upsert_summary(record)
    fetched = repo.get_summary()

    assert fetched is not None
    assert fetched.role == "leader"
    assert fetched.summary == "현재 대화 요약"
    assert fetched.anchors == '[".agent/task/P10-1_session_db.md"]'


def test_conversation_repo_upsert_summary_replaces_by_role(db_path: Path):
    repo = ConversationRepo(db_path)
    repo.upsert_summary(
        ConversationSummaryRecord(
            role="leader",
            summary="old",
            anchors="[]",
            created_at="2026-03-23T00:00:00+00:00",
            updated_at="2026-03-23T00:00:00+00:00",
        )
    )
    repo.upsert_summary(
        ConversationSummaryRecord(
            role="leader",
            summary="new",
            anchors='["docs/anchor.md"]',
            created_at="2026-03-23T01:00:00+00:00",
            updated_at="2026-03-23T01:00:00+00:00",
        )
    )

    fetched = repo.get_summary("leader")
    assert fetched is not None
    assert fetched.summary == "new"
    assert fetched.anchors == '["docs/anchor.md"]'
    assert fetched.created_at == "2026-03-23T01:00:00+00:00"


def test_conversation_repo_get_summary_returns_none_when_missing(db_path: Path):
    repo = ConversationRepo(db_path)

    assert repo.get_summary("leader") is None
