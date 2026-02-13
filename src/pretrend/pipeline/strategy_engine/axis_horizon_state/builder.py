"""
Axis × Horizon State builder — 12-slot 통합 빌더.

4 axes × 3 horizons = 12 slots를 단일 DataFrame으로 결합.
Grain: (trade_date) — 1 row per business day.

SOT: docs/strategy_engine_design.md §A3, §E
Storage: data/strategy/axis_horizon_state/decision_date=YYYY-MM-DD/state_YYYYMMDD.parquet
"""
from __future__ import annotations

import logging

import pandas as pd

from ..axis_features.schema import AxisFeatureBundle
from .long_engine import build_long_phase
from .mid_engine import build_mid_regime
from .short_engine import build_short_signal
from .schema import AXIS_HORIZON_STATE_COLUMNS

logger = logging.getLogger(__name__)


def build_axis_horizon_state(
    bundle: AxisFeatureBundle,
    run_id: str = "",
) -> pd.DataFrame:
    """12-slot Axis×Horizon State를 구축한다.

    Parameters
    ----------
    bundle : AxisFeatureBundle
        4개 axis feature DataFrame 묶음.
    run_id : str
        Lineage run ID.

    Returns
    -------
    DataFrame with AXIS_HORIZON_STATE_COLUMNS.
    Grain: (trade_date).
    """
    # 1) 각 horizon engine 실행
    df_long = build_long_phase(
        macro_policy=bundle.macro_policy,
        price_vol=bundle.price_volatility,
        flow=bundle.flow_structure,
        run_id=run_id,
    )

    df_mid = build_mid_regime(
        price_vol=bundle.price_volatility,
        macro_policy=bundle.macro_policy,
        flow=bundle.flow_structure,
        sentiment=bundle.sentiment,
        run_id=run_id,
    )

    df_short = build_short_signal(
        price_vol=bundle.price_volatility,
        flow=bundle.flow_structure,
        sentiment=bundle.sentiment,
        run_id=run_id,
    )

    # 2) trade_date 기준 merge
    if df_long.empty and df_mid.empty and df_short.empty:
        logger.warning("[AHS Builder] All horizons empty")
        return pd.DataFrame(columns=AXIS_HORIZON_STATE_COLUMNS)

    # Left join 체인: long → mid → short
    result = df_long.copy() if not df_long.empty else pd.DataFrame(columns=["trade_date"])

    if not df_mid.empty:
        mid_cols = ["trade_date", "mid_regime", "mid_regime_confidence"]
        result = result.merge(df_mid[mid_cols], on="trade_date", how="outer")
    else:
        result["mid_regime"] = "UNKNOWN"
        result["mid_regime_confidence"] = None

    if not df_short.empty:
        short_cols = ["trade_date", "short_signal", "short_signal_confidence"]
        result = result.merge(df_short[short_cols], on="trade_date", how="outer")
    else:
        result["short_signal"] = "UNKNOWN"
        result["short_signal_confidence"] = None

    # 3) 결측 상태 → UNKNOWN 채움 (fail-open)
    for col in ("long_phase", "mid_regime", "short_signal"):
        if col in result.columns:
            result[col] = result[col].fillna("UNKNOWN")
        else:
            result[col] = "UNKNOWN"

    for col in ("long_phase_confidence", "mid_regime_confidence", "short_signal_confidence"):
        if col not in result.columns:
            result[col] = None

    if "source_run_id" not in result.columns:
        result["source_run_id"] = run_id
    result["source_run_id"] = result["source_run_id"].fillna(run_id)

    # 4) 컬럼 정렬 및 반환
    for col in AXIS_HORIZON_STATE_COLUMNS:
        if col not in result.columns:
            result[col] = None

    result = result[AXIS_HORIZON_STATE_COLUMNS].sort_values("trade_date").reset_index(drop=True)

    logger.info("[AHS Builder] Built %d rows × 12 slots", len(result))
    return result
