"""
Allocation Engine — HOW_MUCH_EXPOSURE 경계.

Composer(policy_selection) 출력 + 이전 invested_ratio → 조정 액션.

Contract: docs/architecture/allocation_engine_contract.md
SOT: docs/strategy_engine_design.md §D2, §F

v0 규칙:
  1. 현재 비율이 목표 범위 내 → HOLD
  2. 범위 밖 → adjustment_limit 이내 이동
  3. risk_gate=false → INCREASE 금지
  4. run_universe=false → INCREASE 금지
  5. next_invested_ratio ∈ [0.0, 1.0]
  6. step_size 단위 양자화 (ROUND_DOWN)
"""
from __future__ import annotations

import logging
import math
from typing import List

import pandas as pd

from .schema import ACTION_ENUM, ALLOCATION_OUTPUT_COLUMNS

logger = logging.getLogger(__name__)


def _quantize(value: float, step: float, policy: str = "ROUND_DOWN") -> float:
    """step_size 단위로 양자화.

    부동소수점 오차 보정: 0.30-0.20=0.09999...98 같은 경우
    floor(1.999...)=1 대신 floor(2.000...)=2 로 정확히 처리.
    """
    if step <= 0:
        return value
    steps = value / step
    if policy == "ROUND_DOWN":
        return math.floor(steps + 1e-9) * step
    return round(steps) * step


def _compute_allocation(
    current: float,
    lower: float,
    upper: float,
    adj_limit: float,
    step_size: float,
    risk_gate: bool,
    run_universe: bool,
) -> dict:
    """단일 trade_date 조정 로직."""
    notes: List[str] = []

    # 목표 범위 내 → HOLD
    if lower <= current <= upper:
        return {
            "action": "HOLD",
            "next_invested_ratio": current,
            "delta_ratio": 0.0,
            "blocked_by_risk_gate": False,
            "notes": ["in_target_range"],
        }

    # 목표 결정
    if current < lower:
        # 증가 필요
        if not risk_gate:
            notes.append("increase_blocked_by_risk_gate")
            return {
                "action": "HOLD",
                "next_invested_ratio": current,
                "delta_ratio": 0.0,
                "blocked_by_risk_gate": True,
                "notes": notes,
            }
        if not run_universe:
            notes.append("increase_blocked_by_run_universe")
            return {
                "action": "HOLD",
                "next_invested_ratio": current,
                "delta_ratio": 0.0,
                "blocked_by_risk_gate": False,
                "notes": notes,
            }

        raw_delta = min(lower - current, adj_limit)
        delta = _quantize(raw_delta, step_size)
        if delta <= 0:
            delta = 0.0
            action = "HOLD"
        else:
            action = "INCREASE"

        next_ratio = min(current + delta, 1.0)
        notes.append(f"target_lower={lower}")
        return {
            "action": action,
            "next_invested_ratio": round(next_ratio, 4),
            "delta_ratio": round(delta, 4),
            "blocked_by_risk_gate": False,
            "notes": notes,
        }

    else:
        # current > upper → 감소 필요
        raw_delta = min(current - upper, adj_limit)
        delta = _quantize(raw_delta, step_size)
        if delta <= 0:
            delta = 0.0
            action = "HOLD"
        else:
            action = "DECREASE"

        next_ratio = max(current - delta, 0.0)
        notes.append(f"target_upper={upper}")
        return {
            "action": action,
            "next_invested_ratio": round(next_ratio, 4),
            "delta_ratio": round(-delta, 4),
            "blocked_by_risk_gate": False,
            "notes": notes,
        }


def build_allocation(
    policy_selection: pd.DataFrame,
    current_invested_ratio: float,
) -> pd.DataFrame:
    """Allocation 조정을 계산한다.

    Parameters
    ----------
    policy_selection : DataFrame
        build_policy_selection() 출력.
    current_invested_ratio : float
        현재 총 투자 비율.

    Returns
    -------
    DataFrame with ALLOCATION_OUTPUT_COLUMNS.
    """
    if policy_selection.empty:
        return pd.DataFrame(columns=ALLOCATION_OUTPUT_COLUMNS)

    rows = []
    curr = current_invested_ratio

    for _, ps_row in policy_selection.iterrows():
        result = _compute_allocation(
            current=curr,
            lower=ps_row["target_invested_lower"],
            upper=ps_row["target_invested_upper"],
            adj_limit=ps_row["adjustment_limit"],
            step_size=ps_row["step_size"],
            risk_gate=bool(ps_row.get("risk_gate", True)),
            run_universe=bool(ps_row.get("run_universe", True)),
        )
        result["trade_date"] = ps_row["trade_date"]
        rows.append(result)
        # 다음 주기 current 갱신
        curr = result["next_invested_ratio"]

    return pd.DataFrame(rows, columns=ALLOCATION_OUTPUT_COLUMNS)
