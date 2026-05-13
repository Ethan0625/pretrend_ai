"""Tests for bot.intent_router classification behavior."""

from pathlib import Path

import pytest

from bot import intent_router
from bot.intent_router import Intent, RouterContext, route


def ctx(**kwargs) -> RouterContext:
    return RouterContext(**kwargs)


@pytest.fixture()
def fake_db_path(tmp_path: Path) -> Path:
    return tmp_path / "orchestrator.db"


def test_slash_task_status_stays_regex(monkeypatch: pytest.MonkeyPatch, fake_db_path: Path):
    called = {"count": 0}

    def _fake_classifier(*args, **kwargs):
        called["count"] += 1
        return Intent.ANSWER_ONLY.value

    monkeypatch.setattr(intent_router, "_classify_with_codex", _fake_classifier)

    result = route("/task_status", ctx(), fake_db_path)

    assert result == Intent.TASK_STATUS_QUERY
    assert called["count"] == 0


def test_pending_approval_stays_regex(monkeypatch: pytest.MonkeyPatch, fake_db_path: Path):
    called = {"count": 0}

    def _fake_classifier(*args, **kwargs):
        called["count"] += 1
        return Intent.ANSWER_ONLY.value

    monkeypatch.setattr(intent_router, "_classify_with_codex", _fake_classifier)

    result = route("승인합니다", ctx(has_pending_approval=True), fake_db_path)

    assert result == Intent.ASK_APPROVAL
    assert called["count"] == 0


def test_natural_language_uses_codex_classifier(monkeypatch: pytest.MonkeyPatch, fake_db_path: Path):
    monkeypatch.setattr(
        intent_router,
        "_classify_with_codex",
        lambda text, ctx, db_path=None: Intent.RUN_CODEX,
    )

    result = route("codex에 배정하지말고 직접 해줘", ctx(), fake_db_path)

    assert result == Intent.RUN_CODEX


def test_classifier_failure_falls_back_to_answer_only(
    monkeypatch: pytest.MonkeyPatch, fake_db_path: Path
):
    def _boom(*args, **kwargs):
        raise RuntimeError("classifier unavailable")

    monkeypatch.setattr(intent_router, "_classify_with_codex", _boom)
    monkeypatch.setattr(intent_router, "_legacy_natural_language_route", lambda text: Intent.ANSWER_ONLY)

    result = route("안녕하세요", ctx(), fake_db_path)

    assert result == Intent.ANSWER_ONLY


def test_classifier_invalid_output_falls_back_to_legacy(
    monkeypatch: pytest.MonkeyPatch, fake_db_path: Path
):
    monkeypatch.setattr(intent_router, "_classify_with_codex", lambda *args, **kwargs: None)
    monkeypatch.setattr(intent_router, "_legacy_natural_language_route", lambda text: Intent.PLAN_TASK)

    result = route("작업 계획을 정리해줘", ctx(), fake_db_path)

    assert result == Intent.PLAN_TASK


def test_classifier_receives_db_path(monkeypatch: pytest.MonkeyPatch, fake_db_path: Path):
    seen: dict[str, object] = {}

    def _fake_classifier(text, ctx_obj, db_path=None):
        seen["text"] = text
        seen["ctx"] = ctx_obj
        seen["db_path"] = db_path
        return Intent.STATUS_QUERY

    monkeypatch.setattr(intent_router, "_classify_with_codex", _fake_classifier)

    result = route("현재 작업 현황 알려줘", ctx(running_task_count=2), fake_db_path)

    assert result == Intent.STATUS_QUERY
    assert seen["text"] == "현재 작업 현황 알려줘"
    assert seen["ctx"].running_task_count == 2
    assert seen["db_path"] == fake_db_path
