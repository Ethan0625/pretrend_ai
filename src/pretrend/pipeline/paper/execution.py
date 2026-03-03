"""EOD paper execution simulator (stateful, NAV-based)."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple, Any

import pandas as pd

from pretrend.pipeline.backtest.config import BacktestConfig
from pretrend.pipeline.backtest.portfolio import Portfolio, Trade
from pretrend.pipeline.backtest.rebalancer import compute_target_weights
from .io import load_next_step_for_date

_GUARDRAIL_TC_RATIO: float = 0.85
_GUARDRAIL_PEAK_DD: float = -0.20
_GUARDRAIL_PANIC_WARN: int = 5
_GUARDRAIL_RESUME_TC_RATIO: float = 0.90
_GUARDRAIL_RESUME_PEAK_DD: float = -0.15


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


def _resolve_next_step_meta(next_step_df: Optional[pd.DataFrame], td: date) -> Dict[str, Any]:
    row = load_next_step_for_date(next_step_df, td)
    if row is None:
        return {
            "bias_20d": "UNKNOWN",
            "bias_candidate_20d": "UNKNOWN",
            "bias_state_source": "UNKNOWN",
            "cooldown_compressed_flag": False,
            "cooldown_compressed_reason": "NONE",
            "hard_gate_exit_assist_flag": False,
            "hard_gate_exit_assist_reason": "NONE",
        }
    return {
        "bias_20d": str(row.get("bias_20d", "UNKNOWN")),
        "bias_candidate_20d": str(row.get("bias_candidate_20d", "UNKNOWN")),
        "bias_state_source": str(row.get("bias_state_source", "UNKNOWN")),
        "cooldown_compressed_flag": bool(row.get("cooldown_compressed_flag", False)),
        "cooldown_compressed_reason": str(row.get("cooldown_compressed_reason", "NONE")),
        "hard_gate_exit_assist_flag": bool(row.get("hard_gate_exit_assist_flag", False)),
        "hard_gate_exit_assist_reason": str(row.get("hard_gate_exit_assist_reason", "NONE")),
    }


def _apply_soft_gate(config: BacktestConfig, bias_20d: str) -> BacktestConfig:
    """Soft gate: tactical 강도 조절만 수행한다."""
    if bias_20d == "RISK_ON_BIAS":
        return replace(config, max_tactical_slots=2, tactical_weight=config.tactical_weight)
    if bias_20d == "NEUTRAL_BIAS":
        return replace(config, max_tactical_slots=1, tactical_weight=round(config.tactical_weight * 0.75, 4))
    if bias_20d == "RISK_OFF_BIAS":
        return replace(config, max_tactical_slots=0, tactical_weight=0.0)
    # UNKNOWN fail-open -> NEUTRAL 동일
    return replace(config, max_tactical_slots=1, tactical_weight=round(config.tactical_weight * 0.75, 4))


def _lookup_group_transition_rows(
    group_df: Optional[pd.DataFrame],
    td: date,
) -> pd.DataFrame:
    if group_df is None or group_df.empty or "trade_date" not in group_df.columns:
        return pd.DataFrame()
    x = group_df
    if not hasattr(x["trade_date"].iloc[0], "year"):
        x = x.copy()
        x["trade_date"] = pd.to_datetime(x["trade_date"]).dt.date
    mask = x["trade_date"] <= td
    if not mask.any():
        return pd.DataFrame()
    latest = x.loc[mask, "trade_date"].max()
    rows = x[x["trade_date"] == latest].copy()
    if rows.empty:
        return pd.DataFrame()
    if "asset_group" in rows.columns:
        rows = rows.sort_values("asset_group")
    return rows


def _apply_group_transition_gate(
    config: BacktestConfig,
    group_df: Optional[pd.DataFrame],
    td: date,
) -> Tuple[BacktestConfig, Dict[str, Any]]:
    """v3.4 tactical group soft-gate."""
    rows = _lookup_group_transition_rows(group_df, td)
    if rows.empty or "asset_group" not in rows.columns or "group_state_now" not in rows.columns:
        return config, {
            "applied_groups": list(config.tactical_groups),
            "reduced_groups": [],
            "group_gate_source": "MISSING",
        }

    weak_groups = {
        str(r["asset_group"])
        for _, r in rows.iterrows()
        if str(r.get("group_state_now", "UNKNOWN")) == "WEAK"
    }
    allowed_groups = [g for g in config.tactical_groups if g not in weak_groups]

    max_slots = config.max_tactical_slots
    tactical_weight = config.tactical_weight
    if weak_groups:
        max_slots = max(0, max_slots - 1)
        tactical_weight = round(tactical_weight * 0.75, 4)
    if not allowed_groups:
        max_slots = 0
        tactical_weight = 0.0

    return replace(
        config,
        tactical_groups=list(allowed_groups),
        max_tactical_slots=max_slots,
        tactical_weight=tactical_weight,
    ), {
        "applied_groups": list(allowed_groups),
        "reduced_groups": sorted(list(weak_groups)),
        "group_gate_source": "SNAPSHOT",
    }


def _apply_group_transition_gate_v341(
    config: BacktestConfig,
    group_df: Optional[pd.DataFrame],
    td: date,
    *,
    short_signal: str,
    mid_regime: str,
    relief_streak: int,
    group_gate_active: bool,
) -> Tuple[BacktestConfig, Dict[str, Any], int, bool]:
    """v3.4.1 tactical group soft-gate.

    - WEAK >= 2일 때 축소 진입
    - 재진입: RELIEF 2연속 또는 MID=RISK_ON
    """
    rows = _lookup_group_transition_rows(group_df, td)
    reentry_trigger = "NONE"
    if str(mid_regime) == "RISK_ON":
        reentry_trigger = "MID_RISK_ON"
    elif str(short_signal) == "RELIEF" and relief_streak >= 2:
        reentry_trigger = "RELIEF_STREAK"

    if rows.empty or "asset_group" not in rows.columns or "group_state_now" not in rows.columns:
        return config, {
            "applied_groups": list(config.tactical_groups),
            "reduced_groups": [],
            "weak_group_count": 0,
            "group_gate_applied": False,
            "reentry_trigger": reentry_trigger,
            "group_gate_source": "MISSING",
        }, relief_streak, False

    weak_groups = {
        str(r["asset_group"])
        for _, r in rows.iterrows()
        if str(r.get("group_state_now", "UNKNOWN")) == "WEAK"
    }
    weak_count = len(weak_groups)
    if reentry_trigger != "NONE":
        should_de_risk = False
    elif group_gate_active:
        should_de_risk = True
    else:
        should_de_risk = weak_count >= 2

    if should_de_risk:
        allowed_groups = [g for g in config.tactical_groups if g not in weak_groups]
        max_slots = max(0, config.max_tactical_slots - 1)
        tactical_weight = round(config.tactical_weight * 0.75, 4)
        if not allowed_groups:
            max_slots = 0
            tactical_weight = 0.0
        new_cfg = replace(
            config,
            tactical_groups=list(allowed_groups),
            max_tactical_slots=max_slots,
            tactical_weight=tactical_weight,
        )
    else:
        new_cfg = config

    return new_cfg, {
        "applied_groups": list(new_cfg.tactical_groups),
        "reduced_groups": sorted(list(weak_groups if should_de_risk else set())),
        "weak_group_count": weak_count,
        "group_gate_applied": should_de_risk,
        "reentry_trigger": reentry_trigger,
        "group_gate_source": "SNAPSHOT",
    }, relief_streak, should_de_risk


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
    group_transition_df: Optional[pd.DataFrame] = None,
    enable_predictor_gate: bool = True,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """Run EOD paper simulation and return ledger/positions/portfolio frames + guardrail status."""
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
            "guardrail_paused", "guardrail_nav_breach", "guardrail_peak_dd_breach",
            "guardrail_panic_streak", "peak_nav",
            "source_job", "decision_date", "simulation_date",
        ]
        return (
            pd.DataFrame(columns=cols_ledger),
            pd.DataFrame(columns=cols_positions),
            pd.DataFrame(columns=cols_portfolio),
            {
                "paused": False,
                "paused_since": None,
                "nav_breach": False,
                "peak_dd_breach": False,
                "panic_streak": 0,
                "peak_nav": float(initial_capital),
                "last_nav": float(initial_capital),
                "last_total_invested": float(initial_capital),
            },
        )

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
    relief_streak: int = 0
    group_gate_active: bool = False
    peak_nav: float = float(initial_capital)
    paused: bool = False
    paused_since: Optional[date] = None
    panic_streak_guardrail: int = 0

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
            next_meta = _resolve_next_step_meta(next_step_df, td)
            bias_20d = str(next_meta.get("bias_20d", "UNKNOWN"))
            if str(config.preset_name or "") == "v3.4.2a":
                if bool(next_meta.get("hard_gate_exit_assist_flag", False)) and bias_20d == "RISK_OFF_BIAS":
                    bias_20d = "NEUTRAL_BIAS"
                elif (
                    bool(next_meta.get("cooldown_compressed_flag", False))
                    and str(next_meta.get("bias_state_source", "UNKNOWN")) == "HOLD_COOLDOWN"
                ):
                    candidate = str(next_meta.get("bias_candidate_20d", "UNKNOWN"))
                    if candidate in {"RISK_ON_BIAS", "NEUTRAL_BIAS", "RISK_OFF_BIAS"}:
                        bias_20d = candidate
            effective_config = _apply_soft_gate(config, bias_20d)
            short_sig = "UNKNOWN"
            mid_reg = "UNKNOWN"
            if policy_row is not None:
                short_sig = str(policy_row.get("short_signal", "UNKNOWN"))
                mid_reg = str(policy_row.get("mid_regime", "UNKNOWN"))
            relief_streak = relief_streak + 1 if short_sig == "RELIEF" else 0
            if str(config.preset_name or "") == "v3.4.1":
                (
                    effective_config,
                    _,
                    relief_streak,
                    group_gate_active,
                ) = _apply_group_transition_gate_v341(
                    effective_config,
                    group_transition_df,
                    td,
                    short_signal=short_sig,
                    mid_regime=mid_reg,
                    relief_streak=relief_streak,
                    group_gate_active=group_gate_active,
                )
            else:
                effective_config, _ = _apply_group_transition_gate(
                    effective_config, group_transition_df, td
                )

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
        elif weekday == 1 and action == "INCREASE" and not paused:
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
        peak_nav = max(peak_nav, nav)
        peak_dd = (nav - peak_nav) / peak_nav if peak_nav > 0 else 0.0
        nav_tc_ratio = nav / total_invested_capital if total_invested_capital > 0 else 1.0
        nav_breach = nav_tc_ratio < _GUARDRAIL_TC_RATIO
        peak_breach = peak_dd < _GUARDRAIL_PEAK_DD

        if nav_breach or peak_breach:
            if not paused:
                paused = True
                paused_since = td
        elif paused:
            if nav_tc_ratio >= _GUARDRAIL_RESUME_TC_RATIO and peak_dd >= _GUARDRAIL_RESUME_PEAK_DD:
                paused = False
                paused_since = None

        short_sig_for_panic = "UNKNOWN"
        if policy_row is not None:
            short_sig_for_panic = str(policy_row.get("short_signal", "UNKNOWN"))
        panic_streak_guardrail = panic_streak_guardrail + 1 if short_sig_for_panic == "PANIC" else 0

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
                "guardrail_paused": paused,
                "guardrail_nav_breach": nav_breach,
                "guardrail_peak_dd_breach": peak_breach,
                "guardrail_panic_streak": panic_streak_guardrail,
                "peak_nav": peak_nav,
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
    guardrail_status = {
        "paused": paused,
        "paused_since": paused_since.isoformat() if paused_since else None,
        "nav_breach": bool(pf_rows[-1]["guardrail_nav_breach"]) if pf_rows else False,
        "peak_dd_breach": bool(pf_rows[-1]["guardrail_peak_dd_breach"]) if pf_rows else False,
        "panic_streak": int(panic_streak_guardrail),
        "peak_nav": float(peak_nav),
        "last_nav": float(pf_rows[-1]["nav"]) if pf_rows else float(initial_capital),
        "last_total_invested": (
            float(pf_rows[-1]["total_invested_capital"]) if pf_rows else float(initial_capital)
        ),
    }
    return ledger_df, positions_df, portfolio_df, guardrail_status
