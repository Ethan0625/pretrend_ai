from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

pytest.importorskip("bot.task_store", reason="bot module not available in this environment")

try:
    from bot.task_store import (
        CheckpointSummaryRecord,
        CheckpointSummaryRepo,
        ConversationRepo,
        DecisionLedgerRepo,
        IssueLedgerRepo,
        SessionRepo,
        WorkingStateRecord,
        WorkingStateRepo,
        init_db,
    )
except ModuleNotFoundError:
    _SRC_ROOT = Path(__file__).resolve().parents[3] / "src"
    if str(_SRC_ROOT) not in sys.path:
        sys.path.insert(0, str(_SRC_ROOT))
    from bot.task_store import (
        CheckpointSummaryRecord,
        CheckpointSummaryRepo,
        ConversationRepo,
        DecisionLedgerRepo,
        IssueLedgerRepo,
        SessionRepo,
        WorkingStateRecord,
        WorkingStateRepo,
        init_db,
    )
from pretrend.pipeline.strategy_engine.report_analyzer import generate_report_via_analyzer


def test_generate_report_via_analyzer_creates_session_and_summary(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "orchestrator.db"
    monkeypatch.setenv("PRETREND_STATE_DB", str(db_path))
    monkeypatch.setattr(
        "pretrend.pipeline.strategy_engine.report_analyzer._require_codex_bin",
        lambda: Path("/tmp/fake-codex"),
    )

    def _fake_run(cmd, *, cwd, timeout):
        return (
            type("Result", (), {"returncode": 0, "stdout": "session 123e4567-e89b-12d3-a456-426614174000", "stderr": ""})(),
            "구조 원칙: 분석 결과는 한 흐름으로 유지합니다.\n제약: macro raw 값은 본문에 직접 노출하지 않습니다.",
        )

    monkeypatch.setattr(
        "pretrend.pipeline.strategy_engine.report_analyzer._run_codex_output_command",
        _fake_run,
    )

    result = generate_report_via_analyzer(
        system_prompt="system",
        user_content='{"a":"b"}',
        timeout=5,
    )

    assert "구조 원칙" in result

    session = SessionRepo(db_path).get("analyzer", workspace="report")
    assert session is not None
    assert session.provider == "openai_codex"

    summary = ConversationRepo(db_path).get_summary("analyzer", workspace="report")
    assert summary is not None
    data = json.loads(summary.summary)
    assert data["workspace"] == "report"
    assert "분석 결과" in data["last_report_excerpt"]

    state = WorkingStateRepo(db_path).get("report")
    assert state is not None
    assert state.current_owner == "analyzer"
    assert state.current_goal == "Telegram report generation"
    assert state.last_user_correction == '{"a":"b"}'
    decisions = json.loads(state.confirmed_decisions)
    constraints = json.loads(state.constraints)
    assert any("구조" in item or "유지" in item for item in decisions)
    assert any("노출하지 않" in item or "본문" in item or "보조 블록" in item for item in constraints)


def test_generate_report_via_analyzer_reuses_active_session(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "orchestrator.db"
    monkeypatch.setenv("PRETREND_STATE_DB", str(db_path))
    monkeypatch.setattr(
        "pretrend.pipeline.strategy_engine.report_analyzer._require_codex_bin",
        lambda: Path("/tmp/fake-codex"),
    )

    calls = []

    def _fake_run(cmd, *, cwd, timeout):
        calls.append(cmd)
        stdout = ""
        if len(calls) == 1:
            stdout = "session 123e4567-e89b-12d3-a456-426614174000"
        return (
            type("Result", (), {"returncode": 0, "stdout": stdout, "stderr": ""})(),
            "재사용 응답",
        )

    monkeypatch.setattr(
        "pretrend.pipeline.strategy_engine.report_analyzer._run_codex_output_command",
        _fake_run,
    )

    first = generate_report_via_analyzer(
        system_prompt="system",
        user_content='{"first":"payload"}',
        timeout=5,
    )
    second = generate_report_via_analyzer(
        system_prompt="system",
        user_content='{"second":"payload"}',
        timeout=5,
    )

    assert first == "재사용 응답"
    assert second == "재사용 응답"
    assert any("resume" in cmd for cmd in calls[1:])


def test_generate_report_via_analyzer_includes_report_memory_context(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "orchestrator.db"
    monkeypatch.setenv("PRETREND_STATE_DB", str(db_path))
    monkeypatch.setattr(
        "pretrend.pipeline.strategy_engine.report_analyzer._require_codex_bin",
        lambda: Path("/tmp/fake-codex"),
    )
    init_db(db_path)

    WorkingStateRepo(db_path).upsert(
        WorkingStateRecord(
            workspace="report",
            current_goal="report 구조 일관성 유지",
            current_owner="analyzer",
            next_action="compact 규칙 유지",
            confirmed_decisions='["macro raw 값은 본문에 직접 노출하지 않음"]',
        )
    )
    CheckpointSummaryRepo(db_path).create(
        CheckpointSummaryRecord(
            checkpoint_id="cp-1",
            workspace="report",
            topic="p11-3",
            summary_text="paper/mock result는 compact block으로 축약",
        )
    )

    captured = {}

    def _fake_run(cmd, *, cwd, timeout):
        captured["prompt"] = cmd[-1]
        return (
            type("Result", (), {"returncode": 0, "stdout": "session 123e4567-e89b-12d3-a456-426614174000", "stderr": ""})(),
            "리포트 응답",
        )

    monkeypatch.setattr(
        "pretrend.pipeline.strategy_engine.report_analyzer._run_codex_output_command",
        _fake_run,
    )

    result = generate_report_via_analyzer(
        system_prompt="system",
        user_content='{"signal":"payload"}',
        timeout=5,
    )

    assert result == "리포트 응답"
    assert "report working state" in captured["prompt"]
    assert "current_goal: report 구조 일관성 유지" in captured["prompt"]
    assert "macro raw 값은 본문에 직접 노출하지 않음" in captured["prompt"]
    assert "최근 report checkpoint" in captured["prompt"]
    assert "paper/mock result는 compact block으로 축약" in captured["prompt"]


def test_generate_report_via_analyzer_updates_report_working_state_rich_fields(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "orchestrator.db"
    monkeypatch.setenv("PRETREND_STATE_DB", str(db_path))
    monkeypatch.setattr(
        "pretrend.pipeline.strategy_engine.report_analyzer._require_codex_bin",
        lambda: Path("/tmp/fake-codex"),
    )

    def _fake_run(cmd, *, cwd, timeout):
        return (
            type("Result", (), {"returncode": 0, "stdout": "session 123e4567-e89b-12d3-a456-426614174000", "stderr": ""})(),
            "구조 원칙: Signal과 해석은 한 흐름으로 통합합니다.\ncompact 규칙: paper/mock 결과는 보조 블록으로 축약합니다.\n확인 필요: Telegram 실환경 길이 검증은 후속입니다.",
        )

    monkeypatch.setattr(
        "pretrend.pipeline.strategy_engine.report_analyzer._run_codex_output_command",
        _fake_run,
    )

    result = generate_report_via_analyzer(
        system_prompt="system",
        user_content='{"signal":"payload"}',
        timeout=5,
    )

    assert result is not None
    state = WorkingStateRepo(db_path).get("report")
    assert state is not None
    decisions = json.loads(state.confirmed_decisions)
    constraints = json.loads(state.constraints)
    questions = json.loads(state.open_questions)
    assert any("구조 원칙" in item or "통합" in item for item in decisions)
    assert any("compact 규칙" in item or "보조 블록" in item for item in constraints)
    assert any("확인 필요" in item for item in questions)
    decision_rows = DecisionLedgerRepo(db_path).list_active("report")
    issue_rows = IssueLedgerRepo(db_path).list_open("report")
    assert any("구조 원칙" in row.decision_summary or "compact 규칙" in row.decision_summary for row in decision_rows)
    assert any("확인 필요" in row.issue_summary for row in issue_rows)


def test_generate_report_via_analyzer_has_no_default_timeout(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    monkeypatch.setenv("PRETREND_STATE_DB", str(db_path))
    monkeypatch.delenv("REPORT_ANALYZER_TIMEOUT", raising=False)
    monkeypatch.setattr(
        "pretrend.pipeline.strategy_engine.report_analyzer._require_codex_bin",
        lambda: Path("/tmp/fake-codex"),
    )

    captured = {}

    def _fake_run(cmd, *, cwd, timeout):
        captured["timeout"] = timeout
        return (
            type("Result", (), {"returncode": 0, "stdout": "session 123e4567-e89b-12d3-a456-426614174000", "stderr": ""})(),
            "리포트 응답",
        )

    monkeypatch.setattr(
        "pretrend.pipeline.strategy_engine.report_analyzer._run_codex_output_command",
        _fake_run,
    )

    result = generate_report_via_analyzer(
        system_prompt="system",
        user_content='{"signal":"payload"}',
        timeout=5,
    )

    assert result == "리포트 응답"
    assert captured["timeout"] is None
