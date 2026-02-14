"""
BacktestRunner — Strategy Engine 기반 포트폴리오 시뮬레이션.

Usage:
    python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03
"""
from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from .config import BacktestConfig
from .portfolio import Portfolio, Trade
from .rebalancer import compute_target_weights, is_rebalance_day

from pretrend.pipeline.strategy_engine.allocation.engine import (
    _compute_allocation,
    _quantize,
)

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )


@dataclass
class BacktestResult:
    """백테스트 결과."""

    config: BacktestConfig
    daily_log: pd.DataFrame = field(default_factory=pd.DataFrame)
    trade_log: List[Trade] = field(default_factory=list)
    benchmark_nav: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))


class BacktestRunner:
    """E2E 백테스트 실행기."""

    def run(self, config: BacktestConfig) -> BacktestResult:
        logger.info(
            "[Backtest] %s ~ %s, capital=$%.0f",
            config.start_date, config.end_date, config.initial_capital,
        )

        # 1) Gold EOD 로드 (adj_close)
        prices_df = self._load_prices(config)
        if prices_df.empty:
            logger.error("[Backtest] No price data")
            return BacktestResult(config=config)

        trade_dates = sorted(prices_df["trade_date"].unique())
        trade_dates = [d for d in trade_dates if config.start_date <= d <= config.end_date]
        logger.info("[Backtest] %d trade dates", len(trade_dates))

        # 2) Strategy snapshot 로드 (policy_selection + universe만 사용)
        #    allocation은 실제 포트폴리오 상태 기반 동적 계산
        policy_df = self._load_snapshot(config, "policy_selection")
        universe_df = self._load_snapshot(config, "what_to_hold")

        # 3) 포트폴리오 초기화
        portfolio = Portfolio(cash=config.initial_capital)
        daily_rows: List[Dict] = []
        trade_log: List[Trade] = []
        prev_date: Optional[date] = None
        initialized = False

        # 4) 일별 루프
        for td in trade_dates:
            day_prices = self._get_day_prices(prices_df, td)
            if not day_prices:
                continue

            # 초기 매수 (첫 날)
            if not initialized:
                initial_trades = self._initial_buy(
                    portfolio, config, day_prices, td
                )
                trade_log.extend(initial_trades)
                initialized = True

            # 리밸런싱 판단 (매월 첫 영업일)
            elif is_rebalance_day(td, prev_date, config.rebalance_freq):
                policy_row = self._get_signal_row(policy_df, td, "trade_date")

                # 동적 allocation: 실제 포트폴리오 invested_ratio 기반
                alloc_row = self._compute_dynamic_allocation(
                    portfolio, day_prices, policy_row, config
                )

                target_ratio, target_weights = compute_target_weights(
                    trade_date=td,
                    policy_row=policy_row,
                    allocation_row=alloc_row,
                    universe_df=universe_df,
                    config=config,
                    prices=day_prices,
                )

                total_val = portfolio.total_value(day_prices)
                target_invested = total_val * target_ratio

                trades = portfolio.rebalance_to_weights(
                    target_weights, day_prices, target_invested, td
                )
                trade_log.extend(trades)

            # 일별 NAV 기록
            nav = portfolio.total_value(day_prices)
            snap = portfolio.snapshot(day_prices)
            daily_rows.append({
                "trade_date": td,
                "nav": round(nav, 2),
                "cash": snap["cash"],
                "invested": snap["invested"],
                "invested_ratio": round(snap["invested"] / nav, 4) if nav > 0 else 0.0,
                "n_positions": len([p for p in snap["positions"].values()]),
            })

            prev_date = td

        daily_log = pd.DataFrame(daily_rows)
        if not daily_log.empty:
            daily_log["trade_date"] = pd.to_datetime(daily_log["trade_date"])
            daily_log = daily_log.set_index("trade_date")

        # 5) 벤치마크 (SPY Buy & Hold)
        benchmark_nav = self._compute_benchmark(prices_df, config, trade_dates)

        logger.info(
            "[Backtest] Done — %d days, %d trades",
            len(daily_rows), len(trade_log),
        )

        return BacktestResult(
            config=config,
            daily_log=daily_log,
            trade_log=trade_log,
            benchmark_nav=benchmark_nav,
        )

    # ── Private helpers ─────────────────────────────────────

    def _compute_dynamic_allocation(
        self,
        portfolio: Portfolio,
        prices: Dict[str, float],
        policy_row: Optional[pd.Series],
        config: BacktestConfig,
    ) -> Optional[pd.Series]:
        """실제 포트폴리오 상태 기반 동적 allocation 계산.

        v0 (target_ratio_map=None): strategy engine range-maintenance 위임.
        v1 (target_ratio_map=dict): market state → target ratio + gradual movement.
        """
        if policy_row is None:
            return None

        current = portfolio.invested_ratio(prices)

        if config.target_ratio_map is None:
            # v0: range-maintenance
            result = _compute_allocation(
                current=current,
                lower=float(policy_row.get("target_invested_lower", 0.10)),
                upper=float(policy_row.get("target_invested_upper", 0.60)),
                adj_limit=float(policy_row.get("adjustment_limit", 0.10)),
                step_size=float(policy_row.get("step_size", 0.05)),
                risk_gate=bool(policy_row.get("risk_gate", True)),
                run_universe=bool(policy_row.get("run_universe", True)),
            )
            return pd.Series(result)

        # v1: target-seeking
        return pd.Series(self._target_seeking_allocation(
            current=current, policy_row=policy_row, config=config,
        ))

    def _target_seeking_allocation(
        self,
        current: float,
        policy_row: pd.Series,
        config: BacktestConfig,
    ) -> dict:
        """v1: long_phase → target ratio + gradual movement.

        1. long_phase → target (config.target_ratio_map)
        2. delta = target - current, clip to adjustment_limit
        3. quantize by step_size
        4. risk_gate=false → INCREASE 차단 (DECREASE 허용)
        """
        long_phase = str(policy_row.get("long_phase", "UNKNOWN"))
        risk_gate = bool(policy_row.get("risk_gate", True))

        target = config.target_ratio_map.get(
            long_phase,
            config.target_ratio_map.get("UNKNOWN", 0.40),
        )

        raw_delta = target - current

        # 목표 도달 (step_size 이내)
        if abs(raw_delta) < config.allocation_step_size:
            return {
                "action": "HOLD",
                "next_invested_ratio": current,
                "delta_ratio": 0.0,
                "blocked_by_risk_gate": False,
                "notes": [f"at_target:{target}"],
            }

        if raw_delta > 0:
            # INCREASE
            if not risk_gate:
                return {
                    "action": "HOLD",
                    "next_invested_ratio": current,
                    "delta_ratio": 0.0,
                    "blocked_by_risk_gate": True,
                    "notes": ["increase_blocked_by_risk_gate"],
                }
            delta = min(raw_delta, config.allocation_adjustment_limit)
            delta = _quantize(delta, config.allocation_step_size)
            action = "INCREASE" if delta > 0 else "HOLD"
            next_ratio = min(current + delta, 1.0)
        else:
            # DECREASE
            delta = min(abs(raw_delta), config.allocation_adjustment_limit)
            delta = _quantize(delta, config.allocation_step_size)
            action = "DECREASE" if delta > 0 else "HOLD"
            next_ratio = max(current - delta, 0.0)

        return {
            "action": action,
            "next_invested_ratio": round(next_ratio, 4),
            "delta_ratio": round(next_ratio - current, 4),
            "blocked_by_risk_gate": False,
            "notes": [f"target:{target},phase:{long_phase}"],
        }

    def _load_prices(self, config: BacktestConfig) -> pd.DataFrame:
        """Gold EOD parquet에서 adj_close 로드."""
        root = config.gold_eod_root
        files = list(root.rglob("*.parquet"))
        if not files:
            return pd.DataFrame()

        df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
        if "trade_date" in df.columns:
            df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date

        needed = ["symbol", "trade_date", "adj_close"]
        for col in needed:
            if col not in df.columns:
                return pd.DataFrame()

        return df[needed].dropna(subset=["adj_close"])

    def _load_snapshot(
        self, config: BacktestConfig, stage_name: str
    ) -> Optional[pd.DataFrame]:
        """Strategy snapshot parquet 로드 (모든 decision_date 통합)."""
        root = config.strategy_root / stage_name
        if not root.exists():
            logger.warning("[Backtest] No snapshot dir: %s", root)
            return None

        files = list(root.rglob("*.parquet"))
        if not files:
            return None

        df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)

        # trade_date 또는 rebalance_date 정규화
        for col in ("trade_date", "rebalance_date"):
            if col in df.columns:
                df[col] = pd.to_datetime(df[col]).dt.date

        return df

    def _get_day_prices(
        self, prices_df: pd.DataFrame, td: date
    ) -> Dict[str, float]:
        """특정 날짜의 {symbol: adj_close} 딕셔너리."""
        day = prices_df[prices_df["trade_date"] == td]
        return dict(zip(day["symbol"], day["adj_close"]))

    def _get_signal_row(
        self,
        df: Optional[pd.DataFrame],
        td: date,
        date_col: str,
    ) -> Optional[pd.Series]:
        """해당 날짜 또는 가장 가까운 이전 날짜의 시그널 행."""
        if df is None or df.empty or date_col not in df.columns:
            return None

        mask = df[date_col] <= td
        if not mask.any():
            return None

        latest = df.loc[mask, date_col].max()
        row = df[df[date_col] == latest]
        return row.iloc[0] if not row.empty else None

    def _initial_buy(
        self,
        portfolio: Portfolio,
        config: BacktestConfig,
        prices: Dict[str, float],
        trade_date: date,
    ) -> List[Trade]:
        """초기 포트폴리오 매수."""
        invested_amount = config.initial_capital * config.initial_invested_ratio
        weights = config.active_weights(trade_date)

        trades: List[Trade] = []
        for sym, w in weights.items():
            if sym in prices and prices[sym] > 0:
                amount = invested_amount * w
                t = portfolio.buy(sym, amount, prices[sym])
                if t:
                    t.trade_date = trade_date
                    trades.append(t)
        return trades

    def _compute_benchmark(
        self,
        prices_df: pd.DataFrame,
        config: BacktestConfig,
        trade_dates: List[date],
    ) -> pd.Series:
        """SPY Buy & Hold 벤치마크 NAV."""
        spy = prices_df[prices_df["symbol"] == config.benchmark_symbol].copy()
        if spy.empty:
            return pd.Series(dtype=float)

        spy = spy.set_index("trade_date").sort_index()
        valid_dates = [d for d in trade_dates if d in spy.index]
        if not valid_dates:
            return pd.Series(dtype=float)

        first_price = spy.loc[valid_dates[0], "adj_close"]
        if first_price <= 0:
            return pd.Series(dtype=float)

        nav_values = []
        nav_dates = []
        for d in valid_dates:
            if d in spy.index:
                p = spy.loc[d, "adj_close"]
                nav_values.append(config.initial_capital * (p / first_price))
                nav_dates.append(d)

        return pd.Series(
            nav_values,
            index=pd.DatetimeIndex(nav_dates),
            name="benchmark_nav",
        )


def main() -> None:
    """CLI entrypoint."""
    from .config import PRESET_REGISTRY
    from .report import print_report

    parser = argparse.ArgumentParser(description="Backtest Runner")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--capital", type=float, default=1000.0, help="Initial capital (USD)")
    parser.add_argument(
        "--preset", default="v0", choices=list(PRESET_REGISTRY.keys()),
        help="Backtest preset (default: v0)",
    )
    parser.add_argument(
        "--tactical", nargs="*", default=None,
        help="Override tactical groups. e.g. --tactical SECTOR COMMODITY",
    )
    args = parser.parse_args()

    overrides = {"initial_capital": args.capital}
    if args.tactical:
        overrides["tactical_groups"] = args.tactical

    config = BacktestConfig.from_preset(
        args.preset,
        start_date=date.fromisoformat(args.start),
        end_date=date.fromisoformat(args.end),
        **overrides,
    )

    runner = BacktestRunner()
    result = runner.run(config)
    print_report(result)


if __name__ == "__main__":
    main()
