from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from pretrend.pipeline.broker.kis_mock import KISMockAdapter
from pretrend.pipeline.broker.order_manager import execute_from_virtual_fills
from pretrend.pipeline.paper.io import save_decision_partition


def test_paper_broker_flow_saves_order_partition(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("KIS_MOCK_APP_KEY", "mock_key")
    monkeypatch.setenv("KIS_MOCK_APP_SECRET", "mock_secret")
    monkeypatch.setenv("KIS_MOCK_ACCOUNT_NO", "12345678")
    monkeypatch.setenv("KIS_IS_MOCK", "true")
    monkeypatch.setenv("KIS_DRY_RUN", "true")
    adapter = KISMockAdapter.from_env()  # default dry-run
    orders_df, warnings = execute_from_virtual_fills(
        adapter,
        virtual_fills=["SPY BUY $100.0", "IAU BUY $50.0"],
        decision_date=date(2026, 3, 5),
        simulation_date=date(2026, 3, 5),
        source_job="paper_trading_dag",
    )
    assert warnings == []
    assert not orders_df.empty

    out = save_decision_partition(
        orders_df,
        tmp_path / "paper" / "broker_orders",
        date(2026, 3, 5),
        "broker_orders",
    )
    assert out is not None
    loaded = pd.read_parquet(out)
    assert len(loaded) == len(orders_df)
    assert set(loaded.columns) >= {"symbol", "side", "qty", "status"}
