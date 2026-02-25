"""EOD paper execution simulator (stateful, NAV-based)."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from pretrend.pipeline.backtest.config import BacktestConfig
from pretrend.pipeline.backtest.portfolio import Portfolio, Trade
from pretrend.pipeline.backtest.rebalancer import compute_target_weights
from .io import load_next_step_for_date


@dataclass
class StagedSellPlan:
    total_sell_amount: float
    tranches: List[float]
    tranche_idx: int
    target_ratio: float


def _normalize_weights(weights: Dict[str, float], prices: Dict[str, float]) -> Dict[str, float]:
    valid = {k: float(v) for k, v in weights.items() if k in prices and prices[k] > 0 and v > 0}
    s = sum(valid.values())
    if s <= 0:
        return {}
    return {k: v / s for k, v in valid.items()}


def _is_first_of_month(td: date, prev_td: Optional[date]) -> bool:
    if prev_td is None:
        return False
    return td.month != prev_td.month


def _as_prices(prices_df: pd.DataFrame, td: date) -> Dict[str, float]:
    day = prices_df[prices_df["trade_date"] == td]
    if day.empty:
        return {}
    return dict(zip(day["symbol"], day["adj_close"]))


def _get_signal_row(
    df: Optional[pd.DataFrame],
    td: date,
    date_col: str,
) -> Optional[pd.Series]:
    if df is None or df.empty or date_col not in df.columns:
        return None
    mask = df[date_col] <= td
    if not mask.any():
        return None
    latest = df.loc[mask, date_col].max()
    row = df[df[date_col] == latest]
    if row.empty:
        return None
    return row.iloc[-1]


def _get_universe_window(universe_df: Optional[pd.DataFrame], td: date) -> Optional[pd.DataFrame]:
    if universe_df is None or universe_df.empty:
        return None
    if "rebalance_date" not in universe_df.columns:
        return universe_df
    day = universe_df[universe_df["rebalance_date"] <= td]
    if day.empty:
        return None
    latest = day["rebalance_date"].max()
    return day[day["rebalance_date"] == latest].copy()


def _record_trade_rows(trades: List[Trade], source_job: str, decision_date: date, simulation_date: date) -> List[Dict]:
    rows: List[Dict] = []
    for idx, t in enumerate(trades):
        rows.append(
            {
                "trade_date": t.trade_date,
                "symbol": t.symbol,
                "action": t.action,
                "shares": float(t.shares),
                "price_eod": float(t.price),
                "amount": float(t.amount),
                "sequence_id": idx,
                "source_job": source_job,
                "message_type": "PAPER_RESULT",
                "decision_date": decision_date,
                "simulation_date": simulation_date,
            }
        )
    return rows


def _rebalance_to_target(
    portfolio: Portfolio,
    prices: Dict[str, float],
    target_ratio: float,
    target_weights: Dict[str, float],
    trade_date: date,
    *,
    allow_sell: bool,
    lock_sell_symbols: Sequence[str],
) -> List[Trade]:
    lock_set = set(lock_sell_symbols)
    trades: List[Trade] = []

    total_value = portfolio.total_value(prices)
    target_invested = max(0.0, min(1.0, target_ratio)) * total_value

    current_amounts: Dict[str, float] = {}
    for sym, pos in portfolio.positions.items():
        if pos.shares > 0 and sym in prices:
            current_amounts[sym] = pos.market_value(prices[sym])

    target_amounts = {sym: target_invested * w for sym, w in target_weights.items()}

    if allow_sell:
        for sym, cur in list(current_amounts.items()):
            if sym not in target_amounts and sym not in lock_set and cur > 0:
                t = portfolio.sell(sym, cur, prices[sym])
                if t:
                    t.trade_date = trade_date
                    trades.append(t)

        for sym, target_amt in target_amounts.items():
            if sym in lock_set:
                continue
            cur = portfolio.positions.get(sym)
            cur_amt = cur.market_value(prices[sym]) if cur and sym in prices else 0.0
            if cur_amt > target_amt + 0.01:
                t = portfolio.sell(sym, cur_amt - target_amt, prices[sym])
                if t:
                    t.trade_date = trade_date
                    trades.append(t)

    for sym, target_amt in target_amounts.items():
        cur = portfolio.positions.get(sym)
        cur_amt = cur.market_value(prices[sym]) if cur and sym in prices else 0.0
        if target_amt > cur_amt + 0.01:
            t = portfolio.buy(sym, target_amt - cur_amt, prices[sym])
            if t:
                t.trade_date = trade_date
                trades.append(t)

    return trades


def _resolve_bias(next_step_df: Optional[pd.DataFrame], td: date) -> str:
    row = load_next_step_for_date(next_step_df, td)
    if row is None:
        return "UNKNOWN"
    return str(row.get("bias_1m", "UNKNOWN"))


def _apply_soft_gate(config: BacktestConfig, bias_1m: str) -> BacktestConfig:
    """Soft gate: tactical 강도 조절만 수행한다."""
    if bias_1m == "RISK_ON_BIAS":
        return replace(config, max_tactical_slots=2, tactical_weight=config.tactical_weight)
    if bias_1m == "NEUTRAL_BIAS":
        return replace(config, max_tactical_slots=1, tactical_weight=round(config.tactical_weight * 0.75, 4))
    if bias_1m == "RISK_OFF_BIAS":
        return replace(config, max_tactical_slots=0, tactical_weight=0.0)
    # UNKNOWN fail-open -> NEUTRAL 동일
    return replace(config, max_tactical_slots=1, tactical_weight=round(config.tactical_weight * 0.75, 4))


def simulate_paper_execution(
    *,
    config: BacktestConfig,
    exposure_df: pd.DataFrame,
    prices_df: pd.DataFrame,
    source_job: str,
    decision_date: date,
    simulation_date: date,
    initial_capital: float = 1_000_000.0,
    monthly_addition: float = 300_000.0,
    sell_tranches: Sequence[float] = (0.50, 0.30, 0.20),
    schd_sell_locked: bool = True,
    policy_df: Optional[pd.DataFrame] = None,
    universe_df: Optional[pd.DataFrame] = None,
    next_step_df: Optional[pd.DataFrame] = None,
    enable_predictor_gate: bool = True,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run EOD paper simulation and return ledger/positions/portfolio frames."""
    if exposure_df is None or exposure_df.empty:
        cols_ledger = [
            "trade_date", "symbol", "action", "shares", "price_eod", "amount", "sequence_id",
            "source_job", "message_type", "decision_date", "simulation_date",
        ]
        cols_positions = [
            "trade_date", "symbol", "shares", "avg_cost", "eod_price", "market_value", "gain_pct", "weight",
            "source_job", "decision_date", "simulation_date",
        ]
        cols_portfolio = [
            "trade_date", "cash", "invested_value", "nav", "total_invested_capital", "daily_pnl", "cumulative_pnl",
            "source_job", "decision_date", "simulation_date",
        ]
        return pd.DataFrame(columns=cols_ledger), pd.DataFrame(columns=cols_positions), pd.DataFrame(columns=cols_portfolio)

    df = exposure_df.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    df = df.sort_values("trade_date")

    portfolio = Portfolio(cash=initial_capital)
    total_invested_capital = initial_capital
    staged_sell: Optional[StagedSellPlan] = None

    ledger_rows: List[Dict] = []
    pos_rows: List[Dict] = []
    pf_rows: List[Dict] = []

    prev_td: Optional[date] = None
    prev_nav: Optional[float] = None

    for _, row in df.iterrows():
        td: date = row["trade_date"]
        prices = _as_prices(prices_df, td)
        if not prices:
            continue

        if _is_first_of_month(td, prev_td):
            portfolio.add_cash(monthly_addition)
            total_invested_capital += monthly_addition

        action = str(row.get("action", "HOLD"))

        policy_row = _get_signal_row(policy_df, td, "trade_date")
        universe_day = _get_universe_window(universe_df, td)

        effective_config = config
        if enable_predictor_gate:
            bias_1m = _resolve_bias(next_step_df, td)
            effective_config = _apply_soft_gate(config, bias_1m)

        target_ratio, target_weights = compute_target_weights(
            trade_date=td,
            policy_row=policy_row,
            allocation_row=row,
            universe_df=universe_day,
            config=effective_config,
            prices=prices,
        )
        target_weights = _normalize_weights(target_weights, prices)
        if not target_weights:
            target_weights = _normalize_weights(config.active_weights(td), prices)

        lock_symbols = ["SCHD"] if schd_sell_locked else []

        executed_trades: List[Trade] = []
        weekday = td.weekday()  # Mon=0 ... Fri=4

        # Monday: signal evaluation day, no execution
        if weekday == 0:
            if staged_sell is not None and action != "DECREASE":
                staged_sell = None

        # Tuesday: INCREASE only (buy-focused)
        elif weekday == 1 and action == "INCREASE":
            executed_trades = _rebalance_to_target(
                portfolio,
                prices,
                target_ratio,
                target_weights,
                td,
                allow_sell=False,
                lock_sell_symbols=lock_symbols,
            )
            if staged_sell is not None:
                staged_sell = None

        # Friday: staged DECREASE
        elif weekday == 4:
            if action == "DECREASE":
                if staged_sell is None:
                    cur_invested = portfolio.invested_value(prices)
                    target_invested = portfolio.total_value(prices) * max(0.0, min(1.0, target_ratio))
                    total_sell = max(0.0, cur_invested - target_invested)
                    if total_sell > 0:
                        staged_sell = StagedSellPlan(
                            total_sell_amount=total_sell,
                            tranches=[float(x) for x in sell_tranches],
                            tranche_idx=0,
                            target_ratio=target_ratio,
                        )

                if staged_sell is not None and staged_sell.tranche_idx < len(staged_sell.tranches):
                    tranche_ratio = staged_sell.tranches[staged_sell.tranche_idx]
                    tranche_target_ratio = max(
                        0.0,
                        portfolio.invested_ratio(prices)
                        - (staged_sell.total_sell_amount * tranche_ratio / max(portfolio.total_value(prices), 1e-9)),
                    )
                    executed_trades = _rebalance_to_target(
                        portfolio,
                        prices,
                        tranche_target_ratio,
                        target_weights,
                        td,
                        allow_sell=True,
                        lock_sell_symbols=lock_symbols,
                    )
                    staged_sell.tranche_idx += 1
                    if staged_sell.tranche_idx >= len(staged_sell.tranches):
                        staged_sell = None
            else:
                staged_sell = None

        ledger_rows.extend(_record_trade_rows(executed_trades, source_job, decision_date, simulation_date))

        snap = portfolio.snapshot(prices)
        invested_value = float(snap["invested"])
        nav = float(snap["total"])
        daily_pnl = None if prev_nav in (None, 0.0) else (nav / prev_nav - 1.0)
        cumulative_pnl = (nav - total_invested_capital) / total_invested_capital if total_invested_capital > 0 else None

        pf_rows.append(
            {
                "trade_date": td,
                "cash": float(snap["cash"]),
                "invested_value": invested_value,
                "nav": nav,
                "total_invested_capital": float(total_invested_capital),
                "daily_pnl": daily_pnl,
                "cumulative_pnl": cumulative_pnl,
                "source_job": source_job,
                "decision_date": decision_date,
                "simulation_date": simulation_date,
            }
        )

        positions = snap.get("positions", {})
        for sym, p in positions.items():
            shares = float(p.get("shares", 0.0))
            avg_cost = float(p.get("avg_cost", 0.0))
            eod_price = float(p.get("price", 0.0))
            market_value = float(p.get("value", 0.0))
            gain_pct = None
            if shares > 0 and avg_cost > 0:
                gain_pct = eod_price / avg_cost - 1.0
            weight = market_value / invested_value if invested_value > 0 else 0.0
            pos_rows.append(
                {
                    "trade_date": td,
                    "symbol": sym,
                    "shares": shares,
                    "avg_cost": avg_cost,
                    "eod_price": eod_price,
                    "market_value": market_value,
                    "gain_pct": gain_pct,
                    "weight": weight,
                    "source_job": source_job,
                    "decision_date": decision_date,
                    "simulation_date": simulation_date,
                }
            )

        prev_td = td
        prev_nav = nav

    ledger_df = pd.DataFrame(ledger_rows)
    positions_df = pd.DataFrame(pos_rows)
    portfolio_df = pd.DataFrame(pf_rows)
    return ledger_df, positions_df, portfolio_df
