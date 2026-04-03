from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Optional

try:
    from bot.task_store import (
        CheckpointSummaryRepo,
        ConversationRepo,
        ConversationSummaryRecord,
        DecisionLedgerRepo,
        DecisionRecord,
        IssueLedgerRepo,
        IssueRecord,
        SessionRecord,
        SessionRepo,
        WorkingStateRecord,
        WorkingStateRepo,
        init_db,
    )
except ModuleNotFoundError:
    _SRC_ROOT = Path(__file__).resolve().parents[4]
    if str(_SRC_ROOT) not in sys.path:
        sys.path.insert(0, str(_SRC_ROOT))
    from bot.task_store import (
        CheckpointSummaryRepo,
        ConversationRepo,
        ConversationSummaryRecord,
        DecisionLedgerRepo,
        DecisionRecord,
        IssueLedgerRepo,
        IssueRecord,
        SessionRecord,
        SessionRepo,
        WorkingStateRecord,
        WorkingStateRepo,
        init_db,
    )

_ANALYZER_ROLE = "analyzer"
_ANALYZER_PROVIDER = "openai_codex"
_ANALYZER_TIMEOUT_SECS = 180
_REPORT_WORKSPACE = "report"
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
    timeout: int | None,
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
    working_state_text: str,
    checkpoint_text: str,
) -> str:
    return f"""[역할]
너는 Pretrend AI report workspace 전용 analyzer 세션이다.
너의 책임은 입력 payload를 읽고 Telegram용 한국어 시장 해석문을 작성하는 것이다.
개발/디버깅/작업 배정 응답을 하지 말고, report 생성에만 집중한다.

[report working state]
{working_state_text or "(report working state 없음)"}

[최근 report checkpoint]
{checkpoint_text or "(최근 checkpoint 없음)"}

[이전 report workspace 요약]
{prior_summary or "(이전 요약 없음)"}

[시스템 프롬프트]
{system_prompt}

[현재 입력 payload]
{user_content}
"""


def _build_report_working_state_text(
    working_state_repo: WorkingStateRepo,
) -> str:
    state = working_state_repo.get(_REPORT_WORKSPACE)
    if state is None:
        return ""

    lines: list[str] = []
    if state.current_goal:
        lines.append(f"current_goal: {state.current_goal}")
    if state.current_owner:
        lines.append(f"current_owner: {state.current_owner}")
    if state.next_action:
        lines.append(f"next_action: {state.next_action}")
    if state.last_user_correction:
        lines.append(f"last_user_correction: {state.last_user_correction}")
    if state.confirmed_decisions and state.confirmed_decisions != "[]":
        lines.append(f"confirmed_decisions: {state.confirmed_decisions}")
    if state.constraints and state.constraints != "[]":
        lines.append(f"constraints: {state.constraints}")
    if state.open_questions and state.open_questions != "[]":
        lines.append(f"open_questions: {state.open_questions}")
    return "\n".join(lines)


def _build_report_checkpoint_text(
    checkpoint_repo: CheckpointSummaryRepo,
    *,
    limit: int = 3,
) -> str:
    checkpoints = checkpoint_repo.list_recent(workspace=_REPORT_WORKSPACE, limit=limit)
    if not checkpoints:
        return ""
    lines: list[str] = []
    for cp in checkpoints:
        topic = cp.topic or cp.checkpoint_kind
        summary = cp.summary_text or cp.next_question or ""
        if summary:
            lines.append(f"- {topic}: {summary}")
    return "\n".join(lines)


def _update_report_working_state(
    working_state_repo: WorkingStateRepo,
    *,
    user_content: str,
    response_text: str,
) -> None:
    def _parse_json_list(raw: str | None) -> list[str]:
        if not raw:
            return []
        try:
            value = json.loads(raw)
            return [str(item).strip() for item in value if str(item).strip()]
        except Exception:
            return []

    def _dedupe_keep_order(items: list[str], limit: int = 5) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            normalized = item.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized[:280])
            if len(result) >= limit:
                break
        return result

    def _extract_line_matches(text: str, patterns: tuple[str, ...]) -> list[str]:
        matches: list[str] = []
        for raw_line in (text or "").splitlines():
            line = raw_line.strip(" -*\t")
            if not line:
                continue
            if any(pattern in line for pattern in patterns):
                matches.append(line)
        return matches

    existing = working_state_repo.get(_REPORT_WORKSPACE)

    next_action = ""
    for line in (response_text or "").splitlines():
        line = line.strip()
        if line:
            next_action = line[:280]
            break

    existing_decisions = _parse_json_list(existing.confirmed_decisions if existing else "[]")
    existing_constraints = _parse_json_list(existing.constraints if existing else "[]")
    existing_questions = _parse_json_list(existing.open_questions if existing else "[]")

    decision_candidates = _extract_line_matches(
        response_text,
        ("원칙", "구조", "compact", "축약", "유지", "통합", "노출하지 않"),
    )
    constraint_candidates = _extract_line_matches(
        response_text,
        ("금지", "제약", "본문", "노출하지 않", "직접 노출", "보조 블록"),
    )
    question_candidates = _extract_line_matches(
        response_text,
        ("미해결", "후속", "검토 필요", "확인 필요", "열린", "?"),
    )

    record = WorkingStateRecord(
        workspace=_REPORT_WORKSPACE,
        current_goal="Telegram report generation",
        active_parent_task=existing.active_parent_task if existing else "",
        active_leaf_task=existing.active_leaf_task if existing else "",
        current_owner=_ANALYZER_ROLE,
        confirmed_decisions=json.dumps(
            _dedupe_keep_order(existing_decisions + decision_candidates),
            ensure_ascii=False,
        ),
        constraints=json.dumps(
            _dedupe_keep_order(existing_constraints + constraint_candidates),
            ensure_ascii=False,
        ),
        open_questions=json.dumps(
            _dedupe_keep_order(existing_questions + question_candidates),
            ensure_ascii=False,
        ),
        next_action=next_action or (existing.next_action if existing else ""),
        last_user_correction=(user_content or "")[:280],
        created_at=existing.created_at if existing else _now_iso(),
    )
    working_state_repo.upsert(record)
    _sync_report_ledgers(
        source_ref="report_working_state",
        decision_items=_dedupe_keep_order(decision_candidates + constraint_candidates),
        open_question_items=_dedupe_keep_order(question_candidates),
        decision_repo=DecisionLedgerRepo(working_state_repo._db),
        issue_repo=IssueLedgerRepo(working_state_repo._db),
    )


