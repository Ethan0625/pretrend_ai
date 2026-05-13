import sqlite3
import uuid
from pathlib import Path

import pytest

from bot.task_store import (
    ArtifactRefRecord,
    ArtifactRefRepo,
    DiscussionTopicRecord,
    DiscussionTopicRepo,
    GovernanceDecisionRecord,
    GovernanceDecisionRepo,
    init_db,
)


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "test_orchestrator.db"
    init_db(p)
    return p


def test_discussion_topic_create_get_and_close(db_path: Path) -> None:
    topic_repo = DiscussionTopicRepo(db_path)
    decision_repo = GovernanceDecisionRepo(db_path)

    topic_id = str(uuid.uuid4())
    decision_id = str(uuid.uuid4())

    topic_repo.open_topic(
        DiscussionTopicRecord(
            topic_id=topic_id,
            category="control_plane_state_policy",
            workspace="development",
            topic_summary="sessions와 summary의 workspace 식별축을 정한다",
            why_needed="development/report 문맥이 섞이면 정합성이 깨진다",
            opened_by="codex_lead",
        )
    )
    topic_repo.close_topic_with_decision(
        topic_id,
        GovernanceDecisionRecord(
            decision_id=decision_id,
            topic_id=topic_id,
            workspace="development",
            decision_summary="sessions와 conversation_summary는 workspace 축을 포함해 관리한다",
            decision_rationale="owner와 analyzer 문맥을 물리적으로 분리해야 한다",
            closed_by="codex_lead",
        ),
        artifacts=[
            ArtifactRefRecord(
                artifact_id=str(uuid.uuid4()),
                artifact_kind="task_doc",
                artifact_ref=".agent/task/CODEX_P15-7_governance_schema_migration.md",
                artifact_role="evidence",
                created_by="codex_lead",
                topic_id=topic_id,
            )
        ],
    )

    topic = topic_repo.get(topic_id)
    decision = decision_repo.get_active_decision(topic_id)

    assert topic is not None
    assert topic.status == "closed"
    assert topic.current_decision_id == decision_id
    assert decision is not None
    assert decision.decision_summary.startswith("sessions와 conversation_summary")


def test_governance_decision_allows_only_one_active_per_topic(db_path: Path) -> None:
    topic_repo = DiscussionTopicRepo(db_path)
    decision_repo = GovernanceDecisionRepo(db_path)
    topic_id = str(uuid.uuid4())

    topic_repo.open_topic(
        DiscussionTopicRecord(
            topic_id=topic_id,
            category="review_audit_policy",
            workspace="development",
            topic_summary="audit close 기준을 정한다",
            opened_by="codex_lead",
        )
    )
    decision_repo.create(
        GovernanceDecisionRecord(
            decision_id=str(uuid.uuid4()),
            topic_id=topic_id,
            workspace="development",
            decision_summary="close에는 decision artifact가 필요하다",
            closed_by="codex_lead",
        )
    )

    with pytest.raises(sqlite3.IntegrityError):
        decision_repo.create(
            GovernanceDecisionRecord(
                decision_id=str(uuid.uuid4()),
                topic_id=topic_id,
                workspace="development",
                decision_summary="두 번째 active decision은 허용되지 않는다",
                closed_by="claude_auditor",
            )
        )


def test_close_topic_requires_decision_artifact(db_path: Path) -> None:
    topic_repo = DiscussionTopicRepo(db_path)
    topic_id = str(uuid.uuid4())

    topic_repo.open_topic(
        DiscussionTopicRecord(
            topic_id=topic_id,
            category="control_plane_state_policy",
            workspace="development",
            topic_summary="close 최소 기준을 정한다",
            opened_by="codex_lead",
        )
    )

    with pytest.raises(ValueError):
        topic_repo.close_topic_with_decision(
            topic_id,
            GovernanceDecisionRecord(
                decision_id=str(uuid.uuid4()),
                topic_id=topic_id,
                workspace="development",
                decision_summary="artifact 없이 close하지 않는다",
                closed_by="codex_lead",
            ),
            artifacts=[],
        )


