"""
Portfolio + Position — 매매/평가/리밸런싱 실행.

분수 주식 허용, 종가 체결, 거래 비용 제외 (v0).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional


@dataclass
class Trade:
    """단일 매매 기록."""

    trade_date: date
    symbol: str
    action: str  # "BUY" | "SELL"
    shares: float
    price: float
    amount: float  # price * shares


@dataclass
class Position:
    """단일 종목 포지션."""

    symbol: str
    shares: float = 0.0
    avg_cost: float = 0.0

    @property
    def cost_basis(self) -> float:
        return self.shares * self.avg_cost

    def market_value(self, price: float) -> float:
        return self.shares * price


class Portfolio:
    """현금 + 포지션 관리."""

    def __init__(self, cash: float) -> None:
        self.cash: float = cash
        self.positions: Dict[str, Position] = {}

    def total_value(self, prices: Dict[str, float]) -> float:
        invested = sum(
            pos.market_value(prices[sym])
            for sym, pos in self.positions.items()
            if sym in prices
        )
        return self.cash + invested

    def invested_value(self, prices: Dict[str, float]) -> float:
        return sum(
            pos.market_value(prices[sym])
            for sym, pos in self.positions.items()
            if sym in prices
        )

    def invested_ratio(self, prices: Dict[str, float]) -> float:
        tv = self.total_value(prices)
        if tv <= 0:
            return 0.0
        return self.invested_value(prices) / tv

    def add_cash(self, amount: float) -> None:
        """현금 추가 (DCA 월 자금 투입)."""
        if amount > 0:
            self.cash += amount

    def buy(self, symbol: str, amount: float, price: float) -> Optional[Trade]:
        """종가 매수. amount = 투입 금액(USD)."""
        if amount <= 0 or price <= 0:
            return None
        amount = min(amount, self.cash)
        if amount <= 0:
            return None

        shares = amount / price
        pos = self.positions.get(symbol)
        if pos is None:
            pos = Position(symbol=symbol)
            self.positions[symbol] = pos

        # 평균단가 갱신
        total_cost = pos.shares * pos.avg_cost + amount
        pos.shares += shares
        pos.avg_cost = total_cost / pos.shares if pos.shares > 0 else 0.0

        self.cash -= amount
        return Trade(
            trade_date=date.min,  # caller sets
            symbol=symbol,
            action="BUY",
            shares=shares,
            price=price,
            amount=amount,
        )

    def sell(self, symbol: str, amount: float, price: float) -> Optional[Trade]:
        """종가 매도. amount = 매도 금액(USD). 보유 미달 시 전량 매도."""
        pos = self.positions.get(symbol)
        if pos is None or pos.shares <= 0 or price <= 0:
            return None
        if amount <= 0:
            return None

        max_amount = pos.market_value(price)
        amount = min(amount, max_amount)
        shares = amount / price

        pos.shares -= shares
        if pos.shares < 1e-10:
            pos.shares = 0.0

        self.cash += amount
        return Trade(
            trade_date=date.min,
            symbol=symbol,
            action="SELL",
            shares=shares,
            price=price,
            amount=amount,
        )

    def rebalance_to_weights(
        self,
        target_weights: Dict[str, float],
        prices: Dict[str, float],
        target_invested_amount: float,
        trade_date: date,
        min_hold_values: Optional[Dict[str, float]] = None,
    ) -> List[Trade]:
        """목표 비중으로 리밸런싱.

        Parameters
        ----------
        target_weights : {symbol: weight}
            invested 기준 비중 (합계=1.0).
        prices : {symbol: price}
            당일 종가.
        target_invested_amount : float
            투자 목표 금액 (total_value * invested_ratio).
        trade_date : date
            매매일.

        Returns
        -------
        실행된 Trade 목록.
        """
        trades: List[Trade] = []
        min_hold_values = min_hold_values or {}

        # 목표 포지션 금액
        target_amounts: Dict[str, float] = {}
        for sym, w in target_weights.items():
            if sym in prices and prices[sym] > 0:
                target_amounts[sym] = target_invested_amount * w

        # 현재 포지션 금액
        current_amounts: Dict[str, float] = {}
        for sym, pos in self.positions.items():
            if sym in prices:
                current_amounts[sym] = pos.market_value(prices[sym])

        # 1) 매도 먼저 (현금 확보)
        # 목표에 없는 종목 전량 매도
        for sym in list(self.positions.keys()):
            if sym not in target_weights and sym in prices:
                cur = current_amounts.get(sym, 0.0)
                protected_min = max(0.0, float(min_hold_values.get(sym, 0.0)))
                sell_amt = max(cur - protected_min, 0.0)
                if sell_amt > 0:
                    t = self.sell(sym, sell_amt, prices[sym])
                    if t:
                        t.trade_date = trade_date
                        trades.append(t)

        # 비중 축소 종목 부분 매도
        for sym, target_amt in target_amounts.items():
            cur = current_amounts.get(sym, 0.0)
            if cur > target_amt + 0.01:  # 매도 필요
                protected_min = max(0.0, float(min_hold_values.get(sym, 0.0)))
                sell_amt = min(cur - target_amt, max(cur - protected_min, 0.0))
                t = self.sell(sym, sell_amt, prices[sym])
                if t:
                    t.trade_date = trade_date
                    trades.append(t)

        # 2) 매수 (확보된 현금 사용)
        for sym, target_amt in target_amounts.items():
            cur_pos = self.positions.get(sym)
            cur_val = cur_pos.market_value(prices[sym]) if cur_pos and sym in prices else 0.0
            if target_amt > cur_val + 0.01:  # 매수 필요
                buy_amt = target_amt - cur_val
                t = self.buy(sym, buy_amt, prices[sym])
                if t:
                    t.trade_date = trade_date
                    trades.append(t)

        return trades

    def snapshot(self, prices: Dict[str, float]) -> Dict:
        """현재 포트폴리오 상태 스냅샷."""
        positions = {}
        for sym, pos in self.positions.items():
            if pos.shares > 0 and sym in prices:
                cur_price = prices[sym]
                positions[sym] = {
                    "shares": round(pos.shares, 6),
                    "avg_cost": round(pos.avg_cost, 4),
                    "price": cur_price,
                    "value": round(pos.market_value(cur_price), 2),
                }
        return {
            "cash": round(self.cash, 2),
            "invested": round(self.invested_value(prices), 2),
            "total": round(self.total_value(prices), 2),
            "positions": positions,
        }
