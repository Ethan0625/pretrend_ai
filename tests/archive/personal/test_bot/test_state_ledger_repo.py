import uuid
from pathlib import Path

import pytest

from bot.task_store import (
    DecisionLedgerRepo,
    DecisionRecord,
    IssueLedgerRepo,
    IssueRecord,
    WorkingStateRecord,
    WorkingStateRepo,
    init_db,
)


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "test_orchestrator.db"
    init_db(p)
    return p


def test_working_state_upsert_and_get_by_workspace(db_path: Path) -> None:
    repo = WorkingStateRepo(db_path)

    repo.upsert(
        WorkingStateRecord(
            workspace="development",
            current_goal="P12-1 구현",
            active_parent_task="P12",
            active_leaf_task="P12-1",
            current_owner="codex_lead",
            confirmed_decisions='["role+workspace"]',
            next_action="테스트 실행",
        )
    )
    repo.upsert(
        WorkingStateRecord(
            workspace="report",
            current_goal="report analyzer memory 정리",
            current_owner="analyzer",
        )
    )

    development = repo.get("development")
    report = repo.get("report")

    assert development is not None
    assert development.active_leaf_task == "P12-1"
    assert development.current_owner == "codex_lead"
    assert report is not None
    assert report.current_goal == "report analyzer memory 정리"


def test_decision_ledger_create_list_and_supersede(db_path: Path) -> None:
    repo = DecisionLedgerRepo(db_path)
    old_id = str(uuid.uuid4())
    new_id = str(uuid.uuid4())

    repo.create(
        DecisionRecord(
            decision_id=old_id,
            workspace="both",
            topic="session_metadata_axis",
            decision_summary="session metadata는 role+workspace로 해석한다",
            rationale="report와 development 문맥을 분리해야 한다",
            created_by="user",
        )
    )

    active = repo.list_active("both")
    assert [row.decision_id for row in active] == [old_id]

    repo.supersede(
        old_id,
        DecisionRecord(
            decision_id=new_id,
            workspace="both",
            topic="session_metadata_axis",
            decision_summary="role+workspace 해석은 유지하되 물리 정규화는 P12로 미룬다",
            rationale="P11은 transitional design만 수행한다",
            created_by="codex_lead",
        ),
    )

    old_row = repo.get(old_id)
    new_row = repo.get(new_id)
    active = repo.list_active("both")

    assert old_row is not None and old_row.status == "superseded"
    assert new_row is not None and new_row.supersedes_id == old_id
    assert [row.decision_id for row in active] == [new_id]


def test_issue_ledger_create_list_resolve_and_supersede(db_path: Path) -> None:
    repo = IssueLedgerRepo(db_path)
    issue_id = str(uuid.uuid4())
    replacement_id = str(uuid.uuid4())

    repo.create(
        IssueRecord(
            issue_id=issue_id,
            workspace="development",
            topic="team_lead_streaming",
            issue_summary="team lead bot append-only streaming 경계 재정의 필요",
            context="P11-4 해석 수정",
            opened_by="user",
        )
    )

    open_rows = repo.list_open("development")
    assert [row.issue_id for row in open_rows] == [issue_id]

    repo.resolve(issue_id, "P11-4 문서와 구현을 append-only streaming으로 정리")
    resolved = repo.get(issue_id)
    assert resolved is not None
    assert resolved.status == "resolved"
    assert resolved.resolution_summary.startswith("P11-4")
    assert resolved.resolved_at is not None

    repo.create(
        IssueRecord(
            issue_id=str(uuid.uuid4()),
            workspace="report",
            topic="report_memory",
            issue_summary="report workspace working_state 필요",
            opened_by="codex_lead",
        )
    )
    stale_id = str(uuid.uuid4())
    repo.create(
        IssueRecord(
            issue_id=stale_id,
            workspace="report",
            topic="report_memory",
            issue_summary="임시 report memory를 conversation_summary로 재사용",
            opened_by="codex_lead",
        )
    )
    repo.supersede(
        stale_id,
        IssueRecord(
            issue_id=replacement_id,
            workspace="report",
            topic="report_memory",
            issue_summary="working_state(workspace=report) 도입 후 migration 필요",
            opened_by="codex_lead",
        ),
    )

    stale = repo.get(stale_id)
    replacement = repo.get(replacement_id)
    assert stale is not None and stale.status == "superseded"
    assert stale.superseded_by_id == replacement_id
    assert replacement is not None and replacement.status == "open"
