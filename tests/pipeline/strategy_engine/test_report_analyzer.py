from __future__ import annotations

import json
from pathlib import Path

from bot.task_store import ConversationRepo, SessionRepo
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
            "분석 결과 본문",
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

    assert result == "분석 결과 본문"

    session = SessionRepo(db_path).get("analyzer")
    assert session is not None
    assert session.provider == "openai_codex"

    summary = ConversationRepo(db_path).get_summary("analyzer")
    assert summary is not None
    data = json.loads(summary.summary)
    assert data["workspace"] == "report"
    assert "분석 결과" in data["last_report_excerpt"]


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
