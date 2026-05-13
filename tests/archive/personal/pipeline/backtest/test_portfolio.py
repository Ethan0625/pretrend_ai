"""Portfolio + Position 단위 테스트."""
from datetime import date

import pytest

from pretrend.pipeline.backtest.portfolio import Portfolio, Position, Trade


class TestPosition:
    def test_market_value(self):
        pos = Position(symbol="SPY", shares=10.0, avg_cost=100.0)
        assert pos.market_value(110.0) == 1100.0
        assert pos.cost_basis == 1000.0

    def test_zero_shares(self):
        pos = Position(symbol="SPY", shares=0.0)
        assert pos.market_value(100.0) == 0.0


class TestPortfolio:
    def test_initial_cash(self):
        pf = Portfolio(cash=1000.0)
        assert pf.cash == 1000.0
        assert pf.total_value({}) == 1000.0
        assert pf.invested_ratio({}) == 0.0

    def test_buy(self):
        pf = Portfolio(cash=1000.0)
        t = pf.buy("SPY", 500.0, 100.0)
        assert t is not None
        assert t.action == "BUY"
        assert t.shares == 5.0
        assert pf.cash == 500.0
        assert pf.positions["SPY"].shares == 5.0

    def test_buy_exceeds_cash(self):
        pf = Portfolio(cash=100.0)
        t = pf.buy("SPY", 200.0, 50.0)
        assert t is not None
        assert t.amount == 100.0  # capped to cash
        assert pf.cash == pytest.approx(0.0)

    def test_buy_zero(self):
        pf = Portfolio(cash=100.0)
        assert pf.buy("SPY", 0.0, 100.0) is None
        assert pf.buy("SPY", 50.0, 0.0) is None

    def test_sell(self):
        pf = Portfolio(cash=0.0)
        pf.positions["SPY"] = Position("SPY", shares=10.0, avg_cost=100.0)
        t = pf.sell("SPY", 500.0, 110.0)
        assert t is not None
        assert t.action == "SELL"
        assert t.shares == pytest.approx(500.0 / 110.0)
        assert pf.cash == pytest.approx(500.0)

    def test_sell_all(self):
        pf = Portfolio(cash=0.0)
        pf.positions["SPY"] = Position("SPY", shares=5.0, avg_cost=100.0)
        t = pf.sell("SPY", 9999.0, 100.0)
        assert t is not None
        assert t.amount == 500.0  # capped to holdings
        assert pf.positions["SPY"].shares == 0.0
        assert pf.cash == 500.0

    def test_sell_nonexistent(self):
        pf = Portfolio(cash=100.0)
        assert pf.sell("SPY", 50.0, 100.0) is None

    def test_total_value(self):
        pf = Portfolio(cash=400.0)
        pf.positions["SPY"] = Position("SPY", shares=3.0, avg_cost=100.0)
        pf.positions["IAU"] = Position("IAU", shares=10.0, avg_cost=20.0)
        prices = {"SPY": 110.0, "IAU": 22.0}
        assert pf.total_value(prices) == 400.0 + 330.0 + 220.0

    def test_invested_ratio(self):
        pf = Portfolio(cash=400.0)
        pf.positions["SPY"] = Position("SPY", shares=6.0, avg_cost=100.0)
        prices = {"SPY": 100.0}
        # invested=600, total=1000 → 0.6
        assert pf.invested_ratio(prices) == pytest.approx(0.6)

    def test_rebalance_to_weights(self):
        pf = Portfolio(cash=400.0)
        pf.positions["SPY"] = Position("SPY", shares=6.0, avg_cost=100.0)
        prices = {"SPY": 100.0, "IAU": 50.0}

        # 목표: invested $600, SPY 80% IAU 20%
        trades = pf.rebalance_to_weights(
            target_weights={"SPY": 0.80, "IAU": 0.20},
            prices=prices,
            target_invested_amount=600.0,
            trade_date=date(2024, 1, 2),
        )

        assert len(trades) > 0
        # SPY: 600*0.8=480 (현재 600 → 120 매도)
        # IAU: 600*0.2=120 (현재 0 → 120 매수)
        spy_val = pf.positions["SPY"].market_value(100.0)
        iau_val = pf.positions.get("IAU", Position("IAU")).market_value(50.0)
        assert spy_val == pytest.approx(480.0, abs=1.0)
        assert iau_val == pytest.approx(120.0, abs=1.0)

    def test_rebalance_removes_extra_positions(self):
        pf = Portfolio(cash=100.0)
        pf.positions["SPY"] = Position("SPY", shares=5.0, avg_cost=100.0)
        pf.positions["XLK"] = Position("XLK", shares=2.0, avg_cost=50.0)
        prices = {"SPY": 100.0, "XLK": 50.0, "IAU": 30.0}

        trades = pf.rebalance_to_weights(
            target_weights={"SPY": 0.80, "IAU": 0.20},
            prices=prices,
            target_invested_amount=600.0,
            trade_date=date(2024, 1, 2),
        )
        # XLK는 전량 매도되어야 함
        assert pf.positions["XLK"].shares == 0.0

    def test_snapshot(self):
        pf = Portfolio(cash=400.0)
        pf.positions["SPY"] = Position("SPY", shares=3.0, avg_cost=100.0)
        prices = {"SPY": 110.0}
        snap = pf.snapshot(prices)
        assert snap["cash"] == 400.0
        assert snap["invested"] == 330.0
        assert snap["total"] == 730.0
        assert "SPY" in snap["positions"]

    def test_avg_cost_update_on_additional_buy(self):
        pf = Portfolio(cash=2000.0)
        pf.buy("SPY", 500.0, 100.0)  # 5 shares @ 100
        pf.buy("SPY", 600.0, 120.0)  # 5 shares @ 120
        pos = pf.positions["SPY"]
        assert pos.shares == 10.0
        assert pos.avg_cost == pytest.approx(110.0)  # (500+600)/10
