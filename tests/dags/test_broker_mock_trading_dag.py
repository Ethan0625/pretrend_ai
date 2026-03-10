"""Tests for broker_mock_trading_dag — DAG structure and source code policy."""
from __future__ import annotations

import ast
import os
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo
from datetime import datetime

import pytest


class _FakePendulumDateTime:
    def __init__(self, dt: datetime) -> None:
        self._dt = dt

    def in_timezone(self, tz: ZoneInfo) -> "_FakePendulumDateTime":
        return _FakePendulumDateTime(self._dt.astimezone(tz))

    @property
    def day_of_week(self) -> int:
        return self._dt.weekday()

    def replace(self, **kwargs) -> "_FakePendulumDateTime":
        return _FakePendulumDateTime(self._dt.replace(**kwargs))

    def __lt__(self, other: "_FakePendulumDateTime") -> bool:
        return self._dt < other._dt

    def __gt__(self, other: "_FakePendulumDateTime") -> bool:
        return self._dt > other._dt


class _FakePendulumModule:
    DateTime = _FakePendulumDateTime

    @staticmethod
    def timezone(name: str) -> ZoneInfo:
        return ZoneInfo(name)

    @staticmethod
    def datetime(year: int, month: int, day: int, hour: int, minute: int, tz: str) -> _FakePendulumDateTime:
        return _FakePendulumDateTime(datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(tz)))

    @staticmethod
    def now(tz: ZoneInfo) -> _FakePendulumDateTime:
        return _FakePendulumDateTime(datetime.now(tz))


def _load_helpers():
    repo_root = Path(__file__).resolve().parents[2]
    src = (repo_root / "dags" / "broker_mock_trading_dag.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    selected = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == "_ET_TZ" for t in node.targets):
                selected.append(node)
        if isinstance(node, ast.FunctionDef) and node.name in {
            "_resolve_broker_source",
            "_resolve_account_id",
            "_should_skip_market_hours",
        }:
            selected.append(node)
    mod = ast.Module(body=selected, type_ignores=[])
    ast.fix_missing_locations(mod)
    ns = {"os": os, "pendulum": _FakePendulumModule(), "ZoneInfo": ZoneInfo, "datetime": datetime}
    exec(compile(mod, "<broker_mock_helpers>", "exec"), ns)
    return SimpleNamespace(**ns)


def test_broker_mock_trading_dag_has_expected_tasks() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / "dags" / "broker_mock_trading_dag.py").read_text(encoding="utf-8")
    assert '@task(task_id="load_sim_ledger")' in text
    assert '@task(task_id="execute_broker_orders")' in text
    assert '@task(task_id="build_broker_result_payload")' in text
    assert '@task(task_id="send_broker_telegram")' in text


def test_broker_mock_trading_dag_source_has_required_fields() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / "dags" / "broker_mock_trading_dag.py").read_text(encoding="utf-8")
    # Broker-specific fields must be present
    assert "KISMockAdapter" in text
    assert "build_broker_target_orders" in text
    assert "execute_from_ledger_rows" in text
    assert "reconcile_positions" in text
    assert "execution_mode=\"MOCK\"" in text
    assert "capital_source=\"BROKER_BALANCE\"" in text
    assert "nav_source=\"BROKER_SNAPSHOT\"" in text
    assert "broker_source=" in text
    assert "account_id=" in text
    assert "fx_daily" in text
    assert "fx_usdkrw" in text
    assert "orderable_usd" in text
    assert "get_orderable_info" in text
    assert "broker_mock_trading_dag" in text
    # P4-2b: no SIM execution_ledger dependency
    assert "qty_scale_factor" not in text
    assert 'paper_root / "execution_ledger"' not in text
    assert 'execution_mode="SIM"' not in text
    assert 'paper_root / "broker_fills"' in text


def test_broker_mock_dag_does_not_import_paper_trading_dag_helpers() -> None:
    """broker_mock_trading_dag is independent of paper_trading_dag module."""
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / "dags" / "broker_mock_trading_dag.py").read_text(encoding="utf-8")
    assert "from dags.paper_trading_dag import" not in text
    assert "import paper_trading_dag" not in text


