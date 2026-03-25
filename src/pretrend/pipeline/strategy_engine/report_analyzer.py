from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from bot.task_store import (
    ConversationRepo,
    ConversationSummaryRecord,
    SessionRecord,
    SessionRepo,
    init_db,
)

_ANALYZER_ROLE = "analyzer"
_ANALYZER_PROVIDER = "openai_codex"
_ANALYZER_TIMEOUT_SECS = 180
_SESSION_ID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _default_state_db_path() -> Path:
    return _project_root().parent / "state" / "orchestrator.db"


def _require_codex_bin() -> Path:
    ext_root = Path.home() / ".vscode-server" / "extensions"
    candidates = sorted(ext_root.glob("openai.chatgpt-*/bin/linux-x86_64/codex"))
    if candidates:
        return candidates[-1]
    raise RuntimeError("Codex binary not found for report analyzer")


def _extract_session_id(output: str) -> Optional[str]:
    match = _SESSION_ID_RE.search(output)
    return match.group(0) if match else None


def _run_codex_output_command(
    cmd: list[str],
    *,
    cwd: Path,
    timeout: int,
) -> tuple[subprocess.CompletedProcess[str], str]:
    with tempfile.NamedTemporaryFile(prefix="codex-report-", suffix=".txt", delete=False) as tmp:
        output_path = Path(tmp.name)
    try:
        result = subprocess.run(
            [*cmd, "--output-last-message", str(output_path)],
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=timeout,
        )
        response = output_path.read_text().strip() if output_path.exists() else ""
        return result, response
    finally:
        output_path.unlink(missing_ok=True)


def _build_report_analyzer_prompt(
    *,
    system_prompt: str,
    user_content: str,
    prior_summary: str,
) -> str:
    return f"""[역할]
너는 Pretrend AI report workspace 전용 analyzer 세션이다.
너의 책임은 입력 payload를 읽고 Telegram용 한국어 시장 해석문을 작성하는 것이다.
개발/디버깅/작업 배정 응답을 하지 말고, report 생성에만 집중한다.

[이전 report workspace 요약]
{prior_summary or "(이전 요약 없음)"}

[시스템 프롬프트]
{system_prompt}

[현재 입력 payload]
{user_content}
"""


def generate_report_via_analyzer(
    *,
    system_prompt: str,
    user_content: str,
    timeout: int,
) -> Optional[str]:
    """Generate a report via persistent Codex analyzer session.

    Transitional design:
    - Reuse existing sessions/conversation_summary schema without migration.
    - `role='analyzer'` is interpreted as report-only session in P11.
    """
    db_path = Path(os.getenv("PRETREND_STATE_DB", str(_default_state_db_path())))
    init_db(db_path)

    session_repo = SessionRepo(db_path)
    conv_repo = ConversationRepo(db_path)
    session = session_repo.get(_ANALYZER_ROLE)
    summary_record = conv_repo.get_summary(_ANALYZER_ROLE)
    prior_summary = summary_record.summary if summary_record else ""

    prompt = _build_report_analyzer_prompt(
        system_prompt=system_prompt,
        user_content=user_content,
        prior_summary=prior_summary,
    )
    codex_bin = _require_codex_bin()
    project_dir = _project_root()
    timeout_secs = int(os.getenv("REPORT_ANALYZER_TIMEOUT", str(timeout or _ANALYZER_TIMEOUT_SECS)))

    if session and session.status == "active":
        result, response = _run_codex_output_command(
            [
                str(codex_bin),
                "exec",
                "resume",
                session.session_id,
                "--full-auto",
                "-C",
                str(project_dir),
                prompt,
            ],
            cwd=project_dir,
            timeout=timeout_secs,
        )
        if result.returncode == 0:
            session_repo.touch(_ANALYZER_ROLE)
            raw = response or result.stdout.strip()
            _update_analyzer_summary(conv_repo, raw, summary_record)
            return raw or None
        session_repo.set_status(_ANALYZER_ROLE, "broken")

    result, response = _run_codex_output_command(
        [
            str(codex_bin),
            "exec",
            "--full-auto",
            "-C",
            str(project_dir),
            prompt,
        ],
        cwd=project_dir,
        timeout=timeout_secs,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Codex report analyzer failed")

    session_id = _extract_session_id(f"{result.stdout}\n{result.stderr}")
    now = _now_iso()
    if session_id:
        session_repo.upsert(
            SessionRecord(
                role=_ANALYZER_ROLE,
                provider=_ANALYZER_PROVIDER,
                session_id=session_id,
                created_at=now,
                last_used_at=now,
                status="active",
            )
        )
    raw = response or result.stdout.strip()
    _update_analyzer_summary(conv_repo, raw, summary_record)
    return raw or None


def _update_analyzer_summary(
    conv_repo: ConversationRepo,
    response_text: str,
    existing: ConversationSummaryRecord | None,
) -> None:
    now = _now_iso()
    summary_payload = json.dumps(
        {
            "workspace": "report",
            "last_report_excerpt": response_text[:1200],
        },
        ensure_ascii=False,
    )
    conv_repo.upsert_summary(
        ConversationSummaryRecord(
            role=_ANALYZER_ROLE,
            summary=summary_payload,
            anchors=json.dumps(["workspace=report", "report_analyzer"], ensure_ascii=False),
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
    )
