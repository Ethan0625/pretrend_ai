"""
월별 리밸런싱 로직 — Strategy Engine 출력 기반 비중 결정 + 섹터 교체.

비중 결정 흐름:
1. allocation → target_invested_ratio (총 투자 비율)
2. core weights → SCHD/SPY/IAU (기본 비중)
3. universe → is_candidate + relative_strength 기반 전술 종목 교체

전술 교체 조건:
- run_universe=true AND risk_gate=true
- Universe v1 is_candidate=True ETF 중 SPY보다 RS 높은 종목을 tactical slot 편입
- phase 기반 차단 없음 — Universe v1 phase eligible pool이 이미 처리
- tactical 1개당 15% → core 전체에서 비율대로 차감
"""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .config import BacktestConfig


def compute_target_weights(
    trade_date: date,
    policy_row: Optional[pd.Series],
    allocation_row: Optional[pd.Series],
    universe_df: Optional[pd.DataFrame],
    config: BacktestConfig,
    prices: Dict[str, float],
) -> Tuple[float, Dict[str, float]]:
    """리밸런싱 목표 비중을 결정한다.

    Returns
    -------
    (target_invested_ratio, target_weights)
    target_weights: {symbol: weight} — invested 기준, 합계≈1.0
    """
    # 1) target_invested_ratio
    if allocation_row is not None and "next_invested_ratio" in allocation_row.index:
        target_invested_ratio = float(allocation_row["next_invested_ratio"])
    else:
        target_invested_ratio = config.initial_invested_ratio

    # 2) core weights
    weights = config.active_weights(trade_date)

    # 3) 전술 교체 판단
    if _should_run_tactical(policy_row):
        tactical_symbols = _pick_tactical(
            universe_df, prices, config, trade_date
        )
        if tactical_symbols:
            weights = _apply_tactical(weights, tactical_symbols, config, trade_date)

    return target_invested_ratio, weights


def _should_run_tactical(policy_row: Optional[pd.Series]) -> bool:
    """전술 포지션 교체 조건 충족 여부.

    phase 체크 없음 — Universe v1 phase eligible pool이 이미 처리.
    """
    if policy_row is None:
        return False

    run_universe = policy_row.get("run_universe", False)
    risk_gate = policy_row.get("risk_gate", False)
    return bool(run_universe and risk_gate)


def _pick_tactical(
    universe_df: Optional[pd.DataFrame],
    prices: Dict[str, float],
    config: BacktestConfig,
    trade_date: date,
) -> List[str]:
    """universe에서 tactical group의 relative_strength 상위 종목을 선택한다.

    SPY보다 relative_strength가 높은 ETF만 tactical 후보.
    최대 max_tactical_slots개.
    tactical_groups는 config에서 설정 (v0: ["SECTOR"], v1: ["SECTOR", "COMMODITY"]).
    """
    if universe_df is None or universe_df.empty:
        return []

    # 해당 날짜 universe (가장 가까운 rebalance_date)
    if "rebalance_date" in universe_df.columns:
        df = universe_df[universe_df["rebalance_date"] <= trade_date]
        if df.empty:
            return []
        latest = df["rebalance_date"].max()
        df = df[df["rebalance_date"] == latest]
    else:
        df = universe_df

    # 설정된 tactical groups 필터
    candidates = df[df["asset_group"].isin(config.tactical_groups)].copy()
    # Universe v1 is_candidate 필터: Strategy Engine 선정 결과 준수
    if "is_candidate" in candidates.columns:
        candidates = candidates[candidates["is_candidate"] == True]
    if candidates.empty:
        return []

    # SPY relative_strength (벤치마크)
    spy_row = df[df["symbol"] == "SPY"]
    spy_rs = float(spy_row["relative_strength"].iloc[0]) if not spy_row.empty else 0.0

    # SPY보다 강한 종목만
    candidates = candidates[candidates["relative_strength"] > spy_rs]
    if candidates.empty:
        return []

    # 가격이 있는 종목만
    candidates = candidates[candidates["symbol"].isin(prices.keys())]
    if candidates.empty:
        return []

    # relative_strength 내림차순 상위 N개
    candidates = candidates.sort_values("relative_strength", ascending=False)
    return candidates["symbol"].tolist()[: config.max_tactical_slots]


def _apply_tactical(
    base_weights: Dict[str, float],
    tactical_symbols: List[str],
    config: BacktestConfig,
    trade_date: date,
) -> Dict[str, float]:
    """전술 종목을 편입하고 core 비중을 조정한다.

    전술 비중은 core 전체에서 비율대로 차감 → core 내 비율 유지 (5:3:2 등).
    """
    weights = dict(base_weights)
    n = len(tactical_symbols)
    if n == 0:
        return weights

    tactical_total = n * config.tactical_weight
    core_total = sum(weights.values())
    if core_total <= 0:
        return weights

    # core 각 종목이 최소 0.05 유지 가능한지 검증 → 초과 시 slots 축소
    max_deductable = sum(max(0.0, w - 0.05) for w in weights.values())
    if tactical_total > max_deductable:
        max_slots = int(max_deductable / config.tactical_weight)
        if max_slots <= 0:
            return weights
        tactical_symbols = tactical_symbols[:max_slots]
        n = len(tactical_symbols)
        tactical_total = n * config.tactical_weight

    # core 비례 차감 (기존 비율 그대로 유지)
    for sym in list(weights.keys()):
        weights[sym] = max(0.05, weights[sym] - tactical_total * (weights[sym] / core_total))

    for sym in tactical_symbols:
        weights[sym] = config.tactical_weight

    return weights


def is_rebalance_day(
    trade_date: date,
    prev_trade_date: Optional[date],
    freq: str = "monthly",
) -> bool:
    """매월 첫 영업일 판단."""
    if freq != "monthly":
        return False
    if prev_trade_date is None:
        return True  # 첫 날
    return trade_date.month != prev_trade_date.month


def is_first_of_month(trade_date: date, prev_date: Optional[date]) -> bool:
    """월 첫 거래일 판단 (DCA 자금 투입 트리거).

    최초 거래일(prev_date=None)에는 미투입.
    """
    if prev_date is None:
        return False
    return trade_date.month != prev_date.month
