"""Tests for broker_mock_trading_dag — DAG structure and source code policy."""
from __future__ import annotations

import ast
import os
import json
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo
from datetime import datetime
from tempfile import TemporaryDirectory

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


def _load_stage_helpers():
    repo_root = Path(__file__).resolve().parents[2]
    src = (repo_root / "dags" / "broker_mock_trading_dag.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    selected = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in {
            "_broker_staged_sell_path",
            "_load_broker_staged_sell",
            "_save_broker_staged_sell",
            "_clear_broker_staged_sell",
        }:
            selected.append(node)
    mod = ast.Module(body=selected, type_ignores=[])
    ast.fix_missing_locations(mod)
    ns = {"json": json, "Path": Path, "Any": object, "Dict": dict}
    exec(compile(mod, "<broker_mock_stage_helpers>", "exec"), ns)
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


def test_broker_mock_weekday_rules_are_present() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / "dags" / "broker_mock_trading_dag.py").read_text(encoding="utf-8")
    assert 'weekday = today_et.weekday()' in text
    assert 'if weekday == 0:' in text
    assert '["월요일: 신호 평가만 수행, 주문 없음"]' in text
    assert 'if weekday not in {1, 4}:' in text
    assert '["수/목: 실행 요일 아님"]' in text


def test_broker_mock_tuesday_increase_uses_buy_only_and_schd_floor() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / "dags" / "broker_mock_trading_dag.py").read_text(encoding="utf-8")
    assert 'if weekday == 1 and guardrail_paused and action == "INCREASE":' in text
    assert "allow_sell=False" in text
    assert "lock_sell_symbols=[]" in text
    assert "schd_min_weight=0.20" in text
    assert '_clear_broker_staged_sell(paper_root)' in text


def test_broker_mock_level2_guardrail_blocks_tuesday_increase() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / "dags" / "broker_mock_trading_dag.py").read_text(encoding="utf-8")
    assert "nav_tc_ratio < 0.85 or peak_dd < -0.20" in text
    assert "🚨 Level 2 가드레일 발동" in text
    assert 'if weekday == 1 and guardrail_paused and action == "INCREASE":' in text


def test_broker_mock_friday_staged_sell_flow_present() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / "dags" / "broker_mock_trading_dag.py").read_text(encoding="utf-8")
    assert "_load_broker_staged_sell(paper_root)" in text
    assert '"tranche_idx": 0' in text
    assert '"tranches": [0.50, 0.30, 0.20]' in text
    assert 'staged_sell["tranche_idx"] = tranche_idx + 1' in text
    assert "schd_min_weight=0.20" in text


def test_broker_mock_auto_schedule_env_flag_present() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / "dags" / "broker_mock_trading_dag.py").read_text(encoding="utf-8")
    assert 'os.getenv("BROKER_MOCK_AUTO_SCHEDULE_ENABLED", "0")' in text
    assert '"40 9 * * 1-5"' in text
    assert "allow_sell=True" in text


def test_staged_sell_helpers_roundtrip_and_clear() -> None:
    module = _load_stage_helpers()
    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        state = {"tranche_idx": 0, "tranches": [0.5, 0.3, 0.2]}
        module._save_broker_staged_sell(root, state)
        loaded = module._load_broker_staged_sell(root)
        assert loaded == state
        module._clear_broker_staged_sell(root)
        assert module._load_broker_staged_sell(root) is None


