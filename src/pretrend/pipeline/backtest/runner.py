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

from ._utils import load_strategy_snapshot
from .config import BacktestConfig
from .metrics import compute_metrics
from .portfolio import Portfolio, Trade
from .rebalancer import compute_target_weights, is_rebalance_day
from .allocation import dispatch_allocation
from pretrend.pipeline.strategy_engine.universe.engine import build_universe

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
    metrics: Dict = field(default_factory=dict)


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

        # 2) Strategy snapshot + Gold EOD features 로드
        #    - policy_selection: snapshot (시장 국면 신호)
        #    - universe: gold_eod features에서 rebalance 시점마다 inline 계산
        #      (what_to_hold 스냅샷은 누적 이력 문제로 미사용)
        #    - allocation: 실제 포트폴리오 상태 기반 동적 계산
        policy_df = self._load_snapshot(config, "policy_selection")
        gold_eod_features_df = self._load_gold_eod_features(config)

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

                # universe inline 계산: 당일 gold_eod RS 기반 (스냅샷 불사용)
                universe_df = self._compute_universe_inline(
                    policy_row, gold_eod_features_df, td
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

        # 성과 지표 자동 계산
        nav_series = daily_log["nav"] if not daily_log.empty else pd.Series(dtype=float)
        metrics = compute_metrics(nav_series, benchmark_nav)

        return BacktestResult(
            config=config,
            daily_log=daily_log,
            trade_log=trade_log,
            benchmark_nav=benchmark_nav,
            metrics=metrics,
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

        preset_name으로 allocation.ALLOCATION_REGISTRY에서 버전별 함수를 dispatch.
        새 버전 추가 시 runner.py 변경 없이 allocation.py 수정만으로 완료.
        """
        if policy_row is None:
            return None

        current = portfolio.invested_ratio(prices)
        result = dispatch_allocation(
            preset_name=config.preset_name or "v0",
            current=current,
            policy_row=policy_row,
            config=config,
        )
        return pd.Series(result)

    def _load_gold_eod_features(self, config: BacktestConfig) -> pd.DataFrame:
        """Gold EOD features 로드 (universe inline 계산용).

        필요 컬럼: symbol, trade_date, asset_group, ret_20d.
        컬럼이 부족하면 빈 DataFrame 반환 → 전술 교체 없이 core 비중만 사용 (fail-open).
        """
        root = config.gold_eod_root
        files = list(root.rglob("*.parquet"))
        if not files:
            return pd.DataFrame()

        df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
        if "trade_date" in df.columns:
            df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date

        needed = ["symbol", "trade_date", "asset_group", "ret_20d"]
        if not all(c in df.columns for c in needed):
            logger.debug(
                "[Backtest] gold_eod_features 컬럼 부족 %s — universe inline 불가",
                [c for c in needed if c not in df.columns],
            )
            return pd.DataFrame()

        optional = ["asset_name", "vol_20d"]
        keep = needed + [c for c in optional if c in df.columns]
        return df[keep].dropna(subset=["symbol", "trade_date", "ret_20d"])

    def _compute_universe_inline(
        self,
        policy_row: Optional[pd.Series],
        gold_eod_features: pd.DataFrame,
        trade_date: date,
    ) -> pd.DataFrame:
        """rebalance_date 기준 universe를 gold_eod features에서 inline 계산.

        스냅샷 의존 없이 당일 RS 기반으로 전술 후보를 실시간 선별한다.
        데이터 부족 시 빈 DataFrame 반환 (fail-open → tactical 없이 core 비중 유지).
        """
        if policy_row is None or gold_eod_features.empty:
            return pd.DataFrame()

        # trade_date 당일 EOD. 없으면 가장 가까운 이전 날짜 fallback.
        avail = gold_eod_features[gold_eod_features["trade_date"] <= trade_date]
        if avail.empty:
            return pd.DataFrame()
        effective_date = avail["trade_date"].max()

        # policy_row를 effective_date로 설정 → build_universe가 해당 날짜 EOD 매핑
        ps_dict = policy_row.to_dict()
        ps_dict["trade_date"] = effective_date
        ps_df = pd.DataFrame([ps_dict])

        return build_universe(ps_df, gold_eod_features)

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
        """Strategy snapshot parquet 로드 — _utils.load_strategy_snapshot() 위임."""
        return load_strategy_snapshot(config.strategy_root, stage_name)

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
        """해당 날짜 또는 가장 가까운 이전 날짜의 시그널 행 (결정론적 선택).

        다중 decision_date 스냅샷이 같은 trade_date를 커버할 경우:
        1. 최신 decision_date 행을 우선 선택 (date 타입 정규화 후 max())
        2. 동률(동일 decision_date)이면 source_run_id desc 2차 정렬로 결정론적 선택
        """
        if df is None or df.empty or date_col not in df.columns:
            return None

        mask = df[date_col] <= td
        if not mask.any():
            return None

        latest = df.loc[mask, date_col].max()
        row = df[df[date_col] == latest]
        if row.empty:
            return None

        # 최신 decision_date 우선 선택 (decision_date는 _load_snapshot에서 date 타입으로 정규화됨)
        if "decision_date" in row.columns:
            row = row[row["decision_date"] == row["decision_date"].max()]

        # 동률 타이브레이커: source_run_id desc 정렬 (같은 decision_date 내 복수 행 방지)
        if len(row) > 1 and "source_run_id" in row.columns:
            row = row.sort_values("source_run_id", ascending=False)

        return row.iloc[0]

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
    from .report import print_report, save_result

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
    parser.add_argument(
        "--no-save", action="store_true",
        help="결과를 파일로 저장하지 않음 (기본: $PRETREND_RESULT_ROOT/backtest/)",
    )
    parser.add_argument(
        "--save-dir", default=None,
        help="결과 저장 디렉토리 (미지정 시 PRETREND_RESULT_ROOT 환경변수 참조)",
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

    if not args.no_save:
        out_dir = save_result(result, base_dir=args.save_dir)
        if out_dir:
            print(f"  Results saved → {out_dir}\n")


if __name__ == "__main__":
    main()
