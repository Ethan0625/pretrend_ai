"""
Allocation Engine — HOW_MUCH_EXPOSURE 경계.

Composer(policy_selection) 출력 + 이전 invested_ratio → 조정 액션.

Contract: docs/architecture/allocation_engine_contract.md
SOT: docs/strategy_engine_design.md §D2, §F

v0 규칙 (range-maintenance):
  1. 현재 비율이 목표 범위 내 → HOLD
  2. 범위 밖 → adjustment_limit 이내 이동
  3. risk_gate=false → INCREASE 금지 (is_panic=True)
  4. run_universe=false → INCREASE 금지
  5. next_invested_ratio ∈ [0.0, 1.0]
  6. step_size 단위 양자화 (ROUND_DOWN)

v1 규칙 (target-seeking, f(long_phase)):
  - long_phase → 목표 비율 조회 (_ALLOCATION_V1_MAP)
  - 목표로 gradual movement (adj_limit, step_size)
  - risk_gate=false → INCREASE 허용 (저점매수, is_panic=True)
  - run_universe=false → INCREASE 금지

v2 규칙 (2D lookup, f(long_phase, mid_regime)):
  - (long_phase, mid_regime) → 목표 비율 조회 (_ALLOCATION_V2_MAP, 4단계 fallback)
  - 이후 v1과 동일 gradual movement 규칙
"""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .schema import ACTION_ENUM, ALLOCATION_OUTPUT_COLUMNS

logger = logging.getLogger(__name__)

_SENTINEL = object()


# ── v1 target map ─────────────────────────────────────────────────────────────

_ALLOCATION_V1_MAP: Dict[str, float] = {
    "EXPANSION": 0.60,
    "RECOVERY": 0.60,
    "LATE_CYCLE": 0.60,
    "SLOWDOWN": 0.20,
    "RECESSION": 0.10,
    "UNKNOWN": 0.40,
}

# ── v2 target map (long_phase, mid_regime) ────────────────────────────────────

_ALLOCATION_V2_MAP: Dict[Tuple[str, str], float] = {
    ("EXPANSION", "RISK_ON"): 0.80,  ("EXPANSION", "NEUTRAL"): 0.70,
    ("EXPANSION", "RISK_OFF"): 0.55, ("EXPANSION", "UNKNOWN"): 0.65,
    ("LATE_CYCLE", "RISK_ON"): 0.60, ("LATE_CYCLE", "NEUTRAL"): 0.45,
    ("LATE_CYCLE", "RISK_OFF"): 0.30, ("LATE_CYCLE", "UNKNOWN"): 0.45,
    ("SLOWDOWN", "RISK_ON"): 0.35,   ("SLOWDOWN", "NEUTRAL"): 0.25,
    ("SLOWDOWN", "RISK_OFF"): 0.15,  ("SLOWDOWN", "UNKNOWN"): 0.25,
    ("RECOVERY", "RISK_ON"): 0.70,   ("RECOVERY", "NEUTRAL"): 0.60,
    ("RECOVERY", "RISK_OFF"): 0.45,  ("RECOVERY", "UNKNOWN"): 0.60,
    ("RECESSION", "RISK_ON"): 0.20,  ("RECESSION", "NEUTRAL"): 0.10,
    ("RECESSION", "RISK_OFF"): 0.05, ("RECESSION", "UNKNOWN"): 0.10,
    ("UNKNOWN", "RISK_ON"): 0.50,    ("UNKNOWN", "NEUTRAL"): 0.40,
    ("UNKNOWN", "RISK_OFF"): 0.30,   ("UNKNOWN", "UNKNOWN"): 0.40,
}


def _apply_delta(
    current: float,
    target: float,
    adj_limit: float,
    step_size: float,
    risk_gate: bool,
    run_universe: bool,
    notes_prefix: str = "",
) -> dict:
    """target까지 gradual movement — v1/v2 공통 헬퍼.

    PANIC(risk_gate=False)이어도 INCREASE 허용 (저점매수).
    run_universe=False 시 INCREASE 차단.
    """
    raw_delta = target - current

    if abs(raw_delta) < step_size:
        return {
            "action": "HOLD",
            "next_invested_ratio": current,
            "delta_ratio": 0.0,
            "blocked_by_risk_gate": False,
            "notes": [f"{notes_prefix}at_target:{target}"],
        }

    if raw_delta > 0:
        if not run_universe:
            return {
                "action": "HOLD",
                "next_invested_ratio": current,
                "delta_ratio": 0.0,
                "blocked_by_risk_gate": False,
                "notes": [f"{notes_prefix}increase_blocked_by_run_universe"],
            }
        delta = _quantize(min(raw_delta, adj_limit), step_size)
        action = "INCREASE" if delta > 0 else "HOLD"
        next_ratio = round(min(current + delta, 1.0), 4)
    else:
        delta = _quantize(min(abs(raw_delta), adj_limit), step_size)
        action = "DECREASE" if delta > 0 else "HOLD"
        next_ratio = round(max(current - delta, 0.0), 4)

    return {
        "action": action,
        "next_invested_ratio": next_ratio,
        "delta_ratio": round(next_ratio - current, 4),
        "blocked_by_risk_gate": False,
        "notes": [f"{notes_prefix}target:{target}"],
    }


