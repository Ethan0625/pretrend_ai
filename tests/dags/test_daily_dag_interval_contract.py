from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_eod_daily_target_uses_data_interval_end() -> None:
    """Daily EOD run must not lag one market day behind Airflow's cron interval."""

    source = (ROOT / "dags" / "eod_pipeline_dag.py").read_text(encoding="utf-8")

    assert 'data_interval_end = context["data_interval_end"]' in source
    assert 'now_et = data_interval_end.in_tz("US/Eastern")' in source


def test_macro_daily_window_uses_data_interval_end_anchor() -> None:
    """Daily macro rolling window must include the latest completed scheduled day."""

    source = (ROOT / "dags" / "macro_pipeline_dag.py").read_text(encoding="utf-8")

    assert "anchor_date: date = data_interval_end.date()" in source
    assert "end_dt: date = anchor_date - timedelta(days=1)" in source


def test_strategy_engine_daily_decision_date_uses_interval_end() -> None:
    """Strategy snapshots feed regime similarity and must not lag one day behind."""

    source = (ROOT / "dags" / "strategy_engine_dag.py").read_text(encoding="utf-8")

    assert 'data_interval_end = context["data_interval_end"]' in source
    assert "decision_date = _last_us_trading_date(data_interval_end)" in source
    assert 'anchor_et = anchor.in_tz("US/Eastern")' in source