def test_artifact_ref_can_attach_to_topic_and_decision(db_path: Path) -> None:
    topic_repo = DiscussionTopicRepo(db_path)
    decision_repo = GovernanceDecisionRepo(db_path)
    artifact_repo = ArtifactRefRepo(db_path)

    topic_id = str(uuid.uuid4())
    decision_id = str(uuid.uuid4())
    topic_repo.open_topic(
        DiscussionTopicRecord(
            topic_id=topic_id,
            category="bot_operating_model",
            workspace="development",
            topic_summary="operating_lead streaming owner 경로를 정한다",
            opened_by="codex_lead",
        )
    )
    topic_repo.close_topic_with_decision(
        topic_id,
        GovernanceDecisionRecord(
            decision_id=decision_id,
            topic_id=topic_id,
            workspace="development",
            decision_summary="operating_lead 기본 응답은 Codex streaming으로 처리한다",
            closed_by="codex_lead",
        ),
        artifacts=[
            ArtifactRefRecord(
                artifact_id=str(uuid.uuid4()),
                topic_id=topic_id,
                artifact_kind="task_doc",
                artifact_ref=".agent/task/CODEX_P15-1_operating_lead_streaming.md",
                artifact_role="history",
                created_by="codex_lead",
            )
        ],
    )

    artifact_repo.attach_artifact(
        ArtifactRefRecord(
            artifact_id=str(uuid.uuid4()),
            topic_id=topic_id,
            artifact_kind="task_doc",
            artifact_ref=".agent/task/CODEX_P15-1_operating_lead_streaming.md",
            artifact_role="history",
            created_by="codex_lead",
        )
    )
    artifact_repo.attach_artifact(
        ArtifactRefRecord(
            artifact_id=str(uuid.uuid4()),
            topic_id=topic_id,
            decision_id=decision_id,
            artifact_kind="code_path",
            artifact_ref="scripts/telegram_claude_bot.py",
            artifact_role="implementation",
            created_by="codex_lead",
        )
    )

    topic_artifacts = artifact_repo.list_by_topic(topic_id)
    decision_artifacts = artifact_repo.list_by_decision(decision_id)

    assert len(topic_artifacts) == 3
    assert [row.artifact_role for row in decision_artifacts] == ["history", "implementation"]
    assert artifact_repo.has_decision_artifact(decision_id) is True


def test_reopen_and_supersede_preserve_topic_history(db_path: Path) -> None:
    topic_repo = DiscussionTopicRepo(db_path)
    decision_repo = GovernanceDecisionRepo(db_path)
    artifact_repo = ArtifactRefRepo(db_path)

    topic_id = str(uuid.uuid4())
    first_decision_id = str(uuid.uuid4())
    second_decision_id = str(uuid.uuid4())

    topic_repo.open_topic(
        DiscussionTopicRecord(
            topic_id=topic_id,
            category="review_audit_policy",
            workspace="development",
            topic_summary="close 근거에 어떤 artifact가 필요한지 정한다",
            opened_by="codex_lead",
        )
    )
    topic_repo.close_topic_with_decision(
        topic_id,
        GovernanceDecisionRecord(
            decision_id=first_decision_id,
            topic_id=topic_id,
            workspace="development",
            decision_summary="close에는 decision artifact가 1건 이상 필요하다",
            closed_by="codex_lead",
        ),
        artifacts=[
            ArtifactRefRecord(
                artifact_id=str(uuid.uuid4()),
                topic_id=topic_id,
                artifact_kind="contract_doc",
                artifact_ref="docs/architecture/governance_contract.md",
                artifact_role="evidence",
                created_by="codex_lead",
            )
        ],
    )

    topic_repo.reopen_topic(topic_id, "artifact 우선순위를 더 명확히 해야 한다")
    reopened = topic_repo.get(topic_id)
    assert reopened is not None
    assert reopened.status == "open"
    assert reopened.why_needed.startswith("artifact 우선순위")

    decision_repo.supersede_decision(
        first_decision_id,
        GovernanceDecisionRecord(
            decision_id=second_decision_id,
            topic_id=topic_id,
            workspace="development",
            decision_summary="close에는 decision에 직접 연결된 artifact가 1건 이상 필요하다",
            decision_rationale="topic-level artifact만으로는 닫힘 근거가 약하다",
            closed_by="claude_auditor",
        ),
        artifacts=[
            ArtifactRefRecord(
                artifact_id=str(uuid.uuid4()),
                artifact_kind="task_doc",
                artifact_ref=".agent/task/CODEX_P15-6_governance_ledger_model.md",
                artifact_role="evidence",
                created_by="claude_auditor",
            )
        ],
    )

    active = decision_repo.get_active_decision(topic_id)
    history = decision_repo.list_topic_history(topic_id)
    topic = topic_repo.get(topic_id)

    assert active is not None
    assert active.decision_id == second_decision_id
    assert [row.status for row in history] == ["superseded", "active"]
    assert topic is not None
    assert topic.status == "closed"
    assert topic.current_decision_id == second_decision_id
    assert artifact_repo.has_decision_artifact(second_decision_id) is True
