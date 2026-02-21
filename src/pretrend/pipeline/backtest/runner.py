"""
BacktestRunner — Strategy Engine 기반 포트폴리오 시뮬레이션.

매매 규칙:
  - 월 첫 거래일: monthly_addition 자금 추가 (DCA)
  - 월요일: 전 금요일(T-1) 신호 평가 → INCREASE/HOLD/DECREASE 판단
  - 화요일: INCREASE 신호 시 현금으로 target_weights 비율 매수
  - 금요일: DECREASE 신호 시 단계적 매도 (50% → 30% → 20%, 3주)
  - 신호 반전(HOLD/INCREASE): 잔여 단계 매도 취소
  - PANIC(risk_gate=False): DECREASE 신규 생성 차단 + 진행 중 트랜치 동결 (팔지 않음)
                           INCREASE는 허용 (저점매수) — run_universe=False일 때만 INCREASE 차단

SPY 벤치마크도 동일 규칙 적용 (SPY only, 동일 DCA + 신호).

Usage:
    python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03
"""
from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from ._utils import load_strategy_snapshot
from .config import BacktestConfig
from .metrics import compute_metrics
from .portfolio import Portfolio, Trade
from .rebalancer import compute_target_weights, is_first_of_month
from .allocation import dispatch_allocation
from pretrend.pipeline.strategy_engine.universe.engine import build_universe

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )


@dataclass
class StagedSellPlan:
    """단계적 매도 계획 — DECREASE 신호 발생 시 3주에 걸쳐 분산 매도."""

    total_sell_amount: float          # 총 매도 대상 금액
    tranches: List[float]             # [0.50, 0.30, 0.20]
    tranche_idx: int                  # 현재 실행할 인덱스 (0→1→2→완료)
    signal_date: date                 # DECREASE 신호 발생 월요일
    target_weights: Dict[str, float] = field(default_factory=dict)  # 매도 시 비중 기준


@dataclass
class StagedTransitionPlan:
    """DVY/VIG → SCHD 단계 전환 계획 (SCHD 출시 후 1회 실행).

    SCHD 출시일(2011-10-24) 이후 첫 감지 시 생성.
    이후 3회 금요일에 걸쳐 DVY+VIG를 50%→30%→20%씩 매도하고 SCHD로 재투자.
    """

    total_dvy_vig_value: float        # 전환 시작 시 DVY+VIG 총 평가액
    tranches: List[float]             # [0.50, 0.30, 0.20]
    tranche_idx: int                  # 현재 실행할 인덱스 (0→1→2→완료)
    trigger_date: date                # 전환 트리거 감지일 (SCHD 출시 당일 or 이후)


@dataclass
class BacktestResult:
    """백테스트 결과."""

    config: BacktestConfig
    daily_log: pd.DataFrame = field(default_factory=pd.DataFrame)
    trade_log: List[Trade] = field(default_factory=list)
    benchmark_nav: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    metrics: Dict = field(default_factory=dict)
    total_capital_injected: float = 0.0  # DCA 총 투입액 (initial_capital 제외)
    cash_flows: List[Tuple] = field(default_factory=list)      # [(date, amount)] 포트폴리오 XIRR용
    bm_cash_flows: List[Tuple] = field(default_factory=list)   # [(date, amount)] 벤치마크 XIRR용
    final_positions: Dict = field(default_factory=dict)            # 최종 보유 종목 {symbol: {shares, price, value, weight}}
    final_benchmark_positions: Dict = field(default_factory=dict)  # 벤치마크 최종 보유 종목


