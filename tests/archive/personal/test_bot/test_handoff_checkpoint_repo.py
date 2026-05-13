from __future__ import annotations

import uuid
from pathlib import Path

from bot.task_store import (
    CheckpointSummaryRecord,
    CheckpointSummaryRepo,
    HandoffSummaryRecord,
    HandoffSummaryRepo,
    init_db,
)


def _db_path(tmp_path: Path) -> Path:
    db_path = tmp_path / "test_orchestrator.db"
    init_db(db_path)
    return db_path


def test_handoff_summary_create_and_list_recent(tmp_path: Path) -> None:
    repo = HandoffSummaryRepo(_db_path(tmp_path))
    first_id = str(uuid.uuid4())
    second_id = str(uuid.uuid4())

    repo.create(
        HandoffSummaryRecord(
            handoff_id=first_id,
            workspace="development",
            from_owner="claude_lead",
            to_owner="codex_lead",
            trigger_kind="rate_limit",
            window_start_log_id=10,
            window_end_log_id=20,
            delta_decisions='["codex를 운영 owner로 사용"]',
            summary_text="Claude rate limit로 Codex lead에 운영 owner handoff",
            created_at="2026-03-25T10:00:00+00:00",
        )
    )
    repo.create(
        HandoffSummaryRecord(
            handoff_id=second_id,
            workspace="report",
            from_owner="provider_direct",
            to_owner="analyzer",
            trigger_kind="owner_transition",
            window_start_log_id=21,
            window_end_log_id=32,
            delta_next_action="analyzer-first 경로 유지",
            summary_text="P11-2 report analyzer owner 전환",
            created_at="2026-03-25T10:05:00+00:00",
        )
    )

    dev_rows = repo.list_recent("development")
    assert [row.handoff_id for row in dev_rows] == [first_id]
    all_rows = repo.list_recent(limit=5)
    assert [row.handoff_id for row in all_rows] == [second_id, first_id]


def test_checkpoint_summary_create_and_list_recent(tmp_path: Path) -> None:
    repo = CheckpointSummaryRepo(_db_path(tmp_path))
    first_id = str(uuid.uuid4())
    second_id = str(uuid.uuid4())

    repo.create(
        CheckpointSummaryRecord(
            checkpoint_id=first_id,
            workspace="report",
            topic="report_structure",
            checkpoint_kind="exploration",
            window_start_log_id=100,
            window_end_log_id=120,
            confirmed_points='["3섹션 구조 유지"]',
            open_questions='["AI 해석 길이 제한"]',
            next_question="macro feature raw 값 노출 기준",
            summary_text="P11-1 탐색 checkpoint",
            created_at="2026-03-25T11:00:00+00:00",
        )
    )
    repo.create(
        CheckpointSummaryRecord(
            checkpoint_id=second_id,
            workspace="development",
            topic="audit_queue",
            checkpoint_kind="handoff_prep",
            window_start_log_id=121,
            window_end_log_id=150,
            confirmed_points='["deferred_rate_limit 필요"]',
            rejected_points='["git_head 단독 stale 판정"]',
            summary_text="P12 감리 큐 탐색 checkpoint",
            created_at="2026-03-25T11:10:00+00:00",
        )
    )

    report_rows = repo.list_recent("report")
    assert [row.checkpoint_id for row in report_rows] == [first_id]
    all_rows = repo.list_recent(limit=5)
    assert [row.checkpoint_id for row in all_rows] == [second_id, first_id]