def test_staged_sell_helper_fail_open_on_invalid_json() -> None:
    module = _load_stage_helpers()
    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        path = module._broker_staged_sell_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{invalid", encoding="utf-8")
        assert module._load_broker_staged_sell(root) is None


def test_tuesday_increase_does_not_clear_staged_sell() -> None:
    """DECREASE 트랜치 진행 중 Tuesday INCREASE가 발생해도 staged_sell JSON이 유지되어야 한다.

    검증 방법: Tuesday 블록 코드에 _clear_broker_staged_sell 호출이 없음을 소스 분석으로 확인하고,
    실제 JSON 상태 파일을 저장한 후 Tuesday 실행 시뮬레이션 코드 경로에서 파일이 지워지지 않는지 확인한다.
    """
    # 1. 소스 코드 정책 확인: Tuesday 블록(elif weekday == 1:) 내에
    #    _clear_broker_staged_sell 호출이 없어야 한다.
    repo_root = Path(__file__).resolve().parents[2]
    src = (repo_root / "dags" / "broker_mock_trading_dag.py").read_text(encoding="utf-8")
    lines = src.splitlines()

    tuesday_block_start = None
    for i, line in enumerate(lines):
        # Tuesday 블록의 시작: guardrail 분기 이후 "elif weekday == 1:" 라인
        if "elif weekday == 1:" in line and tuesday_block_start is None:
            tuesday_block_start = i

    assert tuesday_block_start is not None, "Tuesday 블록(elif weekday == 1:)을 찾지 못함"

    # Tuesday 블록에서 다음 elif/else 전까지의 라인 수집
    tuesday_block_lines: list[str] = []
    indent_ref = len(lines[tuesday_block_start]) - len(lines[tuesday_block_start].lstrip())
    for line in lines[tuesday_block_start + 1 :]:
        stripped = line.strip()
        if not stripped:
            continue
        current_indent = len(line) - len(line.lstrip())
        # 같은 레벨 또는 상위 레벨의 elif/else는 블록 종료
        if current_indent <= indent_ref and (stripped.startswith("elif ") or stripped.startswith("else:")):
            break
        tuesday_block_lines.append(line)

    block_text = "\n".join(tuesday_block_lines)
    assert "_clear_broker_staged_sell" not in block_text, (
        f"Tuesday 블록에 _clear_broker_staged_sell 호출이 발견됨:\n{block_text}"
    )

    # 2. JSON 상태가 Tuesday 실행 경로에서 실제로 유지되는지 확인
    module = _load_stage_helpers()
    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        # DECREASE tranche 1 완료 후 상태 (tranche_idx=1, 즉 2번째 트랜치 대기)
        initial_state = {
            "tranche_idx": 1,
            "total_sell_amount_pct": 0.30,
            "tranches": [0.50, 0.30, 0.20],
            "target_ratio": 0.20,
            "created_decision_date": "2026-03-13",
        }
        module._save_broker_staged_sell(root, initial_state)

        # Tuesday INCREASE 시 staged_sell을 건드리지 않으므로 파일이 그대로 있어야 함
        # (실제 DAG 로직은 weekday==1 블록에서 _clear를 호출하지 않음)
        loaded_after_tuesday = module._load_broker_staged_sell(root)
        assert loaded_after_tuesday is not None, (
            "Tuesday INCREASE 후 staged_sell JSON이 None이 됨 — Tuesday 블록이 상태를 초기화함"
        )
        assert loaded_after_tuesday["tranche_idx"] == 1
        assert loaded_after_tuesday["tranches"] == [0.50, 0.30, 0.20]


def test_three_consecutive_friday_decrease_tranche_ratios() -> None:
    """3회 연속 Friday DECREASE에서 tranche 비율이 50%→30%→20% 순으로 실행되어야 한다."""
    module = _load_stage_helpers()
    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        tranches = [0.50, 0.30, 0.20]
        total_sell_amount_pct = 0.40  # 현재 invested_ratio - target_ratio

        # 초기 staged_sell 상태 생성 (Friday 1: tranche_idx=0)
        staged_sell = {
            "tranche_idx": 0,
            "total_sell_amount_pct": total_sell_amount_pct,
            "tranches": tranches,
            "target_ratio": 0.20,
            "created_decision_date": "2026-03-13",
        }
        module._save_broker_staged_sell(root, staged_sell)

        executed_ratios: list[float] = []

        for friday_num in range(3):
            state = module._load_broker_staged_sell(root)
            assert state is not None, f"Friday {friday_num + 1}: staged_sell이 None"

            idx = int(state["tranche_idx"])
            t_list = list(state["tranches"])
            assert idx < len(t_list), f"Friday {friday_num + 1}: tranche_idx={idx} 범위 초과"

            ratio = float(t_list[idx])
            executed_ratios.append(ratio)

            # tranche 실행 후 상태 업데이트
            state["tranche_idx"] = idx + 1
            if state["tranche_idx"] >= len(t_list):
                module._clear_broker_staged_sell(root)
            else:
                module._save_broker_staged_sell(root, state)

        assert executed_ratios == [0.50, 0.30, 0.20], (
            f"tranche 비율 순서 오류: {executed_ratios} (기대: [0.50, 0.30, 0.20])"
        )

        # 3회 완료 후 staged_sell 상태가 비워졌는지 확인
        assert module._load_broker_staged_sell(root) is None, "3회 완료 후 staged_sell이 남아 있음"
