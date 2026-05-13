"""tests/test_bot/test_codex_runner.py — Codex prompt helper unit tests."""
import sqlite3
from pathlib import Path
from types import SimpleNamespace
import uuid

from src.bot.codex_runner import OUTPUT_FILENAME, _build_task_prompt, _codex_worker, run_vice_leader, run_vice_leader_streaming
from src.bot.task_store import ConversationRepo, SessionRecord, SessionRepo, TaskRecord, TaskRepo, TaskStatusRepo, init_db


def test_build_task_prompt_without_file_scope_keeps_existing_behavior():
    description = "output_parser.py 수정"
    assert _build_task_prompt(description, []) == description
    assert _build_task_prompt(description, None) == description


def test_build_task_prompt_with_file_scope_prepends_constraint():
    description = "output_parser.py 수정"
    prompt = _build_task_prompt(
        description,
        ["src/bot/output_parser.py", "src/bot/codex_runner.py"],
    )
    assert prompt.startswith(
        "수정 가능한 파일: src/bot/output_parser.py, src/bot/codex_runner.py. "
        "이 파일 외에는 절대 수정하지 마라."
    )
    assert prompt.endswith(description)


def test_codex_worker_persists_output_and_deletes_output_file(tmp_path, monkeypatch):
    db_path = tmp_path / "orchestrator.db"
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()
    init_db(db_path)

    task = TaskRecord(task_id=str(uuid.uuid4()), chat_id=1, description="작업")
    TaskRepo(db_path).create(task)
    TaskStatusRepo(db_path).upsert("P9-5", "task_status DB", "TODO")

    def fake_require_codex_bin():
        return Path("/tmp/fake-codex")

    def fake_run(*args, **kwargs):
        (worktree_path / OUTPUT_FILENAME).write_text("최종 출력\n둘째 줄\n")
        return SimpleNamespace(stdout="stdout fallback", stderr="", returncode=0)

    monkeypatch.setattr("src.bot.codex_runner._require_codex_bin", fake_require_codex_bin)
    monkeypatch.setattr("src.bot.codex_runner.subprocess.run", fake_run)

    _codex_worker(
        task_id=task.task_id,
        description=task.description,
        file_scope=[],
        worktree_path=worktree_path,
        db_path=db_path,
        task_status_id="P9-5",
    )

    repo = TaskRepo(db_path)
    saved = repo.get(task.task_id)
    assert saved is not None
    assert saved.status == "done"
    assert saved.result_summary == "최종 출력\n둘째 줄"
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT output FROM tasks WHERE task_id=?",
            (task.task_id,),
        ).fetchone()
    assert row is not None
    assert row[0] == "최종 출력\n둘째 줄\n"
    assert not (worktree_path / OUTPUT_FILENAME).exists()
    task_status = {
        task.task_id: task for task in TaskStatusRepo(db_path).list_all()
    }
    assert task_status["P9-5"].status == "DONE"


def test_run_vice_leader_includes_recent_conversation_logs_in_prompt(tmp_path, monkeypatch):
    db_path = tmp_path / "orchestrator.db"
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    init_db(db_path)

    conv_repo = ConversationRepo(db_path)
    conv_repo.append_log("user", "P11 task 초안 먼저 정리해줘")
    conv_repo.append_log("leader", "운영 안정화 이후 P11로 간다")
    conv_repo.append_log("vice_leader", "P11a~d로 쪼개는 게 맞다")

    captured = {}

    monkeypatch.setattr("src.bot.codex_runner._require_codex_bin", lambda: Path("/tmp/fake-codex"))

    def fake_run_codex_output_command(cmd, *, cwd, timeout):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        captured["timeout"] = timeout
        return SimpleNamespace(returncode=0, stdout="stdout", stderr=""), "Codex 팀장 답변"

    monkeypatch.setattr("src.bot.codex_runner._run_codex_output_command", fake_run_codex_output_command)

    response = run_vice_leader("그럼 P11a부터 상세화해줘", '{"topic":"P11 planning"}', db_path, project_dir)

    assert response == "Codex 팀장 답변"
    prompt = captured["cmd"][-1]
    assert "[최근 대화 로그]" in prompt
    assert "[user] P11 task 초안 먼저 정리해줘" in prompt
    assert "[leader] 운영 안정화 이후 P11로 간다" in prompt
    assert "[vice_leader] P11a~d로 쪼개는 게 맞다" in prompt
    assert "너는 현재 Pretrend 운영을 담당하는 Codex 팀장(operating_lead)이다." in prompt
    assert "부팀장이라고 말하지 마라." in prompt
    assert "[사용자 메시지]\n그럼 P11a부터 상세화해줘" in prompt


