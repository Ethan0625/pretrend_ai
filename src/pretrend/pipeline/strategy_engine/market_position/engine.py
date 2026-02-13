"""
Market Position Engine — Axis×Horizon State → 표준 상태 벡터.

run_universe, risk_gate 판정 로직.
Composer 계약의 핵심 상태 벡터 생성 단계.

SOT: docs/strategy_engine_design.md §A3
Contract: docs/architecture/market_structure_composer_contract.md §4, §6

v0 판정 규칙 (상태 조합 기반):
  run_universe: long=RECESSION + mid=RISK_OFF → false, 그 외 true
  risk_gate: short=PANIC → false, 그 외 true
"""
from __future__ import annotations

import logging
from typing import List, Optional

import pandas as pd

from ..axis_horizon_state.schema import LONG_PHASE_ENUM, MID_REGIME_ENUM, SHORT_SIGNAL_ENUM
from .schema import MARKET_POSITION_COLUMNS

logger = logging.getLogger(__name__)


def _judge_run_universe(long_phase: str, mid_regime: str) -> bool:
    """Universe 실행 여부 판정 (v0 규칙)."""
    # RECESSION + RISK_OFF → 신규 매수 허용 안 함
    if long_phase == "RECESSION" and mid_regime == "RISK_OFF":
        return False
    # SLOWDOWN + RISK_OFF → 보수적 제한
    if long_phase == "SLOWDOWN" and mid_regime == "RISK_OFF":
        return False
    return True


def _judge_risk_gate(short_signal: str) -> bool:
    """Allocation 증가 허용 여부 판정 (v0 규칙)."""
    # PANIC 시 증가 차단
    if short_signal == "PANIC":
        return False
    return True


def _build_notes(long_phase: str, mid_regime: str, short_signal: str,
                 run_universe: bool, risk_gate: bool) -> List[str]:
    """판정 근거 태그 생성."""
    notes = []
    if not run_universe:
        notes.append(f"universe_blocked:{long_phase}+{mid_regime}")
    if not risk_gate:
        notes.append(f"risk_gate_blocked:{short_signal}")
    if run_universe and risk_gate:
        notes.append("all_clear")
    return notes


def build_market_position(
    axis_horizon_state: pd.DataFrame,
    run_id: str = "",
) -> pd.DataFrame:
    """Axis×Horizon State를 Market Position 상태 벡터로 변환한다.

    Parameters
    ----------
    axis_horizon_state : DataFrame
        build_axis_horizon_state() 출력. (trade_date, long_phase, mid_regime, short_signal, ...)
    run_id : str
        Lineage run ID.

    Returns
    -------
    DataFrame with MARKET_POSITION_COLUMNS.
    """
    if axis_horizon_state.empty:
        logger.warning("[MarketPosition] Empty input")
        return pd.DataFrame(columns=MARKET_POSITION_COLUMNS)

    rows = []
    for _, row in axis_horizon_state.iterrows():
        lp = row.get("long_phase", "UNKNOWN")
        mr = row.get("mid_regime", "UNKNOWN")
        ss = row.get("short_signal", "UNKNOWN")

        # ENUM 강제
        if lp not in LONG_PHASE_ENUM:
            lp = "UNKNOWN"
        if mr not in MID_REGIME_ENUM:
            mr = "UNKNOWN"
        if ss not in SHORT_SIGNAL_ENUM:
            ss = "UNKNOWN"

        run_universe = _judge_run_universe(lp, mr)
        risk_gate = _judge_risk_gate(ss)
        notes = _build_notes(lp, mr, ss, run_universe, risk_gate)

        rows.append({
            "trade_date": row["trade_date"],
            "long_phase": lp,
            "mid_regime": mr,
            "short_signal": ss,
            "run_universe": run_universe,
            "risk_gate": risk_gate,
            "notes": notes,
            "source_run_id": run_id,
        })

    return pd.DataFrame(rows, columns=MARKET_POSITION_COLUMNS)
