"""
Backtest Allocation — 버전별 allocation 함수 + 레지스트리.

각 preset 버전에 대응하는 allocation 로직을 독립 함수로 분리.
새 버전 추가 시: 함수 정의 → ALLOCATION_REGISTRY 등록 → runner.py 변경 없음.

Contract:
  - run_universe=false → INCREASE 금지 (모든 버전 공통)
  - risk_gate=false  → INCREASE 허용 (저점매수), DECREASE는 runner.py에서 동결 처리
  - DECREASE는 run_universe 무관하게 허용
  - next_invested_ratio ∈ [0.0, 1.0]
  - step_size 단위 양자화 (ROUND_DOWN)
"""
from __future__ import annotations

import logging
import math
from typing import Callable, Dict, Optional

import pandas as pd

logger = logging.getLogger(__name__)

_SENTINEL = object()


def _quantize(value: float, step: float) -> float:
    """step 단위 ROUND_DOWN 양자화 (부동소수점 오차 보정)."""
    if step <= 0:
        return value
    return math.floor(value / step + 1e-9) * step


def _apply_delta(
    current: float,
    target: float,
    adj_limit: float,
    step_size: float,
    risk_gate: bool,
    run_universe: bool,
    notes_prefix: str = "",
) -> dict:
    """target까지 gradual movement 로직 (v1/v2 공통).

    Parameters
    ----------
    current : float
        현재 invested_ratio.
    target : float
        목표 invested_ratio.
    adj_limit : float
        한 번에 이동 가능한 최대 delta.
    step_size : float
        양자화 단위.
    risk_gate : bool
        False이면 INCREASE 차단.
    run_universe : bool
        False이면 INCREASE 차단.
    notes_prefix : str
        notes 태그 접두어.
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
        # risk_gate=False(PANIC)여도 INCREASE 허용 — 저점매수 목적
        # PANIC 중 매도 동결은 runner.py(staged sell freeze)에서 처리
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


def compute_allocation_v0(current: float, policy_row: pd.Series, config) -> dict:
    """v0: range-maintenance (policy_row의 target_invested_lower/upper 사용)."""
    from pretrend.pipeline.strategy_engine.allocation.engine import _compute_allocation

    return _compute_allocation(
        current=current,
        lower=float(policy_row.get("target_invested_lower", 0.10)),
        upper=float(policy_row.get("target_invested_upper", 0.60)),
        adj_limit=float(policy_row.get("adjustment_limit", config.allocation_adjustment_limit)),
        step_size=float(policy_row.get("step_size", config.allocation_step_size)),
        risk_gate=bool(policy_row.get("risk_gate", True)),
        run_universe=bool(policy_row.get("run_universe", True)),
    )


def compute_allocation_v1(current: float, policy_row: pd.Series, config) -> dict:
    """v1: f(long_phase) target-seeking.

    기존 runner.py의 _target_seeking_allocation() 로직 + run_universe 버그 수정.
    """
    long_phase = str(policy_row.get("long_phase", "UNKNOWN"))
    risk_gate = bool(policy_row.get("risk_gate", True))
    run_universe = bool(policy_row.get("run_universe", True))

    target = config.target_ratio_map.get(
        long_phase,
        config.target_ratio_map.get("UNKNOWN", 0.40),
    )

    return _apply_delta(
        current=current,
        target=target,
        adj_limit=config.allocation_adjustment_limit,
        step_size=config.allocation_step_size,
        risk_gate=risk_gate,
        run_universe=run_universe,
        notes_prefix=f"phase:{long_phase},",
    )


def compute_allocation_v2(current: float, policy_row: pd.Series, config) -> dict:
    """v2: f(long_phase, mid_regime) 2D lookup.

    Fallback 4단계:
      1. (long_phase, mid_regime)
      2. (long_phase, "UNKNOWN")
      3. ("UNKNOWN", mid_regime)
      4. ("UNKNOWN", "UNKNOWN")
    """
    long_phase = str(policy_row.get("long_phase", "UNKNOWN"))
    mid_regime = str(policy_row.get("mid_regime", "UNKNOWN"))
    risk_gate = bool(policy_row.get("risk_gate", True))
    run_universe = bool(policy_row.get("run_universe", True))

    m = config.target_ratio_map_v2
    target = None
    for key in [
        (long_phase, mid_regime),
        (long_phase, "UNKNOWN"),
        ("UNKNOWN", mid_regime),
        ("UNKNOWN", "UNKNOWN"),
    ]:
        val = m.get(key, _SENTINEL)
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
        current=current,
        target=target,
        adj_limit=config.allocation_adjustment_limit,
        step_size=config.allocation_step_size,
        risk_gate=risk_gate,
        run_universe=run_universe,
        notes_prefix=f"phase:{long_phase},mid:{mid_regime},",
    )


def compute_allocation_v3(current: float, policy_row: pd.Series, config) -> dict:
    """v3: f(long_phase, mid_regime, next_step_bias) target-seeking.

    base_target는 v2와 동일한 2D lookup을 사용하고,
    next_step_bias_20d로 soft adjustment를 적용한다.
    """
    long_phase = str(policy_row.get("long_phase", "UNKNOWN"))
    mid_regime = str(policy_row.get("mid_regime", "UNKNOWN"))
    next_bias = str(
        policy_row.get(
            "next_step_bias_effective",
            policy_row.get("next_step_bias_20d", "UNKNOWN"),
        )
    )
    risk_gate = bool(policy_row.get("risk_gate", True))
    run_universe = bool(policy_row.get("run_universe", True))

    m = config.target_ratio_map_v3 or config.target_ratio_map_v2 or {}
    target = None
    for key in [
        (long_phase, mid_regime),
        (long_phase, "UNKNOWN"),
        ("UNKNOWN", mid_regime),
        ("UNKNOWN", "UNKNOWN"),
    ]:
        val = m.get(key, _SENTINEL)
        if val is not _SENTINEL:
            target = val
            break

    if target is None:
        target = 0.40

    bias_adj = {
        "RISK_ON_BIAS": +0.05,
        "NEUTRAL_BIAS": 0.00,
        "RISK_OFF_BIAS": -0.05,
        "UNKNOWN": 0.00,
    }.get(next_bias, 0.00)
    target = max(0.0, min(1.0, float(target) + bias_adj))

    return _apply_delta(
        current=current,
        target=target,
        adj_limit=config.allocation_adjustment_limit,
        step_size=config.allocation_step_size,
        risk_gate=risk_gate,
        run_universe=run_universe,
        notes_prefix=f"phase:{long_phase},mid:{mid_regime},next:{next_bias},",
    )


# ── Registry ──────────────────────────────────────────────────────────────────

ALLOCATION_REGISTRY: Dict[str, Callable] = {
    "v0": compute_allocation_v0,
    "v1": compute_allocation_v1,
    "v2": compute_allocation_v2,
    "v3": compute_allocation_v3,
    "v3.1": compute_allocation_v3,
    "v3.2": compute_allocation_v3,
    "v3.3": compute_allocation_v3,
    "v3.4": compute_allocation_v3,
    "v3.4.1": compute_allocation_v3,
    "v3.4.1-sim": compute_allocation_v3,
    "v3.4.1-schd-floor-20": compute_allocation_v3,
    "v3.4.2-phase": compute_allocation_v3,
    "v3.4.2a": compute_allocation_v3,
}


def dispatch_allocation(
    preset_name: str,
    current: float,
    policy_row: Optional[pd.Series],
    config,
) -> dict:
    """preset_name으로 allocation 함수를 dispatch한다.

    미등록 preset_name → v0 fallback (경고 로그 출력).
    """
    if policy_row is None:
        return {
            "action": "HOLD",
            "next_invested_ratio": current,
            "delta_ratio": 0.0,
            "blocked_by_risk_gate": False,
            "notes": ["no_policy_row"],
        }

    fn = ALLOCATION_REGISTRY.get(preset_name)
    if fn is None:
        logger.warning(
            "[AllocationDispatch] Unknown preset %r → fallback v0", preset_name
        )
        fn = compute_allocation_v0

    return fn(current, policy_row, config)
