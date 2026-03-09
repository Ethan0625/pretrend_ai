"""Tests for broker_mock_trading_dag — DAG structure and source code policy."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_module():
    pytest.importorskip("pendulum")
    repo_root = Path(__file__).resolve().parents[2]
    mod_path = repo_root / "dags" / "broker_mock_trading_dag.py"
    spec = importlib.util.spec_from_file_location("broker_mock_trading_dag_mod", mod_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_broker_mock_trading_dag_has_expected_tasks() -> None:
    dag = _load_module().broker_mock_trading_dag
    task_ids = set(dag.task_ids)
    assert "load_sim_ledger" in task_ids
    assert "execute_broker_orders" in task_ids
    assert "build_broker_result_payload" in task_ids
    assert "send_broker_telegram" in task_ids


def test_broker_mock_trading_dag_source_has_required_fields() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / "dags" / "broker_mock_trading_dag.py").read_text(encoding="utf-8")
    # Broker-specific fields must be present
    assert "KISMockAdapter" in text
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
    # Shared contract: reads from SIM execution_ledger
    assert "execution_mode=\"SIM\"" in text
    assert "execution_ledger" in text


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
    module = _load_module()
    import os
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
    module = _load_module()
    monkeypatch.delenv("KIS_MOCK_ACCOUNT_NO", raising=False)
    monkeypatch.delenv("KIS_LIVE_ACCOUNT_NO", raising=False)
    monkeypatch.delenv("KIS_ACCOUNT_NO", raising=False)
    monkeypatch.setenv("KIS_IS_MOCK", "true")
    assert module._resolve_account_id() == "UNKNOWN"
