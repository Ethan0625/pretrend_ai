from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_module():
    pytest.importorskip("pendulum")
    repo_root = Path(__file__).resolve().parents[2]
    mod_path = repo_root / "dags" / "paper_trading_dag.py"
    spec = importlib.util.spec_from_file_location("paper_trading_dag_mod", mod_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_paper_trading_dag_has_expected_tasks() -> None:
    paper_trading_dag = _load_module().paper_trading_dag
    task_ids = set(paper_trading_dag.task_ids)
    assert "build_paper_execution" in task_ids
    assert "build_paper_result_payload" in task_ids
    assert "send_paper_result_telegram" in task_ids
    assert "execute_broker_orders" not in task_ids


def test_paper_payload_includes_gate_strength_fields_in_dag_source() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / "dags" / "paper_trading_dag.py").read_text(encoding="utf-8")
    assert "load_next_step_for_date" in text
    assert "effective_bias=" in text
    assert "bias_source=" in text
    assert "hard_gate_run_universe=" in text
    assert "hard_gate_risk_gate=" in text
    assert "effective_max_tactical_slots=" in text
    assert "effective_tactical_weight=" in text
    assert "hazard_10d=" in text
    assert "group_gate_applied_groups=" in text
    assert "group_gate_reduced_groups=" in text
    assert "group_gate_source=" in text
    assert "execution_mode=" in text
    assert "capital_source=" in text
    assert "broker_source=" in text
    assert "account_id=" in text
    assert "nav_source=" in text
    assert "fx_usdkrw" in text
    # broker-specific fields must NOT be in paper DAG (moved to broker_mock_trading_dag)
    assert "fx_daily" not in text
    assert "get_usdkrw_rate" not in text
    assert "orderable_usd" not in text
    assert "get_orderable_info" not in text
    assert "KISMockAdapter" not in text
    assert "execute_from_ledger_rows" not in text


def test_telegram_mode_policy_is_fixed_in_source() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / "dags" / "paper_trading_dag.py").read_text(encoding="utf-8")
    # SIM-only: always save and send a single SIM payload, no mode branching.
    assert "save_paper_result_payload(payload)" in text
    assert "source_job=\"paper_trading_sim\"" in text
    # Must NOT have MOCK/compare mode branching in paper DAG.
    assert "PAPER_TELEGRAM_MODE" not in text
    assert "paper_trading_mock" not in text
    assert "paper_trading_compare" not in text


def test_resolve_paper_capital_params_default() -> None:
    module = _load_module()
    vals = module._resolve_paper_capital_params()
    assert vals["initial_capital_krw"] == 1_000_000.0
    assert vals["monthly_addition_krw"] == 300_000.0
    assert vals["fx_usdkrw"] == 1300.0
    assert abs(vals["initial_capital_usd"] - (1_000_000.0 / 1300.0)) < 1e-9


def test_resolve_paper_capital_params_invalid_fx(monkeypatch) -> None:
    module = _load_module()
    monkeypatch.setenv("PAPER_INITIAL_CAPITAL_KRW", "2000000")
    monkeypatch.setenv("PAPER_MONTHLY_ADDITION_KRW", "400000")
    monkeypatch.setenv("PAPER_FX_USDKRW", "-1")
    vals = module._resolve_paper_capital_params()
    assert vals["initial_capital_krw"] == 2_000_000.0
    assert vals["monthly_addition_krw"] == 400_000.0
    assert vals["fx_usdkrw"] == 1300.0
