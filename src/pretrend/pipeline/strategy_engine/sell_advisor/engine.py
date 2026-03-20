"""
Sell Advisor Engine — HOW_MUCH_TO_SELL 경계.

Advisory 출력: 실제 매도 실행은 Backtest runner(_execute_sell_tranche)가 담당한다.
v0: 매도 예산(sell_budget_ratio)과 우선순위(sell_priority_list)만 정의.
종목별 정밀 매도 비율은 다루지 않는다.

SOT: docs/strategy_engine_design.md §D3, §F
"""
from __future__ import annotations

import logging
from typing import List

import pandas as pd

from .schema import SELL_ADVICE_OUTPUT_COLUMNS

logger = logging.getLogger(__name__)


def build_sell_advice(
    allocation: pd.DataFrame,
    policy_selection: pd.DataFrame,
    universe: pd.DataFrame,
) -> pd.DataFrame:
    """Sell advice를 생성한다.

    Parameters
    ----------
    allocation : DataFrame
        build_allocation() 출력 (action, delta_ratio 등).
    policy_selection : DataFrame
        build_policy_selection() 출력 (상태 벡터 + policy).
    universe : DataFrame
        build_universe() 출력 (후보 목록).

    Returns
    -------
    DataFrame with SELL_ADVICE_OUTPUT_COLUMNS.

    Notes
    -----
    Advisory 출력: sell_budget_ratio / sell_priority_list 는 참고값이며
    실제 매도 실행은 Backtest runner(_execute_sell_tranche, target_weights 기반)가 담당한다.
    """
    if allocation.empty:
        return pd.DataFrame(columns=SELL_ADVICE_OUTPUT_COLUMNS)

    rows = []
    for _, alloc_row in allocation.iterrows():
        td = alloc_row["trade_date"]
        action = alloc_row.get("action", "HOLD")
        delta = alloc_row.get("delta_ratio", 0.0)

        # DECREASE일 때만 매도 예산 발생
        if action == "DECREASE" and delta < 0:
            sell_budget = abs(delta)
        else:
            sell_budget = 0.0

        # 매도 우선순위: v0에서는 단순 역순 (Core는 마지막, Tactical 먼저)
        priority: List[str] = []
        rationale: List[str] = []

        if sell_budget > 0:
            # universe에서 해당 날짜 후보 추출 (decision_date 우선, rebalance_date fallback)
            _date_col = "decision_date" if "decision_date" in universe.columns else "rebalance_date"
            univ_td = universe[universe[_date_col] == td] if not universe.empty and _date_col in universe.columns else pd.DataFrame()
            if not univ_td.empty:
                # relative_strength 오름차순 (약한 것 먼저 매도)
                sorted_univ = univ_td.sort_values("relative_strength", ascending=True)
                priority = sorted_univ["symbol"].tolist()
            rationale.append(f"decrease_action:delta={delta:.4f}")
        else:
            rationale.append("no_sell_needed")

        rows.append({
            "decision_date": td,
            "sell_budget_ratio": round(sell_budget, 4),
            "sell_priority_list": priority,
            "rationale_tags": rationale,
            "execution_notes": [],
        })

    return pd.DataFrame(rows, columns=SELL_ADVICE_OUTPUT_COLUMNS)
