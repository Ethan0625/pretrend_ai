"""
Long Phase Engine — 장기 사이클 위치 판정.

REQUIRED axis: macro_policy
OPTIONAL axis: price_volatility, flow_structure

Contract: docs/architecture/market_structure_long_v1_contract.md
SOT: docs/strategy_engine_design.md §A3

v0 라벨 로직 (placeholder — 규칙 기반):
  regime 다수결 + delta_6m 방향 → phase 매핑
  결측 시 UNKNOWN (fail-open)
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from .schema import LONG_PHASE_ENUM, LONG_OUTPUT_COLUMNS

logger = logging.getLogger(__name__)


def _classify_long_phase(regime: Optional[str], delta_6m: Optional[float]) -> str:
    """단일 trade_date에 대한 long phase 판정 (v0 규칙)."""
    if regime is None or pd.isna(regime):
        return "UNKNOWN"

    regime = str(regime).lower()

    if delta_6m is None or pd.isna(delta_6m):
        # delta_6m 결측 시 regime만으로 판정
        if regime == "tightening":
            return "LATE_CYCLE"
        elif regime == "easing":
            return "RECOVERY"
        elif regime == "neutral":
            return "EXPANSION"
        return "UNKNOWN"

    # regime + delta_6m 조합 판정
    if regime == "tightening":
        return "SLOWDOWN" if delta_6m < 0 else "LATE_CYCLE"
    elif regime == "easing":
        return "RECESSION" if delta_6m < 0 else "RECOVERY"
    elif regime == "neutral":
        return "EXPANSION"

    return "UNKNOWN"


def build_long_phase(
    macro_policy: pd.DataFrame,
    price_vol: Optional[pd.DataFrame] = None,
    flow: Optional[pd.DataFrame] = None,
    run_id: str = "",
) -> pd.DataFrame:
    """Long phase를 판정한다.

    Parameters
    ----------
    macro_policy : DataFrame
        macro_policy axis features (REQUIRED).
        trade_date별로 regime/delta 집계 후 판정.
    price_vol : DataFrame, optional
        price_volatility axis (OPTIONAL, v0 미사용).
    flow : DataFrame, optional
        flow_structure axis (OPTIONAL, v0 미사용).
    run_id : str
        Lineage run ID.

    Returns
    -------
    DataFrame with LONG_OUTPUT_COLUMNS.
    """
    if macro_policy.empty or "trade_date" not in macro_policy.columns:
        logger.warning("[LongEngine] Empty or invalid macro_policy → all UNKNOWN")
        return pd.DataFrame(columns=LONG_OUTPUT_COLUMNS)

    # trade_date별로 regime 다수결 + delta_6m 평균 집계
    agg = macro_policy.groupby("trade_date").agg(
        regime_mode=("regime", lambda x: x.mode().iloc[0] if not x.mode().empty else None),
        delta_6m_mean=("delta_6m", "mean") if "delta_6m" in macro_policy.columns else ("regime", lambda x: None),
    ).reset_index()

    # delta_6m 컬럼이 없을 수 있음
    if "delta_6m" not in macro_policy.columns:
        agg["delta_6m_mean"] = None

    rows = []
    for _, row in agg.iterrows():
        phase = _classify_long_phase(row.get("regime_mode"), row.get("delta_6m_mean"))
        assert phase in LONG_PHASE_ENUM, f"Invalid phase: {phase}"
        rows.append({
            "trade_date": row["trade_date"],
            "long_phase": phase,
            "long_phase_confidence": None,
            "source_run_id": run_id,
        })

    return pd.DataFrame(rows, columns=LONG_OUTPUT_COLUMNS)