def _topic_from_summary(summary: str, prefix: str) -> str:
    head = summary.split(":", 1)[0].strip() if ":" in summary else summary[:40].strip()
    head = re.sub(r"\s+", "_", head)
    head = re.sub(r"[^0-9A-Za-z가-힣_]+", "", head)
    return f"{prefix}:{head or 'general'}"


def _sync_report_ledgers(
    *,
    source_ref: str,
    decision_items: list[str],
    open_question_items: list[str],
    decision_repo: DecisionLedgerRepo,
    issue_repo: IssueLedgerRepo,
) -> None:
    active_decisions = {
        record.topic: record
        for record in decision_repo.list_active(_REPORT_WORKSPACE)
        if record.source_ref == source_ref
    }
    for summary in decision_items:
        topic = _topic_from_summary(summary, "decision")
        existing = active_decisions.get(topic)
        if existing and existing.decision_summary == summary:
            continue
        replacement = DecisionRecord(
            decision_id=str(uuid.uuid4()),
            workspace=_REPORT_WORKSPACE,
            topic=topic,
            decision_summary=summary,
            created_by="report_analyzer",
            source_kind="working_state",
            source_ref=source_ref,
        )
        if existing:
            decision_repo.supersede(existing.decision_id, replacement)
        else:
            decision_repo.create(replacement)

    active_issues = {
        record.topic: record
        for record in issue_repo.list_open(_REPORT_WORKSPACE)
        if record.source_ref == source_ref
    }
    desired_topics: set[str] = set()
    for summary in open_question_items:
        topic = _topic_from_summary(summary, "issue")
        desired_topics.add(topic)
        existing = active_issues.get(topic)
        if existing and existing.issue_summary == summary:
            continue
        replacement = IssueRecord(
            issue_id=str(uuid.uuid4()),
            workspace=_REPORT_WORKSPACE,
            topic=topic,
            issue_summary=summary,
            opened_by="report_analyzer",
            source_kind="working_state",
            source_ref=source_ref,
        )
        if existing:
            issue_repo.supersede(existing.issue_id, replacement)
        else:
            issue_repo.create(replacement)

    for topic, existing in active_issues.items():
        if topic not in desired_topics:
            issue_repo.resolve(existing.issue_id, "removed from working_state")


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
    working_state_repo = WorkingStateRepo(db_path)
    checkpoint_repo = CheckpointSummaryRepo(db_path)
    session = session_repo.get(_ANALYZER_ROLE, workspace=_REPORT_WORKSPACE)
    summary_record = conv_repo.get_summary(_ANALYZER_ROLE, workspace=_REPORT_WORKSPACE)
    prior_summary = summary_record.summary if summary_record else ""
    working_state_text = _build_report_working_state_text(working_state_repo)
    checkpoint_text = _build_report_checkpoint_text(checkpoint_repo)

    prompt = _build_report_analyzer_prompt(
        system_prompt=system_prompt,
        user_content=user_content,
        prior_summary=prior_summary,
        working_state_text=working_state_text,
        checkpoint_text=checkpoint_text,
    )
    codex_bin = _require_codex_bin()
    project_dir = _project_root()
    timeout_raw = os.getenv("REPORT_ANALYZER_TIMEOUT", "").strip()
    if timeout_raw.lower() in {"", "none", "null", "off", "false", "no", "0"}:
        timeout_secs: int | None = None
    else:
        timeout_secs = int(timeout_raw)

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
            session_repo.touch(_ANALYZER_ROLE, workspace=_REPORT_WORKSPACE)
            raw = response or result.stdout.strip()
            _update_analyzer_summary(conv_repo, raw, summary_record)
            _update_report_working_state(
                working_state_repo,
                user_content=user_content,
                response_text=raw,
            )
            return raw or None
        session_repo.set_status(_ANALYZER_ROLE, "broken", workspace=_REPORT_WORKSPACE)

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
                workspace="report",
                provider=_ANALYZER_PROVIDER,
                session_id=session_id,
                created_at=now,
                last_used_at=now,
                status="active",
            )
        )
    raw = response or result.stdout.strip()
    _update_analyzer_summary(conv_repo, raw, summary_record)
    _update_report_working_state(
        working_state_repo,
        user_content=user_content,
        response_text=raw,
    )
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
            workspace="report",
            summary=summary_payload,
            anchors=json.dumps(["workspace=report", "report_analyzer"], ensure_ascii=False),
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
    )
