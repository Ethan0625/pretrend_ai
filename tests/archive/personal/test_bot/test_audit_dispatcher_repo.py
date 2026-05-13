from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from bot.task_store import AuditQueueRecord, AuditQueueRepo, ReviewPacketRecord, ReviewPacketRepo, init_db


def _db_path(tmp_path: Path) -> Path:
    db_path = tmp_path / "test_orchestrator.db"
    init_db(db_path)
    return db_path


def _seed_packet(packet_repo: ReviewPacketRepo, packet_id: str, parent_task_id: str = "P12") -> None:
    packet_repo.create(
        ReviewPacketRecord(
            packet_id=packet_id,
            parent_task_id=parent_task_id,
            workspace="development",
            created_by="codex_lead",
            summary="audit packet",
            snapshot_fingerprint=f"fp-{packet_id}",
        )
    )


def test_audit_queue_acquire_next_ready_oldest_first_and_retry_gate(tmp_path: Path) -> None:
    db_path = _db_path(tmp_path)
    packet_repo = ReviewPacketRepo(db_path)
    audit_repo = AuditQueueRepo(db_path)

    old_packet = str(uuid.uuid4())
    new_packet = str(uuid.uuid4())
    _seed_packet(packet_repo, old_packet)
    _seed_packet(packet_repo, new_packet)

    old_audit = str(uuid.uuid4())
    new_audit = str(uuid.uuid4())
    audit_repo.enqueue(
        AuditQueueRecord(
            audit_id=old_audit,
            parent_task_id="P12",
            packet_id=old_packet,
            workspace="development",
            changed_files='["old.py"]',
            snapshot_fingerprint="fp-old",
            status="deferred_rate_limit",
            next_retry_at="2026-03-25T09:00:00+00:00",
            created_at="2026-03-25T08:00:00+00:00",
            updated_at="2026-03-25T08:00:00+00:00",
        )
    )
    audit_repo.enqueue(
        AuditQueueRecord(
            audit_id=new_audit,
            parent_task_id="P12",
            packet_id=new_packet,
            workspace="development",
            changed_files='["new.py"]',
            snapshot_fingerprint="fp-new",
            status="queued",
            created_at="2026-03-25T08:30:00+00:00",
            updated_at="2026-03-25T08:30:00+00:00",
        )
    )

    got = audit_repo.acquire_next_ready(
        "worker-a",
        lease_until="2026-03-25T09:30:00+00:00",
        now="2026-03-25T09:05:00+00:00",
    )
    assert got is not None
    assert got.audit_id == old_audit
    assert got.status == "running"
    assert got.retry_count == 1
    assert got.lease_owner == "worker-a"


def test_audit_queue_lease_blocks_second_acquire_until_expired(tmp_path: Path) -> None:
    db_path = _db_path(tmp_path)
    packet_repo = ReviewPacketRepo(db_path)
    audit_repo = AuditQueueRepo(db_path)

    packet_id = str(uuid.uuid4())
    _seed_packet(packet_repo, packet_id)
    audit_id = str(uuid.uuid4())
    audit_repo.enqueue(
        AuditQueueRecord(
            audit_id=audit_id,
            parent_task_id="P12",
            packet_id=packet_id,
            workspace="development",
            changed_files='["lease.py"]',
            snapshot_fingerprint="fp-lease",
            created_at="2026-03-25T10:00:00+00:00",
            updated_at="2026-03-25T10:00:00+00:00",
        )
    )

    first = audit_repo.acquire_next_ready(
        "worker-a",
        lease_until="2026-03-25T10:30:00+00:00",
        now="2026-03-25T10:05:00+00:00",
    )
    assert first is not None
    second = audit_repo.acquire_next_ready(
        "worker-b",
        lease_until="2026-03-25T10:40:00+00:00",
        now="2026-03-25T10:10:00+00:00",
    )
    assert second is None

    expired_retry = audit_repo.acquire_next_ready(
        "worker-b",
        lease_until="2026-03-25T11:00:00+00:00",
        now="2026-03-25T10:31:00+00:00",
    )
    assert expired_retry is None

    audit_repo.mark_deferred_rate_limit(
        audit_id,
        next_retry_at="2026-03-25T10:45:00+00:00",
        rate_limit_until="2026-03-25T10:40:00+00:00",
    )
    deferred = audit_repo.acquire_next_ready(
        "worker-b",
        lease_until="2026-03-25T11:05:00+00:00",
        now="2026-03-25T10:50:00+00:00",
    )
    assert deferred is not None
    assert deferred.audit_id == audit_id
    assert deferred.retry_count == 2


