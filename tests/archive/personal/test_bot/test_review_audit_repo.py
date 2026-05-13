from __future__ import annotations

import uuid
from pathlib import Path

from bot.task_store import (
    AuditQueueRecord,
    AuditQueueRepo,
    ReviewPacketRecord,
    ReviewPacketRepo,
    init_db,
)


def _db_path(tmp_path: Path) -> Path:
    db_path = tmp_path / "test_orchestrator.db"
    init_db(db_path)
    return db_path


def test_review_packet_create_get_and_list_by_parent(tmp_path: Path) -> None:
    repo = ReviewPacketRepo(_db_path(tmp_path))
    first_id = str(uuid.uuid4())
    second_id = str(uuid.uuid4())

    repo.create(
        ReviewPacketRecord(
            packet_id=first_id,
            parent_task_id="P11",
            workspace="report",
            created_by="codex_lead",
            summary="P11 리포트 구조 개편 1차 완료",
            snapshot_fingerprint="fp-1",
            created_at="2026-03-25T12:00:00+00:00",
        )
    )
    repo.create(
        ReviewPacketRecord(
            packet_id=second_id,
            parent_task_id="P11",
            workspace="report",
            created_by="codex_lead",
            summary="P11 append-only streaming까지 완료",
            snapshot_fingerprint="fp-2",
            created_at="2026-03-25T12:05:00+00:00",
        )
    )

    got = repo.get(second_id)
    assert got is not None
    assert got.snapshot_fingerprint == "fp-2"
    rows = repo.list_by_parent("P11")
    assert [row.packet_id for row in rows] == [first_id, second_id]


def test_audit_queue_enqueue_and_state_updates(tmp_path: Path) -> None:
    db_path = _db_path(tmp_path)
    packet_repo = ReviewPacketRepo(db_path)
    audit_repo = AuditQueueRepo(db_path)

    packet_id = str(uuid.uuid4())
    first_audit_id = str(uuid.uuid4())
    second_audit_id = str(uuid.uuid4())

    packet_repo.create(
        ReviewPacketRecord(
            packet_id=packet_id,
            parent_task_id="P12",
            workspace="development",
            created_by="codex_lead",
            summary="P12 control-plane schema 단계적 반영",
            snapshot_fingerprint="fp-p12-1",
        )
    )
    audit_repo.enqueue(
        AuditQueueRecord(
            audit_id=first_audit_id,
            parent_task_id="P12",
            packet_id=packet_id,
            workspace="development",
            changed_files='["src/bot/task_store.py"]',
            snapshot_fingerprint="fp-p12-1",
            created_at="2026-03-25T12:10:00+00:00",
            updated_at="2026-03-25T12:10:00+00:00",
        )
    )

    pending = audit_repo.list_pending()
    assert [row.audit_id for row in pending] == [first_audit_id]
    assert pending[0].changed_files == '["src/bot/task_store.py"]'

    audit_repo.mark_deferred_rate_limit(
        first_audit_id,
        next_retry_at="2026-03-26T04:00:00+00:00",
        rate_limit_until="2026-03-26T03:55:00+00:00",
    )
    deferred = audit_repo.get(first_audit_id)
    assert deferred is not None
    assert deferred.status == "deferred_rate_limit"
    assert deferred.defer_count == 1
    assert deferred.next_retry_at == "2026-03-26T04:00:00+00:00"

    audit_repo.enqueue(
        AuditQueueRecord(
            audit_id=second_audit_id,
            parent_task_id="P12",
            packet_id=packet_id,
            workspace="development",
            changed_files='["tests/test_bot/test_review_audit_repo.py"]',
            snapshot_fingerprint="fp-p12-2",
            created_at="2026-03-25T12:15:00+00:00",
            updated_at="2026-03-25T12:15:00+00:00",
        )
    )
    audit_repo.mark_superseded(first_audit_id, second_audit_id)
    superseded = audit_repo.get(first_audit_id)
    assert superseded is not None
    assert superseded.status == "superseded"
    assert superseded.superseded_by_audit_id == second_audit_id

    audit_repo.mark_reviewed(second_audit_id, "Claude 감리 완료")
    reviewed = audit_repo.get(second_audit_id)
    assert reviewed is not None
    assert reviewed.changed_files == '["tests/test_bot/test_review_audit_repo.py"]'
    assert reviewed.status == "reviewed"
    assert reviewed.review_summary == "Claude 감리 완료"
