from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pandas as pd

from pretrend.pipeline.backtest.config import BacktestConfig
from pretrend.pipeline.backtest.report import save_result
from pretrend.pipeline.utils.result_registry import query_registry


class _Trade:
    def __init__(self, trade_date, symbol, action, shares, price, amount):
        self.trade_date = trade_date
        self.symbol = symbol
        self.action = action
        self.shares = shares
        self.price = price
        self.amount = amount


def test_save_result_writes_standard_artifacts_and_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("PRETREND_RESULT_ROOT", str(tmp_path / "result"))
    cfg = BacktestConfig.from_preset("v2", start_date=date(2025, 1, 1), end_date=date(2025, 1, 10))
    idx = pd.to_datetime(["2025-01-01", "2025-01-02"])
    daily_log = pd.DataFrame(
        {"nav": [1000.0, 1010.0], "benchmark_nav": [1000.0, 1005.0], "action": ["HOLD", "INCREASE"]},
        index=idx,
    )
    result = SimpleNamespace(
        config=cfg,
        daily_log=daily_log,
        trade_log=[_Trade(date(2025, 1, 2), "SPY", "BUY", 1.0, 500.0, 500.0)],
        metrics={"cagr": 0.1, "total_return": 0.01, "max_drawdown": -0.02, "sharpe_ratio": 1.2},
        final_positions={"SPY": {"shares": 1.0, "price": 500.0, "value": 500.0, "weight": 0.5}},
    )

    out_dir = save_result(result)
    assert out_dir is not None
    files = list(out_dir.glob("*"))
    names = [f.name for f in files]
    assert any(n.endswith("_daily_nav.parquet") for n in names)
    assert any(n.endswith("_summary_metrics.parquet") for n in names)
    assert any(n.endswith("_diagnostics.parquet") for n in names)
    assert any(n.endswith("_final_positions.parquet") for n in names)

    reg = query_registry(tmp_path / "result" / "backtest" / "registry", pipeline="backtest")
    assert not reg.empty
    assert reg.iloc[-1]["preset"] == "v2"
