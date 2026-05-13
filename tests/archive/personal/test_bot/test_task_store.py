"""Tests for bot.task_store — SQLite schema, repos, restart recovery."""
import sqlite3
import uuid
from pathlib import Path

import pytest

from bot.task_store import (
    ApprovalRecord,
    ApprovalRepo,
    EventRepo,
    TaskRecord,
    TaskStatusRepo,
    TaskRepo,
    init_db,
)


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "test_orchestrator.db"
    init_db(p)
    return p


# ── TaskRepo ─────────────────────────────────────────────────────────────────

def test_task_create_and_get(db_path):
    repo = TaskRepo(db_path)
    task = TaskRecord(
        task_id=str(uuid.uuid4()),
        chat_id=123,
        description="테스트 작업",
        branch="codex/abc",
        worktree_path="/tmp/wt",
    )
    repo.create(task)
    fetched = repo.get(task.task_id)
    assert fetched is not None
    assert fetched.description == "테스트 작업"
    assert fetched.status == "queued"


def test_task_update_status(db_path):
    repo = TaskRepo(db_path)
    task = TaskRecord(task_id=str(uuid.uuid4()), chat_id=1, description="x")
    repo.create(task)
    repo.update(task.task_id, status="running")
    assert repo.get(task.task_id).status == "running"


def test_task_set_output_persists_raw_text(db_path):
    repo = TaskRepo(db_path)
    task = TaskRecord(task_id=str(uuid.uuid4()), chat_id=1, description="x")
    repo.create(task)

    output = "첫 줄\n둘째 줄\n"
    repo.set_output(task.task_id, output)

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT output FROM tasks WHERE task_id=?",
            (task.task_id,),
        ).fetchone()
    assert row is not None
    assert row[0] == output


def test_task_find_by_short_id(db_path):
    repo = TaskRepo(db_path)
    task = TaskRecord(task_id=str(uuid.uuid4()), chat_id=1, description="x")
    repo.create(task)
    found = repo.find_by_short_id(task.task_id[:8])
    assert found is not None
    assert found.task_id == task.task_id


def test_task_list_active(db_path):
    repo = TaskRepo(db_path)
    queued  = TaskRecord(task_id=str(uuid.uuid4()), chat_id=1, description="a", status="queued")
    running = TaskRecord(task_id=str(uuid.uuid4()), chat_id=1, description="b", status="running")
    done    = TaskRecord(task_id=str(uuid.uuid4()), chat_id=1, description="c", status="done")
    for t in (queued, running, done):
        repo.create(t)
    active = repo.list_active()
    ids = {t.task_id for t in active}
    assert queued.task_id in ids
    assert running.task_id in ids
    assert done.task_id not in ids


def test_task_list_needs_review(db_path):
    repo = TaskRepo(db_path)
    done_reviewed   = TaskRecord(task_id=str(uuid.uuid4()), chat_id=1, description="a",
                                  status="done", review_summary="ok")
    done_unreviewed = TaskRecord(task_id=str(uuid.uuid4()), chat_id=1, description="b",
                                  status="done", review_summary="")
    failed          = TaskRecord(task_id=str(uuid.uuid4()), chat_id=1, description="c",
                                  status="failed", review_summary="")
    for t in (done_reviewed, done_unreviewed, failed):
        repo.create(t)
    needs = {t.task_id for t in repo.list_needs_review()}
    assert done_unreviewed.task_id in needs
    assert failed.task_id in needs
    assert done_reviewed.task_id not in needs


def test_task_continuation_lineage(db_path):
    repo = TaskRepo(db_path)
    origin = TaskRecord(task_id=str(uuid.uuid4()), chat_id=1, description="origin")
    child  = TaskRecord(task_id=str(uuid.uuid4()), chat_id=1, description="child",
                        parent_task_id=origin.task_id, origin_task_id=origin.task_id)
    repo.create(origin)
    repo.create(child)
    fetched = repo.get(child.task_id)
    assert fetched.parent_task_id == origin.task_id
    assert fetched.origin_task_id == origin.task_id


def test_task_approval_notify_detection(db_path):
    task_repo  = TaskRepo(db_path)
    event_repo = EventRepo(db_path)

    t = TaskRecord(task_id=str(uuid.uuid4()), chat_id=1, description="x",
                   status="awaiting_approval")
    task_repo.create(t)

    # Before notification event → should appear in list
    needs = task_repo.list_needs_approval_notify()
    assert any(x.task_id == t.task_id for x in needs)

    # After appending 'approval_notified' event → should not appear
    event_repo.append(t.task_id, "approval_notified")
    needs2 = task_repo.list_needs_approval_notify()
    assert not any(x.task_id == t.task_id for x in needs2)


# ── TaskStatusRepo ───────────────────────────────────────────────────────────

def test_task_status_upsert_and_list_active(db_path):
    repo = TaskStatusRepo(db_path)
    repo.upsert("P9-2", "배정 전 확인", "TODO")
    repo.upsert("P9-3", "Codex output DB 저장", "DONE")
    repo.upsert("P4-1b", "daily_pnl 정밀화", "BACKLOG")

    active = repo.list_active()
    ids = {task.task_id for task in active}
    assert ids == {"P9-2", "P4-1b"}