def test_run_vice_leader_streaming_emits_agent_message_chunks(tmp_path, monkeypatch):
    db_path = tmp_path / "orchestrator.db"
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    init_db(db_path)

    class _FakeProcess:
        def __init__(self, output_path: Path):
            self.stdout_lines = iter(
                [
                    '{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"첫 단계 확인 중"}}\n',
                    '{"type":"item.completed","item":{"id":"item_1","type":"agent_message","text":"둘째 단계 진행 중"}}\n',
                ]
            )
            output_path.write_text("최종 답변", encoding="utf-8")

        @property
        def stdout(self):
            return self

        def readline(self):
            try:
                return next(self.stdout_lines)
            except StopIteration:
                return ""

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr("src.bot.codex_runner._require_codex_bin", lambda: Path("/tmp/fake-codex"))
    monkeypatch.setattr("src.bot.codex_runner._extract_session_id", lambda output: None)

    def fake_popen(cmd, **kwargs):
        output_path = Path(cmd[-1])
        assert "--json" in cmd
        return _FakeProcess(output_path)

    monkeypatch.setattr("src.bot.codex_runner.subprocess.Popen", fake_popen)

    chunks = []
    response = run_vice_leader_streaming(
        "상태 알려줘",
        '{"topic":"test"}',
        db_path,
        project_dir,
        on_chunk=lambda text: chunks.append(text),
    )

    assert response == "최종 답변"
    assert chunks == ["첫 단계 확인 중", "둘째 단계 진행 중"]


def test_run_vice_leader_streaming_resume_places_cd_before_resume(tmp_path, monkeypatch):
    db_path = tmp_path / "orchestrator.db"
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    init_db(db_path)
    SessionRepo(db_path).upsert(
        SessionRecord(
            role="vice_leader",
            workspace="development",
            provider="openai_codex",
            session_id="session-123",
            created_at="2026-03-30T00:00:00+00:00",
            last_used_at="2026-03-30T00:00:00+00:00",
            status="active",
        )
    )

    class _FakeProcess:
        def __init__(self, output_path: Path):
            self.stdout_lines = iter([])
            output_path.write_text("최종 답변", encoding="utf-8")

        @property
        def stdout(self):
            return self

        def readline(self):
            return ""

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr("src.bot.codex_runner._require_codex_bin", lambda: Path("/tmp/fake-codex"))
    monkeypatch.setattr("src.bot.codex_runner._extract_session_id", lambda output: None)

    captured = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        output_path = Path(cmd[-1])
        return _FakeProcess(output_path)

    monkeypatch.setattr("src.bot.codex_runner.subprocess.Popen", fake_popen)

    run_vice_leader_streaming(
        "상태 알려줘",
        '{"topic":"test"}',
        db_path,
        project_dir,
        on_chunk=None,
    )

    cmd = captured["cmd"]
    assert cmd[:6] == [
        "/tmp/fake-codex",
        "exec",
        "-C",
        str(project_dir),
        "resume",
        "session-123",
    ]


def test_run_vice_leader_streaming_retries_fresh_session_after_resume_failure(tmp_path, monkeypatch):
    db_path = tmp_path / "orchestrator.db"
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    init_db(db_path)
    SessionRepo(db_path).upsert(
        SessionRecord(
            role="vice_leader",
            workspace="development",
            provider="openai_codex",
            session_id="stale-session",
            created_at="2026-03-30T00:00:00+00:00",
            last_used_at="2026-03-30T00:00:00+00:00",
            status="active",
        )
    )

    class _FakeProcess:
        def __init__(self, lines, output_path: Path, final_output: str, return_code: int):
            self.stdout_lines = iter(lines)
            output_path.write_text(final_output, encoding="utf-8")
            self._return_code = return_code

        @property
        def stdout(self):
            return self

        def readline(self):
            try:
                return next(self.stdout_lines)
            except StopIteration:
                return ""

        def poll(self):
            return self._return_code

        def wait(self, timeout=None):
            return self._return_code

    monkeypatch.setattr("src.bot.codex_runner._require_codex_bin", lambda: Path("/tmp/fake-codex"))
    monkeypatch.setattr("src.bot.codex_runner._extract_session_id", lambda output: "new-session")

    calls = {"count": 0, "cmds": []}

    def fake_popen(cmd, **kwargs):
        calls["count"] += 1
        calls["cmds"].append(cmd)
        output_path = Path(cmd[-1])
        if calls["count"] == 1:
            return _FakeProcess(
                ["thread/resume failed: no rollout found for thread id stale-session\n"],
                output_path,
                "",
                1,
            )
        return _FakeProcess([], output_path, "최종 답변", 0)

    monkeypatch.setattr("src.bot.codex_runner.subprocess.Popen", fake_popen)

    response = run_vice_leader_streaming(
        "상태 알려줘",
        '{"topic":"test"}',
        db_path,
        project_dir,
        on_chunk=None,
    )

    assert response == "최종 답변"
    assert calls["count"] == 2
    assert "resume" in calls["cmds"][0]
    assert "resume" not in calls["cmds"][1]
    session = SessionRepo(db_path).get("vice_leader", workspace="development")
    assert session is not None
    assert session.session_id == "new-session"