def test_audit_queue_mark_failed_and_migrate_lease_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy_audit.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE tasks (
            task_id TEXT PRIMARY KEY,
            parent_task_id TEXT,
            origin_task_id TEXT,
            chat_id INTEGER NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL,
            intent TEXT NOT NULL DEFAULT 'RUN_CODEX',
            executor_type TEXT NOT NULL DEFAULT 'codex',
            status TEXT NOT NULL DEFAULT 'queued',
            branch TEXT NOT NULL DEFAULT '',
            worktree_path TEXT NOT NULL DEFAULT '',
            checkpoint_path TEXT NOT NULL DEFAULT '',
            result_summary TEXT NOT NULL DEFAULT '',
            review_summary TEXT NOT NULL DEFAULT '',
            retry_count INTEGER NOT NULL DEFAULT 0,
            cooldown_until TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            finished_at TEXT
        );
        CREATE TABLE review_packet (
            packet_id TEXT PRIMARY KEY,
            parent_task_id TEXT NOT NULL,
            workspace TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            changed_files TEXT NOT NULL DEFAULT '[]',
            test_results TEXT NOT NULL DEFAULT '[]',
            key_decisions TEXT NOT NULL DEFAULT '[]',
            open_issues TEXT NOT NULL DEFAULT '[]',
            recommended_next_action TEXT NOT NULL DEFAULT '',
            snapshot_fingerprint TEXT NOT NULL DEFAULT '',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE audit_queue (
            audit_id TEXT PRIMARY KEY,
            parent_task_id TEXT NOT NULL,
            packet_id TEXT NOT NULL REFERENCES review_packet(packet_id),
            workspace TEXT NOT NULL,
            changed_files TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'queued',
            snapshot_fingerprint TEXT NOT NULL DEFAULT '',
            retry_count INTEGER NOT NULL DEFAULT 0,
            defer_count INTEGER NOT NULL DEFAULT 0,
            last_attempt_at TEXT,
            next_retry_at TEXT,
            rate_limit_until TEXT,
            last_error_code TEXT NOT NULL DEFAULT '',
            review_summary TEXT NOT NULL DEFAULT '',
            superseded_by_audit_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()

    init_db(db_path)

    conn = sqlite3.connect(db_path)
    cols = {
        row[1]
        for row in conn.execute("PRAGMA table_info(audit_queue)").fetchall()
    }
    conn.close()
    assert "changed_files" in cols
    assert "lease_owner" in cols
    assert "lease_until" in cols

    packet_repo = ReviewPacketRepo(db_path)
    audit_repo = AuditQueueRepo(db_path)
    packet_id = str(uuid.uuid4())
    _seed_packet(packet_repo, packet_id)
    audit_id = str(uuid.uuid4())
    audit_repo.enqueue(
        AuditQueueRecord(
            audit_id=audit_id,
            parent_task_id="P12",
            packet_id=packet_id,
            workspace="development",
            changed_files='["src/bot/task_store.py"]',
            snapshot_fingerprint="fp-failed",
        )
    )
    running = audit_repo.acquire_next_ready(
        "worker-a",
        lease_until="2026-03-25T12:30:00+00:00",
        now="2026-03-25T12:00:00+00:00",
    )
    assert running is not None
    audit_repo.mark_failed(audit_id, "CLAUDE_EXEC_ERROR", now="2026-03-25T12:01:00+00:00")
    failed = audit_repo.get(audit_id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.last_error_code == "CLAUDE_EXEC_ERROR"
    assert failed.lease_owner is None
    assert failed.lease_until is None
