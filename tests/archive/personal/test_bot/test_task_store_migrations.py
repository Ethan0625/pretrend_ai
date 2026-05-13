import sqlite3
from pathlib import Path

from bot.task_store import ConversationRepo, SessionRepo, TaskStatusRepo, init_db


def test_init_db_normalizes_legacy_identity_and_task_status(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy_orchestrator.db"

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE sessions (
                role TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                session_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_used_at TEXT,
                status TEXT NOT NULL DEFAULT 'active'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO sessions (role, provider, session_id, created_at, last_used_at, status)
            VALUES ('analyzer', 'openai_codex', 'sess-an', '2026-03-27T00:00:00+00:00', NULL, 'active')
            """
        )
        conn.execute(
            """
            CREATE TABLE conversation_summary (
                role TEXT PRIMARY KEY,
                summary TEXT NOT NULL,
                anchors TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO conversation_summary (role, summary, anchors, created_at, updated_at)
            VALUES ('analyzer', 'summary', '[]', '2026-03-27T00:00:00+00:00', '2026-03-27T00:00:00+00:00')
            """
        )
        conn.execute(
            """
            CREATE TABLE task_status (
                task_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO task_status (task_id, title, status, updated_at)
            VALUES ('P11', 'legacy row', 'DONE', '2026-03-27T00:00:00+00:00')
            """
        )
        conn.commit()

    init_db(db_path)

    session = SessionRepo(db_path).get("analyzer", workspace="report")
    assert session is not None
    assert session.workspace == "report"

    summary = ConversationRepo(db_path).get_summary("analyzer", workspace="report")
    assert summary is not None
    assert summary.workspace == "report"

    rows = {row.task_id: row for row in TaskStatusRepo(db_path).list_all()}
    assert rows["P11"].status_source == "legacy_unknown"


def test_init_db_backfills_governance_from_legacy_ledgers_idempotently(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy_governance.db"

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE decision_ledger (
                decision_id TEXT PRIMARY KEY,
                workspace TEXT NOT NULL,
                topic TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                decision_summary TEXT NOT NULL,
                rationale TEXT NOT NULL DEFAULT '',
                source_kind TEXT NOT NULL DEFAULT 'discussion',
                source_ref TEXT NOT NULL DEFAULT '',
                supersedes_id TEXT,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE issue_ledger (
                issue_id TEXT PRIMARY KEY,
                workspace TEXT NOT NULL,
                topic TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                issue_summary TEXT NOT NULL,
                context TEXT NOT NULL DEFAULT '',
                source_kind TEXT NOT NULL DEFAULT 'discussion',
                source_ref TEXT NOT NULL DEFAULT '',
                opened_by TEXT NOT NULL,
                resolution_summary TEXT NOT NULL DEFAULT '',
                resolved_at TEXT,
                superseded_by_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO decision_ledger (
                decision_id, workspace, topic, status, decision_summary,
                rationale, source_kind, source_ref, supersedes_id,
                created_by, created_at, updated_at
            ) VALUES (
                'dec-1', 'development', 'owner.execution_path', 'active',
                'operating_lead는 Codex로 유지한다',
                'owner identity 정합성 유지',
                'discussion', 'NO_MATCH_DECISION', NULL,
                'codex_lead', '2026-03-27T00:00:00+00:00', '2026-03-27T00:00:00+00:00'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO issue_ledger (
                issue_id, workspace, topic, status, issue_summary, context,
                source_kind, source_ref, opened_by, resolution_summary,
                resolved_at, superseded_by_id, created_at, updated_at
            ) VALUES (
                'iss-1', 'development', 'task_status.provenance', 'open',
                'task_status provenance 물리 필드 필요',
                'runtime과 backfill 구분이 안 됨',
                'discussion', 'NO_MATCH_ISSUE', 'codex_lead', '',
                NULL, NULL, '2026-03-27T00:00:00+00:00', '2026-03-27T00:00:00+00:00'
            )
            """
        )
        conn.commit()

    init_db(db_path)
    init_db(db_path)

    with sqlite3.connect(db_path) as conn:
        topic_count = conn.execute("SELECT COUNT(*) FROM discussion_topic").fetchone()[0]
        decision_count = conn.execute("SELECT COUNT(*) FROM decision").fetchone()[0]
        artifact_count = conn.execute("SELECT COUNT(*) FROM artifact_ref").fetchone()[0]

    assert topic_count == 2
    assert decision_count == 1
    assert artifact_count == 2