def test_broker_mock_telegram_sends_mock_source_job() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / "dags" / "broker_mock_trading_dag.py").read_text(encoding="utf-8")
    # Telegram is sent with broker_mock_trading_dag source_job
    assert "source_job=\"broker_mock_trading_dag\"" in text
    # SIM source_job must NOT appear in broker_mock DAG telegram
    assert "source_job=\"paper_trading_sim\"" not in text
    assert "source_job=\"paper_trading_compare\"" not in text


def test_resolve_broker_source() -> None:
    module = _load_helpers()
    orig = os.environ.get("KIS_IS_MOCK")
    try:
        os.environ["KIS_IS_MOCK"] = "true"
        assert module._resolve_broker_source() == "KIS_MOCK"
        os.environ["KIS_IS_MOCK"] = "false"
        assert module._resolve_broker_source() == "KIS_LIVE"
    finally:
        if orig is None:
            os.environ.pop("KIS_IS_MOCK", None)
        else:
            os.environ["KIS_IS_MOCK"] = orig


def test_resolve_account_id_unknown_when_no_env(monkeypatch) -> None:
    module = _load_helpers()
    monkeypatch.delenv("KIS_MOCK_ACCOUNT_NO", raising=False)
    monkeypatch.delenv("KIS_LIVE_ACCOUNT_NO", raising=False)
    monkeypatch.delenv("KIS_ACCOUNT_NO", raising=False)
    monkeypatch.setenv("KIS_IS_MOCK", "true")
    assert module._resolve_account_id() == "UNKNOWN"


def test_market_hours_gate_allows_regular_session(monkeypatch) -> None:
    module = _load_helpers()
    monkeypatch.delenv("BROKER_SKIP_MARKET_HOURS_CHECK", raising=False)
    now_et = module.pendulum.datetime(2026, 3, 9, 10, 0, tz="America/New_York")  # Monday
    should_skip, reason, bypassed = module._should_skip_market_hours(now_et)
    assert should_skip is False
    assert reason is None
    assert bypassed is False


def test_market_hours_gate_skips_premarket(monkeypatch) -> None:
    module = _load_helpers()
    monkeypatch.delenv("BROKER_SKIP_MARKET_HOURS_CHECK", raising=False)
    now_et = module.pendulum.datetime(2026, 3, 9, 8, 45, tz="America/New_York")  # Monday
    should_skip, reason, bypassed = module._should_skip_market_hours(now_et)
    assert should_skip is True
    assert reason == "장외 시간"
    assert bypassed is False


def test_market_hours_gate_skips_weekend(monkeypatch) -> None:
    module = _load_helpers()
    monkeypatch.delenv("BROKER_SKIP_MARKET_HOURS_CHECK", raising=False)
    now_et = module.pendulum.datetime(2026, 3, 8, 10, 0, tz="America/New_York")  # Sunday
    should_skip, reason, bypassed = module._should_skip_market_hours(now_et)
    assert should_skip is True
    assert reason == "장외 시간"
    assert bypassed is False


def test_market_hours_gate_bypass_env(monkeypatch) -> None:
    module = _load_helpers()
    monkeypatch.setenv("BROKER_SKIP_MARKET_HOURS_CHECK", "1")
    now_et = module.pendulum.datetime(2026, 3, 8, 10, 0, tz="America/New_York")  # Sunday
    should_skip, reason, bypassed = module._should_skip_market_hours(now_et)
    assert should_skip is False
    assert reason is None
    assert bypassed is True


def test_broker_mock_payload_source_has_approximate_metrics_and_empty_position_message() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / "dags" / "broker_mock_trading_dag.py").read_text(encoding="utf-8")
    assert "_estimate_total_invested_capital_usd" in text
    assert "포지션 없음(당일 미체결 가능성)" in text
    assert "전일 브로커 스냅샷 부재로 당일 수익률은 0.0% 근사치로 표시됩니다" in text


def test_broker_mock_payload_uses_broker_fills_and_exposure_action() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / "dags" / "broker_mock_trading_dag.py").read_text(encoding="utf-8")
    assert 'load_decision_partition(\n            data_root / "paper" / "broker_fills"' in text
    assert 'action = str(broker_meta.get("action", "HOLD")).upper()' in text
    assert 'next_invested_ratio=float(broker_meta.get("next_invested_ratio", next_ratio))' in text
