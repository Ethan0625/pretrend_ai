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
    assert "execute_broker_orders" in task_ids
    assert "build_paper_result_payload" in task_ids
    assert "send_paper_result_telegram" in task_ids


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
    assert "fx_daily" in text
    assert "fx_usdkrw" in text
    assert "get_usdkrw_rate" in text
    assert "orderable_usd" in text
    assert "get_orderable_info" in text
    assert "orderable_krw_amt" in text
    assert "orderable_overseas_amt" in text


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