def test_task_status_update_status(db_path):
    repo = TaskStatusRepo(db_path)
    repo.upsert("P9-5", "task_status DB", "TODO")

    repo.update_status("P9-5", "IN_PROGRESS")

    all_tasks = {task.task_id: task for task in repo.list_all()}
    assert all_tasks["P9-5"].status == "IN_PROGRESS"


# ── ApprovalRepo ─────────────────────────────────────────────────────────────

def test_approval_create_and_get_pending(db_path):
    task_repo = TaskRepo(db_path)
    task = TaskRecord(task_id=str(uuid.uuid4()), chat_id=1, description="x")
    task_repo.create(task)

    ar = ApprovalRecord(
        approval_id=str(uuid.uuid4()),
        task_id=task.task_id,
        question="진행해도 될까요?",
    )
    ApprovalRepo(db_path).create(ar)
    pending = ApprovalRepo(db_path).get_pending_for_task(task.task_id)
    assert pending is not None
    assert pending.question == "진행해도 될까요?"
    assert pending.decision_status == "pending"


def test_approval_respond(db_path):
    task_repo = TaskRepo(db_path)
    task = TaskRecord(task_id=str(uuid.uuid4()), chat_id=1, description="x")
    task_repo.create(task)

    ar = ApprovalRecord(
        approval_id=str(uuid.uuid4()),
        task_id=task.task_id,
        question="Q",
    )
    repo = ApprovalRepo(db_path)
    repo.create(ar)
    repo.respond(ar.approval_id, "approved", "승인합니다")

    fetched = repo.get(ar.approval_id)
    assert fetched.decision_status == "approved"
    assert fetched.user_response == "승인합니다"
    assert fetched.decided_at is not None


def test_approval_list_pending(db_path):
    task_repo = TaskRepo(db_path)
    repo = ApprovalRepo(db_path)

    for i in range(3):
        t = TaskRecord(task_id=str(uuid.uuid4()), chat_id=1, description=f"task {i}")
        task_repo.create(t)
        repo.create(ApprovalRecord(
            approval_id=str(uuid.uuid4()),
            task_id=t.task_id,
            question=f"Q{i}",
        ))

    pending = repo.list_pending()
    assert len(pending) == 3

    # Respond to one → only 2 pending
    repo.respond(pending[0].approval_id, "approved")
    assert len(repo.list_pending()) == 2


# ── EventRepo ────────────────────────────────────────────────────────────────

def test_event_append_and_list(db_path):
    task_repo  = TaskRepo(db_path)
    event_repo = EventRepo(db_path)

    t = TaskRecord(task_id=str(uuid.uuid4()), chat_id=1, description="x")
    task_repo.create(t)

    event_repo.append(t.task_id, "task_created", {"key": "val"})
    event_repo.append(t.task_id, "worker_started")

    events = event_repo.list_by_task(t.task_id)
    types  = [e.event_type for e in events]
    assert "task_created" in types
    assert "worker_started" in types


# ── Restart recovery ─────────────────────────────────────────────────────────

def test_restart_recovery_active_tasks(db_path):
    """Simulates bot restart: tasks created in one repo instance are
    visible in a fresh repo instance (same db_path)."""
    repo1 = TaskRepo(db_path)
    for i in range(2):
        t = TaskRecord(task_id=str(uuid.uuid4()), chat_id=1,
                       description=f"task {i}", status="running")
        repo1.create(t)

    # New repo instance (simulating restart)
    repo2 = TaskRepo(db_path)
    active = repo2.list_active()
    assert len(active) == 2


def test_init_db_migrates_legacy_tasks_output_column(tmp_path: Path):
    db_path = tmp_path / "legacy_orchestrator.db"
    created_at = "2026-03-23T00:00:00+00:00"

    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE tasks (
                task_id TEXT PRIMARY KEY,
                parent_task_id TEXT,
                origin_task_id TEXT,
                chat_id INTEGER NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL,
                intent TEXT NOT NULL DEFAULT 'RUN_CODEX',
                executor_type TEXT NOT NULL DEFAULT 'codex',
                status TEXT NOT NULL DEFAULT 'queued',
                branch TEXT NOT NULL DEFAULT '',
                worktree_path TEXT NOT NULL DEFAULT '',
                checkpoint_path TEXT NOT NULL DEFAULT '',
                result_summary TEXT NOT NULL DEFAULT '',
                review_summary TEXT NOT NULL DEFAULT '',
                retry_count INTEGER NOT NULL DEFAULT 0,
                cooldown_until TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                finished_at TEXT
            );
            """
        )
        conn.execute(
            """
            INSERT INTO tasks (
                task_id, chat_id, description, created_at, updated_at
            ) VALUES (?,?,?,?,?)
            """,
            (str(uuid.uuid4()), 1, "legacy", created_at, created_at),
        )
        conn.commit()

    init_db(db_path)

    with sqlite3.connect(db_path) as conn:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()
        }
        row = conn.execute("SELECT output FROM tasks").fetchone()

    assert "output" in columns
    assert row is not None
    assert row[0] == "처리완료 (출력 없음)"