def _compute_allocation_v1(current: float, ps_row: pd.Series) -> dict:
    """v1: f(long_phase) target-seeking."""
    long_phase = str(ps_row.get("long_phase", "UNKNOWN"))
    risk_gate = bool(ps_row.get("risk_gate", True))
    run_universe = bool(ps_row.get("run_universe", True))
    adj_limit = float(ps_row.get("adjustment_limit", 0.10))
    step_size = float(ps_row.get("step_size", 0.05))
    target = _ALLOCATION_V1_MAP.get(long_phase, _ALLOCATION_V1_MAP["UNKNOWN"])
    return _apply_delta(
        current, target, adj_limit, step_size, risk_gate, run_universe,
        notes_prefix=f"phase:{long_phase},",
    )


def _compute_allocation_v2(current: float, ps_row: pd.Series) -> dict:
    """v2: f(long_phase, mid_regime) 2D lookup.

    Fallback 4단계:
      1. (long_phase, mid_regime)
      2. (long_phase, "UNKNOWN")
      3. ("UNKNOWN", mid_regime)
      4. ("UNKNOWN", "UNKNOWN")
    """
    long_phase = str(ps_row.get("long_phase", "UNKNOWN"))
    mid_regime = str(ps_row.get("mid_regime", "UNKNOWN"))
    risk_gate = bool(ps_row.get("risk_gate", True))
    run_universe = bool(ps_row.get("run_universe", True))
    adj_limit = float(ps_row.get("adjustment_limit", 0.10))
    step_size = float(ps_row.get("step_size", 0.05))

    target: Optional[float] = None
    for key in [
        (long_phase, mid_regime),
        (long_phase, "UNKNOWN"),
        ("UNKNOWN", mid_regime),
        ("UNKNOWN", "UNKNOWN"),
    ]:
        val = _ALLOCATION_V2_MAP.get(key, _SENTINEL)
        if val is not _SENTINEL:
            target = val
            break

    if target is None:
        logger.warning(
            "[AllocationV2] No fallback found for (%s, %s) → using 0.40",
            long_phase, mid_regime,
        )
        target = 0.40

    return _apply_delta(
        current, target, adj_limit, step_size, risk_gate, run_universe,
        notes_prefix=f"phase:{long_phase},mid:{mid_regime},",
    )


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


_VALID_ALLOCATION_MODES = frozenset({"v0", "v1", "v2"})


def build_allocation(
    policy_selection: pd.DataFrame,
    current_invested_ratio: float,
    allocation_mode: str = "v0",
) -> pd.DataFrame:
    """Allocation 조정을 계산한다.

    Parameters
    ----------
    policy_selection : DataFrame
        build_policy_selection() 출력.
    current_invested_ratio : float
        현재 총 투자 비율.
    allocation_mode : str
        "v0" (range-maintenance, 기본값) | "v1" (target-seeking) | "v2" (2D lookup).

    Returns
    -------
    DataFrame with ALLOCATION_OUTPUT_COLUMNS.
    """
    if policy_selection.empty:
        return pd.DataFrame(columns=ALLOCATION_OUTPUT_COLUMNS)

    if allocation_mode not in _VALID_ALLOCATION_MODES:
        logger.warning(
            "[Allocation] Unknown allocation_mode %r → fallback v0", allocation_mode
        )
        allocation_mode = "v0"

    rows = []
    curr = current_invested_ratio

    for _, ps_row in policy_selection.iterrows():
        if allocation_mode == "v1":
            result = _compute_allocation_v1(curr, ps_row)
        elif allocation_mode == "v2":
            result = _compute_allocation_v2(curr, ps_row)
        else:
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
