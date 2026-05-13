"""Tests for bot.policy_engine — pre-execution and post-change checks."""
import subprocess
from pathlib import Path

import pytest

from bot.policy_engine import Decision, post_change_check, pre_execution_check


# ── pre_execution_check ───────────────────────────────────────────────────────

@pytest.mark.parametrize("desc", [
    "rm -rf /data",
    "DROP TABLE users",
    "git push --force origin main",
    "git push -f main",
    "git reset --hard HEAD~5",
    "프로덕션 파일 삭제",
    "DB 전체 삭제",
])
def test_pre_execution_deny(desc):
    decision, reason = pre_execution_check(desc)
    assert decision == Decision.DENY, f"Expected DENY for: {desc!r}"


@pytest.mark.parametrize("desc", [
    "broker 주문 로직 수정",
    "paper_trading DAG 변경",
    "strategy_engine_design.md 업데이트",
    "migration 추가",
    "실 api 호출 구현",
    "broker 모듈 리팩토링",
])
def test_pre_execution_require_approval(desc):
    decision, reason = pre_execution_check(desc)
    assert decision == Decision.REQUIRE_APPROVAL, f"Expected REQUIRE_APPROVAL for: {desc!r}"


@pytest.mark.parametrize("desc", [
    "tests/bot/test_foo.py 추가",
    "CHANGELOG 업데이트",
    "report_context.py 리팩토링",
    "주석 추가",
    "로그 레벨 변경",
])
def test_pre_execution_allow(desc):
    decision, reason = pre_execution_check(desc)
    assert decision == Decision.ALLOW, f"Expected ALLOW for: {desc!r}"


# ── post_change_check ─────────────────────────────────────────────────────────

def test_post_change_no_diff(tmp_path):
    """If git diff returns nothing → ALLOW."""
    # In a temp path that is not a git repo, git will fail → should return ALLOW
    decision, reason, files = post_change_check(tmp_path, "origin/dev")
    assert decision == Decision.ALLOW


def test_post_change_sensitive_files(monkeypatch, tmp_path):
    """Patch subprocess.run to simulate sensitive file changes."""
    def fake_run(cmd, **kwargs):
        class R:
            stdout = "docs/architecture/text_observability_contract.md\nsrc/foo.py\n"
            returncode = 0
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    decision, reason, files = post_change_check(tmp_path, "origin/dev")
    assert decision == Decision.REQUIRE_APPROVAL
    assert "docs/architecture/" in reason or "text_observability_contract" in reason


def test_post_change_safe_files(monkeypatch, tmp_path):
    """Only safe files changed → ALLOW."""
    def fake_run(cmd, **kwargs):
        class R:
            stdout = "tests/bot/test_foo.py\nsrc/pretrend/pipeline/features/macro.py\n"
            returncode = 0
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    decision, reason, files = post_change_check(tmp_path, "origin/dev")
    assert decision == Decision.ALLOW
    assert len(files) == 2


def test_post_change_broker_files(monkeypatch, tmp_path):
    def fake_run(cmd, **kwargs):
        class R:
            stdout = "src/pretrend/pipeline/broker/order_manager.py\n"
            returncode = 0
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    decision, reason, files = post_change_check(tmp_path, "origin/dev")
    assert decision == Decision.REQUIRE_APPROVAL


def test_post_change_dag_files(monkeypatch, tmp_path):
    def fake_run(cmd, **kwargs):
        class R:
            stdout = "dags/strategy_engine_dag.py\n"
            returncode = 0
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    decision, reason, files = post_change_check(tmp_path, "origin/dev")
    assert decision == Decision.REQUIRE_APPROVAL