class BacktestRunner:
    """E2E 백테스트 실행기 — 주간 매매 + DCA."""

    def run(self, config: BacktestConfig) -> BacktestResult:
        logger.info(
            "[Backtest] %s ~ %s, capital=$%.0f, monthly_addition=$%.0f",
            config.start_date, config.end_date,
            config.initial_capital, config.monthly_addition,
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
        policy_df = self._load_snapshot(config, "policy_selection")
        gold_eod_features_df = self._load_gold_eod_features(config)

        # 3) 포트폴리오 + 벤치마크 초기화
        portfolio = Portfolio(cash=config.initial_capital)
        benchmark = Portfolio(cash=config.initial_capital)  # SPY only

        # 4) 상태 변수
        staged_sell: Optional[StagedSellPlan] = None
        bm_staged_sell: Optional[StagedSellPlan] = None
        schd_transition: Optional[StagedTransitionPlan] = None  # DVY/VIG → SCHD 1회 전환

        # 월요일 평가 결과 저장 (화요일 매수에 사용)
        last_monday_action: str = "HOLD"
        last_monday_policy_row: Optional[pd.Series] = None
        last_monday_alloc_row: Optional[pd.Series] = None
        last_monday_universe_df: Optional[pd.DataFrame] = None
        last_monday_target_weights: Dict[str, float] = {}

        total_capital_injected: float = 0.0
        cash_flows: List[Tuple[date, float]] = []     # 포트폴리오 XIRR용
        bm_cash_flows: List[Tuple[date, float]] = []  # 벤치마크 XIRR용
        daily_rows: List[Dict] = []
        bm_nav_rows: List[Dict] = []
        trade_log: List[Trade] = []
        initialized: bool = False
        prev_date: Optional[date] = None

        # 5) 일별 루프
        for td in trade_dates:
            day_prices = self._get_day_prices(prices_df, td)
            if not day_prices:
                continue

            # [1] 초기 매수 (첫 날)
            if not initialized:
                initial_trades = self._initial_buy(portfolio, config, day_prices, td)
                trade_log.extend(initial_trades)
                bm_trades = self._initial_benchmark_buy(benchmark, config, day_prices, td)
                trade_log.extend(bm_trades)
                cash_flows.append((td, -config.initial_capital))     # 최초 자금 투입 (outflow)
                bm_cash_flows.append((td, -config.initial_capital))  # 벤치마크도 동일
                initialized = True

            else:
                # [2] 월 첫 거래일: DCA 자금 투입
                if is_first_of_month(td, prev_date):
                    portfolio.add_cash(config.monthly_addition)
                    benchmark.add_cash(config.monthly_addition)
                    total_capital_injected += config.monthly_addition
                    cash_flows.append((td, -config.monthly_addition))     # DCA 투입 (outflow)
                    bm_cash_flows.append((td, -config.monthly_addition))  # 벤치마크도 동일
                    logger.debug("[Backtest] DCA injection $%.0f on %s", config.monthly_addition, td)

                # [2.5] SCHD 전환 트리거 — 출시일 이후 DVY/VIG 보유 시 1회 생성
                if (
                    schd_transition is None
                    and td >= config.schd_start_date
                    and any(
                        sym in portfolio.positions and portfolio.positions[sym].shares > 0
                        for sym in ["DVY", "VIG"]
                    )
                ):
                    dvy_vig_val = sum(
                        portfolio.positions[sym].market_value(day_prices[sym])
                        for sym in ["DVY", "VIG"]
                        if sym in portfolio.positions
                        and sym in day_prices
                        and portfolio.positions[sym].shares > 0
                    )
                    if dvy_vig_val > 0.01:
                        schd_transition = StagedTransitionPlan(
                            total_dvy_vig_value=dvy_vig_val,
                            tranches=[0.50, 0.30, 0.20],
                            tranche_idx=0,
                            trigger_date=td,
                        )
                        logger.info(
                            "[Backtest] SCHD 전환 계획 생성 on %s — DVY/VIG $%.0f → SCHD (3 Fridays)",
                            td, dvy_vig_val,
                        )

                # [3] 월요일: 신호 평가 (look-ahead 수정: prev_date 신호 사용)
                if td.weekday() == 0:
                    # prev_date = 금요일(마지막 거래일) 종가 기준 신호 (T-1 close, look-ahead 부분 수정)
                    signal_date = prev_date if prev_date is not None else td
                    policy_row = self._get_signal_row(policy_df, signal_date, "trade_date")
                    alloc_row = self._compute_dynamic_allocation(
                        portfolio, day_prices, policy_row, config
                    )
                    universe_df = self._compute_universe_inline(
                        policy_row, gold_eod_features_df, td
                    )
                    action = (
                        str(alloc_row.get("action", "HOLD"))
                        if alloc_row is not None
                        else "HOLD"
                    )

                    # 신호 반전 → 잔여 매도 취소
                    if action != "DECREASE":
                        if staged_sell is not None:
                            logger.debug(
                                "[Backtest] Signal reversal on %s (%s) → cancel staged sell", td, action
                            )
                            staged_sell = None
                        if bm_staged_sell is not None:
                            bm_staged_sell = None

                    # DECREASE → 단계 매도 계획 수립 (PANIC 시 차단, 이미 진행 중이면 유지)
                    risk_gate = (
                        bool(policy_row.get("risk_gate", True))
                        if policy_row is not None
                        else True
                    )

                    # compute_target_weights: 월요일에 미리 계산 (DECREASE + INCREASE 공용)
                    _, monday_target_weights = compute_target_weights(
                        trade_date=td,
                        policy_row=policy_row,
                        allocation_row=alloc_row,
                        universe_df=universe_df,
                        config=config,
                        prices=day_prices,
                    )

                    if action == "DECREASE" and staged_sell is None and risk_gate:
                        staged_sell = self._create_staged_sell(
                            portfolio, alloc_row, day_prices, td,
                            target_weights=monday_target_weights,
                        )
                        bm_staged_sell = self._create_staged_sell(
                            benchmark, alloc_row, day_prices, td,
                            target_weights={"SPY": 1.0},
                        )
                    elif action == "DECREASE" and not risk_gate:
                        logger.debug(
                            "[Backtest] PANIC on %s — DECREASE 차단, HOLD 유지", td
                        )

                    last_monday_action = action
                    last_monday_policy_row = policy_row
                    last_monday_alloc_row = alloc_row
                    last_monday_universe_df = universe_df
                    last_monday_target_weights = monday_target_weights

                # [4] 화요일: 매수 실행 (전 월요일 INCREASE 신호 시)
                elif td.weekday() == 1 and last_monday_action == "INCREASE":
                    if last_monday_target_weights:
                        new_trades = self._execute_weekly_buy(
                            portfolio, last_monday_target_weights, day_prices, td,
                        )
                        trade_log.extend(new_trades)
                        bm_new_trades = self._execute_weekly_buy(
                            benchmark, {"SPY": 1.0}, day_prices, td,
                        )
                        trade_log.extend(bm_new_trades)

            # [5] 금요일: 단계 매도 실행 (PANIC 시 동결 — 계획 유지, 트랜치 건너뜀)
            if td.weekday() == 4:
                # 이번 주 월요일 risk_gate 확인 (PANIC이면 매도 동결)
                friday_risk_gate = (
                    bool(last_monday_policy_row.get("risk_gate", True))
                    if last_monday_policy_row is not None
                    else True
                )

                if staged_sell is not None:
                    if friday_risk_gate:
                        sell_trades = self._execute_sell_tranche(
                            portfolio, staged_sell, day_prices, td
                        )
                        trade_log.extend(sell_trades)
                        staged_sell.tranche_idx += 1
                        if staged_sell.tranche_idx >= len(staged_sell.tranches):
                            staged_sell = None
                    else:
                        logger.debug(
                            "[Backtest] PANIC on %s — 단계 매도 동결 (tranche %d 보류)",
                            td, staged_sell.tranche_idx,
                        )

                if bm_staged_sell is not None:
                    if friday_risk_gate:
                        bm_sell_trades = self._execute_sell_tranche(
                            benchmark, bm_staged_sell, day_prices, td
                        )
                        trade_log.extend(bm_sell_trades)
                        bm_staged_sell.tranche_idx += 1
                        if bm_staged_sell.tranche_idx >= len(bm_staged_sell.tranches):
                            bm_staged_sell = None

                # SCHD 전환 실행 (DVY/VIG → SCHD, PANIC 여부 무관)
                if schd_transition is not None:
                    # 화요일 weekly buy에서 이미 DVY/VIG 청산됐을 경우 계획 취소
                    has_dvy_vig = any(
                        sym in portfolio.positions and portfolio.positions[sym].shares > 0
                        for sym in ["DVY", "VIG"]
                    )
                    if not has_dvy_vig:
                        logger.info(
                            "[Backtest] SCHD 전환 취소 on %s — DVY/VIG 이미 청산됨", td
                        )
                        schd_transition = None
                    else:
                        transition_trades = self._execute_transition_tranche(
                            portfolio, schd_transition, day_prices, td
                        )
                        trade_log.extend(transition_trades)
                        schd_transition.tranche_idx += 1
                        if schd_transition.tranche_idx >= len(schd_transition.tranches):
                            logger.info("[Backtest] SCHD 전환 완료 on %s", td)
                            schd_transition = None

            # [6] 일별 NAV 기록
            nav = portfolio.total_value(day_prices)
            snap = portfolio.snapshot(day_prices)
            daily_rows.append({
                "trade_date": td,
                "nav": round(nav, 2),
                "cash": snap["cash"],
                "invested": snap["invested"],
                "invested_ratio": round(snap["invested"] / nav, 4) if nav > 0 else 0.0,
                "n_positions": len(snap["positions"]),
            })

            # 벤치마크 NAV 기록
            bm_nav_rows.append({
                "trade_date": td,
                "nav": round(benchmark.total_value(day_prices), 2),
            })

            prev_date = td

        # 7) daily_log DataFrame 구성
        daily_log = pd.DataFrame(daily_rows)
        if not daily_log.empty:
            daily_log["trade_date"] = pd.to_datetime(daily_log["trade_date"])
            daily_log = daily_log.set_index("trade_date")

        # 8) 벤치마크 NAV Series 구성
        bm_df = pd.DataFrame(bm_nav_rows)
        if not bm_df.empty:
            benchmark_nav = pd.Series(
                bm_df["nav"].values,
                index=pd.DatetimeIndex(bm_df["trade_date"]),
                name="benchmark_nav",
            )
        else:
            benchmark_nav = pd.Series(dtype=float)

        logger.info(
            "[Backtest] Done — %d days, %d trades, DCA injected=$%.0f",
            len(daily_rows), len(trade_log), total_capital_injected,
        )

        # 9) 성과 지표 산출
        nav_series = daily_log["nav"] if not daily_log.empty else pd.Series(dtype=float)

        # XIRR용 최종 NAV inflow 추가 (마지막 날 전체 청산 가정)
        if daily_rows:
            last_row = daily_rows[-1]
            cash_flows.append((last_row["trade_date"], last_row["nav"]))
        if bm_nav_rows:
            last_bm = bm_nav_rows[-1]
            bm_cash_flows.append((last_bm["trade_date"], last_bm["nav"]))

        metrics = compute_metrics(
            nav_series, benchmark_nav, total_capital_injected, cash_flows=cash_flows
        )

        # 10) 최종 포트폴리오 구성 계산
        def _build_final_positions(pf: Portfolio, prices: Dict[str, float]) -> Dict:
            nav = pf.total_value(prices)
            snap = pf.snapshot(prices)
            pos: Dict = {}
            for sym, data in snap["positions"].items():
                avg_cost = data.get("avg_cost", 0.0)
                cur_price = data["price"]
                gain_pct = (cur_price / avg_cost - 1.0) if avg_cost > 0 else 0.0
                pos[sym] = {
                    "shares": data["shares"],
                    "avg_cost": avg_cost,
                    "price": cur_price,
                    "gain_pct": gain_pct,
                    "value": data["value"],
                    "weight": round(data["value"] / nav, 4) if nav > 0 else 0.0,
                }
            pos["_CASH"] = {
                "shares": None,
                "price": None,
                "value": snap["cash"],
                "weight": round(snap["cash"] / nav, 4) if nav > 0 else 0.0,
            }
            return pos

        final_positions: Dict = {}
        final_benchmark_positions: Dict = {}
        if daily_rows:
            last_td = daily_rows[-1]["trade_date"]
            last_prices = self._get_day_prices(prices_df, last_td)
            final_positions = _build_final_positions(portfolio, last_prices)
            final_benchmark_positions = _build_final_positions(benchmark, last_prices)

        return BacktestResult(
            config=config,
            daily_log=daily_log,
            trade_log=trade_log,
            benchmark_nav=benchmark_nav,
            metrics=metrics,
            total_capital_injected=total_capital_injected,
            cash_flows=cash_flows,
            bm_cash_flows=bm_cash_flows,
            final_positions=final_positions,
            final_benchmark_positions=final_benchmark_positions,
        )

    # ── Private helpers ─────────────────────────────────────

    def _compute_dynamic_allocation(
        self,
        portfolio: Portfolio,
        prices: Dict[str, float],
        policy_row: Optional[pd.Series],
        config: BacktestConfig,
    ) -> Optional[pd.Series]:
        """실제 포트폴리오 상태 기반 동적 allocation 계산."""
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

    def _create_staged_sell(
        self,
        portfolio: Portfolio,
        alloc_row: pd.Series,
        prices: Dict[str, float],
        signal_date: date,
        target_weights: Optional[Dict[str, float]] = None,
    ) -> Optional[StagedSellPlan]:
        """DECREASE 신호 기반 단계 매도 계획 생성.

        총 매도 금액 = current_invested - target_invested.
        target_weights: 매도 시 과매수 종목 우선 정리에 사용.
        """
        current_invested = portfolio.invested_value(prices)
        target_ratio = float(alloc_row.get("next_invested_ratio", 0.0))
        total_value = portfolio.total_value(prices)
        target_invested = total_value * target_ratio
        sell_amount = max(current_invested - target_invested, 0.0)

        if sell_amount < 0.01:
            return None

        return StagedSellPlan(
            total_sell_amount=sell_amount,
            tranches=[0.50, 0.30, 0.20],
            tranche_idx=0,
            signal_date=signal_date,
            target_weights=target_weights or {},
        )

    def _execute_sell_tranche(
        self,
        portfolio: Portfolio,
        plan: StagedSellPlan,
        prices: Dict[str, float],
        trade_date: date,
    ) -> List[Trade]:
        """현재 트랜치 매도 실행.

        target_weights가 있으면 목표 비중 기준으로 과매수 종목을 우선 매도하여
        내부 비율을 정상화한다. 없으면 현재 비율대로 비례 매도(fallback).
        """
        trades: List[Trade] = []
        tranche_ratio = plan.tranches[plan.tranche_idx]
        sell_amount = plan.total_sell_amount * tranche_ratio
        total_invested = portfolio.invested_value(prices)

        if total_invested <= 0 or sell_amount <= 0:
            return trades

        target_weights = plan.target_weights

        if target_weights:
            # target_weights 기반: 목표 비중 대비 과매수분 우선 매도
            target_invested_after = total_invested - sell_amount
            for sym, pos in list(portfolio.positions.items()):
                if sym not in prices or pos.shares <= 0:
                    continue
                sym_current = pos.market_value(prices[sym])
                sym_target = target_invested_after * target_weights.get(sym, 0.0)
                sym_sell = max(sym_current - sym_target, 0.0)
                if sym_sell < 0.01:
                    continue
                t = portfolio.sell(sym, sym_sell, prices[sym])
                if t:
                    t.trade_date = trade_date
                    trades.append(t)
        else:
            # fallback: 현재 비율대로 비례 매도
            for sym, pos in list(portfolio.positions.items()):
                if sym not in prices or pos.shares <= 0:
                    continue
                sym_value = pos.market_value(prices[sym])
                weight = sym_value / total_invested
                sym_sell = sell_amount * weight
                if sym_sell < 0.01:
                    continue
                t = portfolio.sell(sym, sym_sell, prices[sym])
                if t:
                    t.trade_date = trade_date
                    trades.append(t)

        return trades

    def _execute_transition_tranche(
        self,
        portfolio: Portfolio,
        plan: StagedTransitionPlan,
        prices: Dict[str, float],
        trade_date: date,
    ) -> List[Trade]:
        """DVY/VIG → SCHD 단계 전환 트랜치 실행.

        현재 트랜치 비율만큼 DVY+VIG를 비율대로 매도하고,
        판 금액 전액으로 SCHD를 매수한다.
        """
        trades: List[Trade] = []

        # DVY+VIG 현재 평가액
        dvy_vig_now = sum(
            portfolio.positions[sym].market_value(prices[sym])
            for sym in ["DVY", "VIG"]
            if sym in portfolio.positions
            and sym in prices
            and portfolio.positions[sym].shares > 0
        )
        if dvy_vig_now <= 0:
            return trades

        is_last_tranche = plan.tranche_idx == len(plan.tranches) - 1
        if is_last_tranche:
            # 마지막 트랜치: 가격 변동 잔여 없도록 전액 청산
            actual_sell = dvy_vig_now
        else:
            tranche_ratio = plan.tranches[plan.tranche_idx]
            actual_sell = min(plan.total_dvy_vig_value * tranche_ratio, dvy_vig_now)

        # DVY, VIG 비중대로 분산 매도
        total_sold = 0.0
        for sym in ["DVY", "VIG"]:
            if sym not in portfolio.positions or sym not in prices:
                continue
            pos = portfolio.positions[sym]
            if pos.shares <= 0:
                continue
            sym_value = pos.market_value(prices[sym])
            weight = sym_value / dvy_vig_now
            sym_sell = actual_sell * weight
            if sym_sell < 0.01:
                continue
            t = portfolio.sell(sym, sym_sell, prices[sym])
            if t:
                t.trade_date = trade_date
                trades.append(t)
                total_sold += sym_sell

        # SCHD 매수 (판 금액만큼)
        schd_price = prices.get("SCHD", 0.0)
        if schd_price > 0 and total_sold > 0.01:
            t = portfolio.buy("SCHD", total_sold, schd_price)
            if t:
                t.trade_date = trade_date
                trades.append(t)
            logger.debug(
                "[Backtest] SCHD 전환 tranche %d/%d on %s — 매도 $%.0f, SCHD 매수 $%.0f",
                plan.tranche_idx + 1, len(plan.tranches), trade_date, total_sold, total_sold,
            )

        return trades

    def _execute_weekly_buy(
        self,
        portfolio: Portfolio,
        target_weights: Dict[str, float],
        prices: Dict[str, float],
        trade_date: date,
    ) -> List[Trade]:
        """보유 현금 전량 배포 + 기존 포지션 비율 정상화.

        current_invested + cash = total_value 를 target_weights 비율로 리밸런싱.
        - 매도 우선(비중 축소 / 전술 교체) → 매수 순으로 처리
        - 기존 포지션 드리프트(예: SCHD 과비중)도 함께 정상화
        """
        target_invested = portfolio.total_value(prices)  # 현금 포함 전량 배포
        return portfolio.rebalance_to_weights(
            target_weights, prices, target_invested, trade_date
        )

    def _load_gold_eod_features(self, config: BacktestConfig) -> pd.DataFrame:
        """Gold EOD features 로드 (universe inline 계산용)."""
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
        """rebalance_date 기준 universe를 gold_eod features에서 inline 계산."""
        if policy_row is None or gold_eod_features.empty:
            return pd.DataFrame()

        avail = gold_eod_features[gold_eod_features["trade_date"] <= trade_date]
        if avail.empty:
            return pd.DataFrame()
        effective_date = avail["trade_date"].max()

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
        """Strategy snapshot parquet 로드."""
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
        1. 최신 decision_date 행을 우선 선택
        2. 동률(동일 decision_date)이면 source_run_id desc 2차 정렬
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

        if "decision_date" in row.columns:
            row = row[row["decision_date"] == row["decision_date"].max()]

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

    def _initial_benchmark_buy(
        self,
        benchmark: Portfolio,
        config: BacktestConfig,
        prices: Dict[str, float],
        trade_date: date,
    ) -> List[Trade]:
        """벤치마크(SPY only) 초기 매수."""
        spy_price = prices.get("SPY", 0.0)
        if spy_price <= 0:
            return []

        amount = config.initial_capital * config.initial_invested_ratio
        t = benchmark.buy("SPY", amount, spy_price)
        if t:
            t.trade_date = trade_date
            return [t]
        return []


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
        "--monthly-addition", type=float, default=None,
        help="월별 자금 추가액 (기본: preset 설정값)",
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
    if args.monthly_addition is not None:
        overrides["monthly_addition"] = args.monthly_addition

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
