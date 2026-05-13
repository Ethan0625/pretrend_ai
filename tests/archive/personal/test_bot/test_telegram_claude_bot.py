"""Tests for scripts/telegram_claude_bot.py task-status sync and cooldown bypass."""
from __future__ import annotations

import importlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from bot.task_store import (
    ApprovalRepo,
    ArtifactRefRepo,
    AuditQueueRepo,
    ConversationRepo,
    ConversationSummaryRecord,
    DecisionLedgerRepo,
    DiscussionTopicRecord,
    DiscussionTopicRepo,
    EventRepo,
    GovernanceDecisionRecord,
    GovernanceDecisionRepo,
    IssueLedgerRepo,
    ReviewPacketRecord,
    ReviewPacketRepo,
    SessionRecord,
    SessionRepo,
    TaskRepo,
    TaskRecord,
    TaskStatusRepo,
    WorkingStateRecord,
    WorkingStateRepo,
    init_db,
)


def _load_bot_module(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    fake_claude = fake_home / ".vscode-server" / "extensions" / "anthropic.claude-code-test" / "resources" / "native-binary" / "claude"
    fake_claude.parent.mkdir(parents=True, exist_ok=True)
    fake_claude.write_text("")

    db_path = tmp_path / "orchestrator.db"
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_DEV_CHAT_ID", "1")
    monkeypatch.setenv("ORCHESTRATOR_DB_PATH", str(db_path))

    sys.modules.pop("telegram_claude_bot", None)
    return importlib.import_module("telegram_claude_bot"), db_path


def test_cooldown_bypass_targets_are_explicit(monkeypatch, tmp_path):
    bot_module, _ = _load_bot_module(monkeypatch, tmp_path)

    assert bot_module._cooldown_bypass_message("/task_status") is True
    assert bot_module._cooldown_bypass_message("/codex_status") is True
    assert bot_module._cooldown_bypass_message("/approve abcd1234") is True
    assert bot_module._cooldown_bypass_message("/help") is False

    assert bot_module._cooldown_bypass_callback_data("dispatch_confirm:abc") is True
    assert bot_module._cooldown_bypass_callback_data("dispatch_cancel:abc") is True
    assert bot_module._cooldown_bypass_callback_data("approve:abc:def") is True
    assert bot_module._cooldown_bypass_callback_data("reject:abc:def") is True
    assert bot_module._cooldown_bypass_callback_data("cx_ok:abc:def") is True
    assert bot_module._cooldown_bypass_callback_data("cx_no:abc:def") is True
    assert bot_module._cooldown_bypass_callback_data("cl_ok") is True
    assert bot_module._cooldown_bypass_callback_data("something_else") is False


def test_parse_approval_callback_parts_supports_alias_format(monkeypatch, tmp_path):
    bot_module, _ = _load_bot_module(monkeypatch, tmp_path)

    assert bot_module._parse_approval_callback_parts("approve:abcd1234:ap-1") == ("abcd1234", "ap-1")
    assert bot_module._parse_approval_callback_parts("reject:efgh5678:ap-2") == ("efgh5678", "ap-2")
    assert bot_module._parse_approval_callback_parts("approve:abcd1234") == ("abcd1234", "")


def test_handle_dispatch_confirm_upserts_task_status_via_task_doc_fallback(monkeypatch, tmp_path):
    bot_module, db_path = _load_bot_module(monkeypatch, tmp_path)
    init_db(db_path)
    monkeypatch.setattr(bot_module, "DB_PATH", db_path)
    monkeypatch.setattr(bot_module, "_send_leader_message", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        bot_module,
        "pre_execution_check",
        lambda description: (bot_module.Decision.ALLOW, "ok"),
    )

    captured = {}

    def fake_spawn_codex_task(**kwargs):
        captured.update(kwargs)
        return str(uuid.uuid4())

    monkeypatch.setattr(bot_module, "spawn_codex_task", fake_spawn_codex_task)

    dispatch_id = "dispatch-1"
    bot_module.pending_dispatches.clear()
    bot_module.pending_dispatches[dispatch_id] = bot_module.CodexDispatch(
        description="P9-6 cooldown sync 구현",
        task_doc=".agent/task/P9-6_missing.md",
        executor="local",
        file_scope=["scripts/telegram_claude_bot.py"],
    )

    bot_module._handle_dispatch_confirm(dispatch_id, 1, ConversationRepo(db_path))

    task_status = {task.task_id: task for task in TaskStatusRepo(db_path).list_all()}
    assert task_status["P9-6"].status == "IN_PROGRESS"
    assert task_status["P9-6"].title == "P9-6 cooldown sync 구현"
    assert captured["task_status_id"] == "P9-6"


def test_handle_codex_completions_marks_done_from_description_fallback(monkeypatch, tmp_path):
    bot_module, db_path = _load_bot_module(monkeypatch, tmp_path)
    init_db(db_path)
    monkeypatch.setattr(bot_module, "DB_PATH", db_path)

    task_repo = TaskRepo(db_path)
    approval_repo = ApprovalRepo(db_path)
    event_repo = EventRepo(db_path)
    conv_repo = ConversationRepo(db_path)

    task_id = str(uuid.uuid4())
    task_repo.create(TaskRecord(task_id=task_id, chat_id=1, description="P9-6 cooldown sync 구현"))
    task_repo.update(
        task_id,
        status="done",
        result_summary="완료",
        finished_at=datetime.now(timezone.utc).isoformat(),
    )
    TaskStatusRepo(db_path).upsert("P9-6", "Claude cooldown sync", "IN_PROGRESS")

    reviewed = []
    monkeypatch.setattr(
        bot_module,
        "_do_review_and_report",
        lambda task, *_args: reviewed.append(task.task_id),
    )

    bot_module._handle_codex_completions(task_repo, approval_repo, event_repo, conv_repo)

    task_status = {task.task_id: task for task in TaskStatusRepo(db_path).list_all()}
    assert task_status["P9-6"].status == "DONE"
    assert reviewed == [task_id]


def test_respond_via_vice_leader_sends_and_logs_response(monkeypatch, tmp_path):
    bot_module, db_path = _load_bot_module(monkeypatch, tmp_path)
    init_db(db_path)
    monkeypatch.setattr(bot_module, "DB_PATH", db_path)

    sent = []
    monkeypatch.setattr(bot_module, "send_message", lambda chat_id, text: sent.append((chat_id, text)))
    monkeypatch.setattr(bot_module, "run_operating_lead_streaming", lambda *args, **kwargs: "Codex 팀장 응답 본문")

    conv_repo = ConversationRepo(db_path)
    task_repo = TaskRepo(db_path)
    task_status_repo = TaskStatusRepo(db_path)
    working_state_repo = WorkingStateRepo(db_path)
    ok = bot_module._respond_via_vice_leader(
        1,
        "현재 상태 알려줘",
        conv_repo,
        task_repo,
        working_state_repo,
        task_status_repo,
    )

    assert ok is True
    assert sent == []
    logs = conv_repo.recent_logs(1)
    assert len(logs) == 1
    assert logs[0].role == "leader"
    assert logs[0].content == "Codex 팀장 응답 본문"


def test_respond_via_operating_lead_processes_dispatch_markers(monkeypatch, tmp_path):
    bot_module, db_path = _load_bot_module(monkeypatch, tmp_path)
    init_db(db_path)
    monkeypatch.setattr(bot_module, "DB_PATH", db_path)
    monkeypatch.setattr(bot_module, "run_operating_lead_streaming", lambda *args, **kwargs: '[CODEX_DISPATCH]{"description":"P16-2","task_doc":".agent/task/P16-2_archive_boundary_anchor_alignment.md"}[/CODEX_DISPATCH]')
    captured = {}

    def _fake_process(text, chat_id, conv_repo, task_repo, approval_repo, event_repo):
        captured["text"] = text
        captured["chat_id"] = chat_id

    monkeypatch.setattr(bot_module, "_process_claude_output", _fake_process)
    monkeypatch.setattr(bot_module, "send_message", lambda *args, **kwargs: None)

    ok = bot_module._respond_via_operating_lead(
        1,
        "P16-2 배정해",
        ConversationRepo(db_path),
        TaskRepo(db_path),
        WorkingStateRepo(db_path),
        TaskStatusRepo(db_path),
    )

    assert ok is True
    assert captured["chat_id"] == 1
    assert "CODEX_DISPATCH" in captured["text"]


def test_respond_via_vice_leader_returns_false_on_failure(monkeypatch, tmp_path):
    bot_module, db_path = _load_bot_module(monkeypatch, tmp_path)
    init_db(db_path)
    monkeypatch.setattr(bot_module, "DB_PATH", db_path)
    monkeypatch.setattr(
        bot_module,
        "run_operating_lead_streaming",
        lambda *args, **kwargs: "⚠️ 오류: streaming failed",
    )
    monkeypatch.setattr(bot_module, "run_vice_leader", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(bot_module, "send_message", lambda *args, **kwargs: None)

    conv_repo = ConversationRepo(db_path)
    ok = bot_module._respond_via_vice_leader(
        1,
        "상태",
        conv_repo,
        TaskRepo(db_path),
        WorkingStateRepo(db_path),
        TaskStatusRepo(db_path),
    )

    assert ok is False
    assert conv_repo.recent_logs(10) == []


def test_respond_via_operating_lead_falls_back_to_codex_on_streaming_error(monkeypatch, tmp_path):
    bot_module, db_path = _load_bot_module(monkeypatch, tmp_path)
    init_db(db_path)
    monkeypatch.setattr(bot_module, "DB_PATH", db_path)

    sent = []
    monkeypatch.setattr(bot_module, "send_message", lambda chat_id, text: sent.append((chat_id, text)))

    def _raise_rate_limit(*_args, **_kwargs):
        raise RuntimeError("codex stream failed")

    monkeypatch.setattr(bot_module, "run_operating_lead_streaming", _raise_rate_limit)
    monkeypatch.setattr(bot_module, "run_vice_leader", lambda *args, **kwargs: "Codex fallback 응답")

    conv_repo = ConversationRepo(db_path)
    ok = bot_module._respond_via_operating_lead(
        1,
        "상태",
        conv_repo,
        TaskRepo(db_path),
        WorkingStateRepo(db_path),
        TaskStatusRepo(db_path),
    )

    assert ok is True
    assert sent == [(1, "👤 Codex 팀장(fallback) 응답:\n\nCodex fallback 응답")]
    assert bot_module._claude_cooldown.is_active() is False


def test_split_codex_commands_splits_batch_lines(monkeypatch, tmp_path):
    bot_module, _ = _load_bot_module(monkeypatch, tmp_path)

    commands = bot_module._split_codex_commands("/codex p16-1\n/codex p16-2\n/codex p16-3")

    assert commands == ["p16-1", "p16-2", "p16-3"]


def test_operating_lead_prompt_allows_dispatch_markers(monkeypatch, tmp_path):
    _load_bot_module(monkeypatch, tmp_path)
    from bot.codex_runner import _build_operating_lead_prompt

    prompt = _build_operating_lead_prompt("P16-1 배정", "요약", "로그")

    assert "CODEX_DISPATCH" in prompt
    assert "출력하지 마라" not in prompt


def test_sync_task_status_from_queue_backfills_only_missing_rows(monkeypatch, tmp_path):
    bot_module, db_path = _load_bot_module(monkeypatch, tmp_path)
    init_db(db_path)
    monkeypatch.setattr(bot_module, "DB_PATH", db_path)

    project_dir = tmp_path / "project"
    queue_dir = project_dir / ".agent"
    queue_dir.mkdir(parents=True, exist_ok=True)
    (queue_dir / "TASK_QUEUE.md").write_text(
        "\n".join(
            [
                "| 항목 | 상태 | 상세 링크 |",
                "| --- | --- | --- |",
                "| **P11 Telegram 리포트 구조 개편 (parent)** | **DONE** | archive |",
                "| P11-1 signal + ai 통합 | DONE | archive |",
                "| **P15 Bot 운영 UX 실증 (parent)** | **IN PROGRESS** | .agent/task/P15_parent_bot_ux_wiring.md |",
                "| P16-2 | P11~P12 archive 경계 문서 정리 | READY | .agent/task/P16-2_archive_boundary_anchor_alignment.md |",
                "| P16-4 | queue and docs sync | BLOCKED | .agent/task/P16-4_queue_and_docs_sync.md |",
                "| P14-5 | Telegram E2E validation packet 정리 | REOPEN | .agent/task/P14-5_telegram_e2e_validation_packet.md |",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(bot_module, "PROJECT_DIR", project_dir)

    repo = TaskStatusRepo(db_path)
    repo.upsert("P11-1", "기존 제목", "IN_PROGRESS")

    bot_module._sync_task_status_from_queue(repo)

    statuses = {row.task_id: row for row in repo.list_all()}
    assert statuses["P11"].status == "DONE"
    assert statuses["P15"].status == "IN_PROGRESS"
    assert statuses["P11-1"].title == "기존 제목"
    assert statuses["P11-1"].status == "IN_PROGRESS"
    assert statuses["P16-2"].status == "READY"
    assert statuses["P16-2"].title == "P11~P12 archive 경계 문서 정리"
    assert statuses["P16-4"].status == "BLOCKED"
    assert statuses["P14-5"].status == "REOPEN"


def test_backfill_role_workspace_defaults_sets_analyzer_to_report(monkeypatch, tmp_path):
    bot_module, db_path = _load_bot_module(monkeypatch, tmp_path)
    init_db(db_path)

    session_repo = SessionRepo(db_path)
    conv_repo = ConversationRepo(db_path)
    session_repo.upsert(
        SessionRecord(
            role="analyzer",
            workspace="development",
            provider="openai_codex",
            session_id="sess-1",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
    )
    conv_repo.upsert_summary(
        ConversationSummaryRecord(
            role="analyzer",
            workspace="development",
            summary="report summary",
            anchors="[]",
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
    )

    bot_module._backfill_role_workspace_defaults(db_path)

    assert session_repo.get("analyzer", workspace="report").workspace == "report"
    assert conv_repo.get_summary("analyzer", workspace="report").workspace == "report"


def test_run_claude_retries_with_new_session_when_resume_session_is_missing(monkeypatch, tmp_path):
    bot_module, db_path = _load_bot_module(monkeypatch, tmp_path)
    init_db(db_path)
    monkeypatch.setattr(bot_module, "DB_PATH", db_path)

    session_repo = SessionRepo(db_path)
    session_repo.upsert(
        SessionRecord(
            role="leader",
            workspace="development",
            provider="claude",
            session_id="stale-session",
            created_at=datetime.now(timezone.utc).isoformat(),
            status="active",
        )
    )

    calls = {"count": 0}

    def _fake_run(cmd, capture_output, text, cwd, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            return type(
                "Result",
                (),
                {
                    "stdout": "",
                    "stderr": "No conversation found with session ID: stale-session",
                },
            )()
        return type("Result", (), {"stdout": "fresh response", "stderr": ""})()

    monkeypatch.setattr(bot_module.subprocess, "run", _fake_run)

    result = bot_module.run_claude("audit prompt")

    assert result == "fresh response"
    assert calls["count"] == 2
    refreshed = session_repo.get("leader", workspace="development")
    assert refreshed is not None
    assert refreshed.session_id != "stale-session"


def test_detect_rate_limit_matches_hit_your_limit_format(monkeypatch, tmp_path):
    bot_module, _ = _load_bot_module(monkeypatch, tmp_path)

    secs = bot_module._detect_rate_limit(
        "You've hit your limit · resets Mar 26, 1pm (Asia/Seoul)"
    )

    assert secs > 0


def test_detect_rate_limit_non_limit_message_returns_zero(monkeypatch, tmp_path):
    bot_module, _ = _load_bot_module(monkeypatch, tmp_path)

    secs = bot_module._detect_rate_limit("정상 응답입니다")

    assert secs == 0


def test_claude_cooldown_set_updates_last_probe_at(monkeypatch, tmp_path):
    bot_module, _ = _load_bot_module(monkeypatch, tmp_path)

    before = bot_module.time.time()
    bot_module._claude_cooldown.clear()
    bot_module._claude_cooldown.set(3600, 1, "resume me")
    after = bot_module.time.time()

    assert before <= bot_module._claude_cooldown.last_probe_at <= after
    assert bot_module._claude_cooldown.pending_message == "resume me"


def test_handle_claude_cooldown_expiry_skips_when_pending_message_empty(monkeypatch, tmp_path):
    bot_module, db_path = _load_bot_module(monkeypatch, tmp_path)
    init_db(db_path)
    monkeypatch.setattr(bot_module, "DB_PATH", db_path)

    called = {"run_claude": 0}

    def _fake_run_claude(message):
        called["run_claude"] += 1
        return "ok"

    monkeypatch.setattr(bot_module, "run_claude", _fake_run_claude)
    monkeypatch.setattr(bot_module, "send_message", lambda *args, **kwargs: None)

    bot_module._claude_cooldown.until = 9999999999.0
    bot_module._claude_cooldown.pending_chat_id = 1
    bot_module._claude_cooldown.pending_message = ""
    bot_module._claude_cooldown.last_probe_at = 0.0

    bot_module._handle_claude_cooldown_expiry(ConversationRepo(db_path))

    assert called["run_claude"] == 0


def test_handle_claude_cooldown_expiry_probe_is_silent_on_rate_limit(monkeypatch, tmp_path):
    bot_module, db_path = _load_bot_module(monkeypatch, tmp_path)
    init_db(db_path)
    monkeypatch.setattr(bot_module, "DB_PATH", db_path)

    sent = []
    monkeypatch.setattr(bot_module, "send_message", lambda chat_id, text: sent.append((chat_id, text)))

    def _fake_run_claude(message):
        raise bot_module.RateLimitHit("Claude 팀장", 3600)

    monkeypatch.setattr(bot_module, "run_claude", _fake_run_claude)

    bot_module._claude_cooldown.until = 9999999999.0
    bot_module._claude_cooldown.pending_chat_id = 1
    bot_module._claude_cooldown.pending_message = "probe me"
    bot_module._claude_cooldown.last_probe_at = 0.0

    bot_module._handle_claude_cooldown_expiry(ConversationRepo(db_path))

    assert sent == []
    assert bot_module._claude_cooldown.pending_message == "probe me"


def test_run_operating_lead_streaming_sends_append_only_chunks(monkeypatch, tmp_path):
    bot_module, db_path = _load_bot_module(monkeypatch, tmp_path)
    init_db(db_path)
    monkeypatch.setattr(bot_module, "DB_PATH", db_path)

    sent = []

    def _fake_stream(message, summary, db_path, project_dir, on_chunk):
        on_chunk("첫 문장입니다.")
        on_chunk("둘째 문장입니다.")
        return "첫 문장입니다. 둘째 문장입니다."

    monkeypatch.setattr(bot_module, "run_vice_leader_streaming", _fake_stream)
    monkeypatch.setattr(bot_module, "send_message", lambda chat_id, text: sent.append((chat_id, text)))

    response = bot_module.run_operating_lead_streaming("질문", 1)

    assert response == "첫 문장입니다. 둘째 문장입니다."
    assert sent == [(1, "첫 문장입니다."), (1, "둘째 문장입니다.")]


def test_run_operating_lead_streaming_rate_limit_does_not_use_placeholder(monkeypatch, tmp_path):
    bot_module, db_path = _load_bot_module(monkeypatch, tmp_path)
    init_db(db_path)
    monkeypatch.setattr(bot_module, "DB_PATH", db_path)

    monkeypatch.setattr(
        bot_module,
        "run_vice_leader_streaming",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("codex stream boom")),
    )

    response = bot_module.run_operating_lead_streaming("질문", 1)

    assert response.startswith("⚠️ 오류:")


def test_build_development_working_state_prefix_includes_current_state(monkeypatch, tmp_path):
    bot_module, db_path = _load_bot_module(monkeypatch, tmp_path)
    init_db(db_path)

    repo = WorkingStateRepo(db_path)
    repo.upsert(
        WorkingStateRecord(
            workspace=bot_module.DEVELOPMENT_WORKSPACE,
            current_goal="P13-1 wiring 정리",
            active_parent_task="P13",
            active_leaf_task="P13-1",
            current_owner=bot_module.LOGICAL_OPERATING_LEAD,
            next_action="working_state 연결 구현",
            last_user_correction="section 구조 수정",
        )
    )

    prefix = bot_module._build_development_working_state_prefix(repo)

    assert "[development working state]" in prefix
    assert "current_goal: P13-1 wiring 정리" in prefix
    assert "active_leaf_task: P13-1" in prefix
    assert "next_action: working_state 연결 구현" in prefix


def test_update_development_working_state_persists_runtime_snapshot(monkeypatch, tmp_path):
    bot_module, db_path = _load_bot_module(monkeypatch, tmp_path)
    init_db(db_path)

    task_status_repo = TaskStatusRepo(db_path)
    task_status_repo.upsert("P13-1", "development working_state runtime 연결", "IN_PROGRESS")
    working_state_repo = WorkingStateRepo(db_path)

    bot_module._update_development_working_state(
        working_state_repo,
        task_status_repo,
        "P13-1부터 진행하자. 다시 정리해줘. schema migration은 보류하고 범위 밖으로 유지해.",
        "결론: development working_state 연결을 먼저 진행합니다.\n제약: schema migration은 지금 범위 밖으로 유지합니다.\n확인 필요: Telegram 실환경 검증은 후속에서 본다.",
    )

    state = working_state_repo.get(bot_module.DEVELOPMENT_WORKSPACE)
    assert state is not None
    assert state.current_goal.startswith("P13-1부터 진행하자")
    assert state.active_parent_task == "P13"
    assert state.active_leaf_task == "P13-1"
    assert state.current_owner == bot_module.LOGICAL_OPERATING_LEAD
    assert state.next_action == "결론: development working_state 연결을 먼저 진행합니다."
    assert state.last_user_correction.startswith("P13-1부터 진행하자")
    decisions = json.loads(state.confirmed_decisions)
    constraints = json.loads(state.constraints)
    questions = json.loads(state.open_questions)
    assert any("결론" in item for item in decisions)
    assert any("유지" in item for item in constraints)
    assert any("확인 필요" in item for item in questions)
    decision_rows = DecisionLedgerRepo(db_path).list_active(bot_module.DEVELOPMENT_WORKSPACE)
    issue_rows = IssueLedgerRepo(db_path).list_open(bot_module.DEVELOPMENT_WORKSPACE)
    assert any("결론" in row.decision_summary for row in decision_rows)
    assert any("제약" in row.decision_summary for row in decision_rows)
    assert any("확인 필요" in row.issue_summary for row in issue_rows)

    bot_module._update_development_working_state(
        working_state_repo,
        task_status_repo,
        "P13-1 상태 다시 정리",
        "결론: development working_state 연결을 유지합니다.\n제약: schema migration은 지금 범위 밖으로 유지합니다.",
    )
    issue_rows = IssueLedgerRepo(db_path).list_open(bot_module.DEVELOPMENT_WORKSPACE)
    assert all("확인 필요" not in row.issue_summary for row in issue_rows)


def test_update_development_working_state_creates_governance_decision_when_task_doc_exists(monkeypatch, tmp_path):
    bot_module, db_path = _load_bot_module(monkeypatch, tmp_path)
    init_db(db_path)

    project_dir = tmp_path / "project"
    task_dir = project_dir / ".agent" / "task"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "P15-9_operating_lead_governance_writeflow.md").write_text(
        "# P15-9\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(bot_module, "PROJECT_DIR", project_dir)
    monkeypatch.setattr(bot_module, "DB_PATH", db_path)

    task_status_repo = TaskStatusRepo(db_path)
    task_status_repo.upsert("P15-9", "governance write flow", "IN_PROGRESS")
    working_state_repo = WorkingStateRepo(db_path)

    bot_module._update_development_working_state(
        working_state_repo,
        task_status_repo,
        "P15-9 진행. task_status provenance는 유지한다.",
        "결론: task_status provenance는 governance ledger에서 관리한다.\n확인 필요: auditor verify flow와 연결한다.",
    )

    topics = DiscussionTopicRepo(db_path).list_by_workspace(bot_module.DEVELOPMENT_WORKSPACE)
    closed_topics = [row for row in topics if row.status == "closed"]
    open_topics = [row for row in topics if row.status == "open"]

    assert any("auditor verify flow" in row.topic_summary for row in open_topics)
    assert len(closed_topics) >= 1

    decision_repo = GovernanceDecisionRepo(db_path)
    artifact_repo = ArtifactRefRepo(db_path)
    matched = False
    for topic in closed_topics:
        active = decision_repo.get_active_decision(topic.topic_id)
        if active is None:
            continue
        if "task_status provenance" in active.decision_summary:
            matched = True
            assert artifact_repo.has_decision_artifact(active.decision_id) is True
    assert matched is True


def test_update_development_working_state_keeps_topic_open_without_task_doc_artifact(monkeypatch, tmp_path):
    bot_module, db_path = _load_bot_module(monkeypatch, tmp_path)
    init_db(db_path)
    monkeypatch.setattr(bot_module, "DB_PATH", db_path)

    project_dir = tmp_path / "project"
    (project_dir / ".agent" / "task").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(bot_module, "PROJECT_DIR", project_dir)

    task_status_repo = TaskStatusRepo(db_path)
    task_status_repo.upsert("P15-99", "missing task doc", "IN_PROGRESS")
    working_state_repo = WorkingStateRepo(db_path)

    bot_module._update_development_working_state(
        working_state_repo,
        task_status_repo,
        "P15-99 진행",
        "결론: workspace identity는 role+workspace 기준으로 유지한다.",
    )

    open_topics = DiscussionTopicRepo(db_path).list_open_topics(bot_module.DEVELOPMENT_WORKSPACE)
    assert any("workspace identity" in row.topic_summary for row in open_topics)
    for topic in open_topics:
        assert GovernanceDecisionRepo(db_path).get_active_decision(topic.topic_id) is None


def test_build_development_working_state_prefix_includes_rich_state_fields(monkeypatch, tmp_path):
    bot_module, db_path = _load_bot_module(monkeypatch, tmp_path)
    init_db(db_path)

    repo = WorkingStateRepo(db_path)
    repo.upsert(
        WorkingStateRecord(
            workspace=bot_module.DEVELOPMENT_WORKSPACE,
            current_goal="P14-1 추출 고도화",
            active_parent_task="P14",
            active_leaf_task="P14-1",
            current_owner=bot_module.LOGICAL_OPERATING_LEAD,
            confirmed_decisions=json.dumps(["결론: Codex 팀장이 기본 owner"], ensure_ascii=False),
            constraints=json.dumps(["제약: schema migration은 범위 밖"], ensure_ascii=False),
            open_questions=json.dumps(["확인 필요: Telegram 실환경 검증"], ensure_ascii=False),
            next_action="추출 규칙 보강",
        )
    )

    prefix = bot_module._build_development_working_state_prefix(repo)

    assert "confirmed_decisions:" in prefix
    assert "constraints:" in prefix
    assert "open_questions:" in prefix
    assert "Codex 팀장이 기본 owner" in prefix


def test_maybe_create_parent_review_packet_when_all_leaf_done(monkeypatch, tmp_path):
    bot_module, db_path = _load_bot_module(monkeypatch, tmp_path)
    init_db(db_path)
    monkeypatch.setattr(bot_module, "DB_PATH", db_path)

    project_dir = tmp_path / "project"
    task_dir = project_dir / ".agent" / "task"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "P13-1_first.md").write_text("x")
    (task_dir / "P13-2_second.md").write_text("x")
    monkeypatch.setattr(bot_module, "PROJECT_DIR", project_dir)

    task_status_repo = TaskStatusRepo(db_path)
    task_status_repo.upsert("P13-1", "leaf1", "DONE")
    task_status_repo.upsert("P13-2", "leaf2", "DONE")

    task = TaskRecord(task_id="task-1", chat_id=1, description="P13-2 작업")
    ReviewPacketRepo(db_path)
    bot_module._maybe_create_parent_review_packet(
        task,
        "P13-2",
        "리뷰 요약",
        task_status_repo,
        ReviewPacketRepo(db_path),
        changed_files=["scripts/telegram_claude_bot.py"],
        test_results=["pytest tests/test_bot/test_telegram_claude_bot.py -q"],
        open_issues=["주의: Telegram 실환경 검증 필요"],
    )

    packets = ReviewPacketRepo(db_path).list_by_parent("P13")
    assert len(packets) == 1
    assert packets[0].workspace == bot_module.DEVELOPMENT_WORKSPACE
    assert "latest leaf P13-2 reviewed" in packets[0].summary
    assert "telegram_claude_bot.py" in packets[0].changed_files
    assert "pytest" in packets[0].test_results
    assert "주의" in packets[0].open_issues
    audits = AuditQueueRepo(db_path).list_by_parent("P13")
    assert len(audits) == 1
    assert audits[0].status == "queued"


def test_maybe_create_parent_review_packet_skips_when_sibling_not_done(monkeypatch, tmp_path):
    bot_module, db_path = _load_bot_module(monkeypatch, tmp_path)
    init_db(db_path)
    monkeypatch.setattr(bot_module, "DB_PATH", db_path)

    project_dir = tmp_path / "project"
    task_dir = project_dir / ".agent" / "task"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "P13-1_first.md").write_text("x")
    (task_dir / "P13-2_second.md").write_text("x")
    monkeypatch.setattr(bot_module, "PROJECT_DIR", project_dir)

    task_status_repo = TaskStatusRepo(db_path)
    task_status_repo.upsert("P13-1", "leaf1", "DONE")
    task_status_repo.upsert("P13-2", "leaf2", "IN_PROGRESS")

    task = TaskRecord(task_id="task-1", chat_id=1, description="P13-1 작업")
    bot_module._maybe_create_parent_review_packet(
        task,
        "P13-1",
        "리뷰 요약",
        task_status_repo,
        ReviewPacketRepo(db_path),
    )

    packets = ReviewPacketRepo(db_path).list_by_parent("P13")
    assert packets == []


def test_handle_one_audit_queue_item_marks_reviewed(monkeypatch, tmp_path):
    bot_module, db_path = _load_bot_module(monkeypatch, tmp_path)
    init_db(db_path)
    monkeypatch.setattr(bot_module, "DB_PATH", db_path)
    monkeypatch.setattr(bot_module, "ALLOWED_CHAT_ID", "1")

    review_packet_repo = ReviewPacketRepo(db_path)
    audit_queue_repo = AuditQueueRepo(db_path)
    packet = ReviewPacketRecord(
        packet_id="packet-1",
        parent_task_id="P13",
        workspace=bot_module.DEVELOPMENT_WORKSPACE,
        created_by="codex_lead",
        summary="parent done",
        changed_files='["scripts/telegram_claude_bot.py"]',
        snapshot_fingerprint="fp-1",
    )
    review_packet_repo.create(packet)
    audit_queue_repo.enqueue(
        bot_module.AuditQueueRecord(
            audit_id="audit-1",
            parent_task_id="P13",
            packet_id="packet-1",
            workspace=bot_module.DEVELOPMENT_WORKSPACE,
            changed_files='["scripts/telegram_claude_bot.py"]',
            snapshot_fingerprint="fp-1",
        )
    )

    DiscussionTopicRepo(db_path).open_topic(
        DiscussionTopicRecord(
            topic_id="topic-1",
            category="control_plane_state_policy",
            workspace=bot_module.DEVELOPMENT_WORKSPACE,
            topic_summary="task_status provenance를 governance ledger에서 관리한다",
            why_needed="runtime DONE과 backfill DONE을 audit에서 구분해야 한다",
            opened_by="codex_lead",
            status="closed",
            current_decision_id="decision-1",
            source_kind="working_state",
            source_ref="P13",
        )
    )
    GovernanceDecisionRepo(db_path).create(
        GovernanceDecisionRecord(
            decision_id="decision-1",
            topic_id="topic-1",
            workspace=bot_module.DEVELOPMENT_WORKSPACE,
            decision_summary="task_status provenance는 governance ledger에서 관리한다",
            decision_rationale="audit 입력 정합성을 유지하기 위해",
            closed_by="codex_lead",
            source_kind="working_state",
            source_ref="P13",
        )
    )
    ArtifactRefRepo(db_path).attach_artifact(
        bot_module.ArtifactRefRecord(
            artifact_id="artifact-1",
            decision_id="decision-1",
            artifact_kind="task_doc",
            artifact_ref=".agent/task/CODEX_P15-9_operating_lead_governance_writeflow.md",
            artifact_role="evidence",
            created_by="codex_lead",
        )
    )

    sent = []
    captured = {}
    def _run_claude(prompt):
        captured["prompt"] = prompt
        return "No critical findings."
    monkeypatch.setattr(bot_module, "run_claude", _run_claude)
    monkeypatch.setattr(bot_module, "_send_leader_message", lambda chat_id, text, conv_repo: sent.append((chat_id, text)))
    bot_module._claude_cooldown.clear()

    bot_module._handle_one_audit_queue_item(ConversationRepo(db_path))

    audit = audit_queue_repo.get("audit-1")
    assert audit is not None
    assert audit.status == "reviewed"
    assert audit.changed_files == '["scripts/telegram_claude_bot.py"]'
    assert "No critical findings." in audit.review_summary
    assert sent
    assert "Claude 감리 완료" in sent[0][1]
    assert "governance_snapshot:" in captured["prompt"]
    assert "changed_file_list:" in captured["prompt"]
    assert "- scripts/telegram_claude_bot.py" in captured["prompt"]
    assert "task_status provenance를 governance ledger에서 관리한다" in captured["prompt"]
    assert ".agent/task/CODEX_P15-9_operating_lead_governance_writeflow.md" in captured["prompt"]
    assert "reopen 권고" in captured["prompt"]


def test_handle_one_audit_queue_item_defers_on_rate_limit(monkeypatch, tmp_path):
    bot_module, db_path = _load_bot_module(monkeypatch, tmp_path)
    init_db(db_path)
    monkeypatch.setattr(bot_module, "DB_PATH", db_path)
    monkeypatch.setattr(bot_module, "ALLOWED_CHAT_ID", "1")

    review_packet_repo = ReviewPacketRepo(db_path)
    audit_queue_repo = AuditQueueRepo(db_path)
    review_packet_repo.create(
        ReviewPacketRecord(
            packet_id="packet-1",
            parent_task_id="P13",
            workspace=bot_module.DEVELOPMENT_WORKSPACE,
            created_by="codex_lead",
            summary="parent done",
            changed_files='["scripts/telegram_claude_bot.py"]',
            snapshot_fingerprint="fp-1",
        )
    )
    audit_queue_repo.enqueue(
        bot_module.AuditQueueRecord(
            audit_id="audit-1",
            parent_task_id="P13",
            packet_id="packet-1",
            workspace=bot_module.DEVELOPMENT_WORKSPACE,
            changed_files='["scripts/telegram_claude_bot.py"]',
            snapshot_fingerprint="fp-1",
        )
    )

    def _raise_rate_limit(prompt):
        raise bot_module.RateLimitHit("Claude 팀장", 3600)

    monkeypatch.setattr(bot_module, "run_claude", _raise_rate_limit)
    bot_module._claude_cooldown.clear()

    bot_module._handle_one_audit_queue_item(ConversationRepo(db_path))

    audit = audit_queue_repo.get("audit-1")
    assert audit is not None
    assert audit.status == "deferred_rate_limit"
    assert audit.defer_count == 1
    assert audit.next_retry_at is not None
    assert audit.rate_limit_until is not None


def test_handle_one_audit_queue_item_supersedes_stale_packet(monkeypatch, tmp_path):
    bot_module, db_path = _load_bot_module(monkeypatch, tmp_path)
    init_db(db_path)
    monkeypatch.setattr(bot_module, "DB_PATH", db_path)

    review_packet_repo = ReviewPacketRepo(db_path)
    audit_queue_repo = AuditQueueRepo(db_path)
    review_packet_repo.create(
        ReviewPacketRecord(
            packet_id="packet-old",
            parent_task_id="P13",
            workspace=bot_module.DEVELOPMENT_WORKSPACE,
            created_by="codex_lead",
            summary="old",
            changed_files='["old.py"]',
            snapshot_fingerprint="fp-old",
        )
    )
    review_packet_repo.create(
        ReviewPacketRecord(
            packet_id="packet-new",
            parent_task_id="P13",
            workspace=bot_module.DEVELOPMENT_WORKSPACE,
            created_by="codex_lead",
            summary="new",
            changed_files='["new.py"]',
            snapshot_fingerprint="fp-new",
        )
    )
    audit_queue_repo.enqueue(
        bot_module.AuditQueueRecord(
            audit_id="audit-old",
            parent_task_id="P13",
            packet_id="packet-old",
            workspace=bot_module.DEVELOPMENT_WORKSPACE,
            changed_files='["old.py"]',
            snapshot_fingerprint="fp-old",
        )
    )

    bot_module._claude_cooldown.clear()
    monkeypatch.setattr(bot_module, "run_claude", lambda prompt: "should not be used")

    bot_module._handle_one_audit_queue_item(ConversationRepo(db_path))

    old_audit = audit_queue_repo.get("audit-old")
    assert old_audit is not None
    assert old_audit.status == "superseded"
    replacement = audit_queue_repo.list_by_packet("packet-new")
    assert len(replacement) == 1
    assert old_audit.superseded_by_audit_id == replacement[0].audit_id
    assert replacement[0].changed_files == '["new.py"]'


def test_extract_review_test_results_and_open_issues(monkeypatch, tmp_path):
    bot_module, _ = _load_bot_module(monkeypatch, tmp_path)

    test_results = bot_module._extract_review_test_results(
        "pytest tests/test_bot/test_telegram_claude_bot.py -q\n21 passed in 8.06s",
        "No critical findings.",
    )
    open_issues = bot_module._extract_review_open_issues(
        "failed",
        "⚠️ 오류: timeout",
        "Residual risk: Telegram 실환경 미검증",
    )

    assert any("pytest" in item for item in test_results)
    assert any("passed" in item.lower() for item in test_results)
    assert any("timeout" in item.lower() for item in open_issues)
    assert any("residual" in item.lower() for item in open_issues)
