"""
Mid Regime Engine — 중기 레짐 판정.

REQUIRED axis: price_volatility
OPTIONAL axis: macro_policy, flow_structure, sentiment

Contract: docs/architecture/market_structure_mid_v1_contract.md
SOT: docs/strategy_engine_design.md §A3

v0 라벨 로직 (placeholder — 규칙 기반):
  SPY ret_20d + vol_20d 기반 → RISK_ON / NEUTRAL / RISK_OFF
  결측 시 UNKNOWN (fail-open)
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

from .schema import MID_REGIME_ENUM, MID_OUTPUT_COLUMNS

logger = logging.getLogger(__name__)

# v0 threshold (placeholder, not tunable parameters)
# vol_20d = 일간 수익률 std: median≈0.008, p90≈0.017, max≈0.059
_VOL_HIGH_THRESHOLD = 0.015
_VOL_LOW_THRESHOLD = 0.010


def _classify_mid_regime(
    spy_ret_20d: Optional[float],
    spy_vol_20d: Optional[float],
) -> str:
    """단일 trade_date에 대한 mid regime 판정 (v0 규칙)."""
    if spy_ret_20d is None or pd.isna(spy_ret_20d):
        return "UNKNOWN"
    if spy_vol_20d is None or pd.isna(spy_vol_20d):
        return "UNKNOWN"

    if spy_ret_20d > 0 and spy_vol_20d < _VOL_HIGH_THRESHOLD:
        return "RISK_ON"
    elif spy_ret_20d < 0 and spy_vol_20d > _VOL_HIGH_THRESHOLD:
        return "RISK_OFF"
    else:
        return "NEUTRAL"


def build_mid_regime(
    price_vol: pd.DataFrame,
    macro_policy: Optional[pd.DataFrame] = None,
    flow: Optional[pd.DataFrame] = None,
    sentiment: Optional[pd.DataFrame] = None,
    run_id: str = "",
) -> pd.DataFrame:
    """Mid regime을 판정한다.

    Parameters
    ----------
    price_vol : DataFrame
        price_volatility axis features (REQUIRED).
        SPY 행에서 ret_20d, vol_20d 추출.
    macro_policy, flow, sentiment : DataFrame, optional
        OPTIONAL axes (v0 미사용).
    run_id : str
        Lineage run ID.

    Returns
    -------
    DataFrame with MID_OUTPUT_COLUMNS.
    """
    if price_vol.empty or "trade_date" not in price_vol.columns:
        logger.warning("[MidEngine] Empty or invalid price_vol → all UNKNOWN")
        return pd.DataFrame(columns=MID_OUTPUT_COLUMNS)

    # SPY 데이터 추출
    spy = price_vol[price_vol["symbol"] == "SPY"] if "symbol" in price_vol.columns else pd.DataFrame()

    if spy.empty:
        logger.warning("[MidEngine] No SPY data in price_vol → all UNKNOWN")
        trade_dates = price_vol["trade_date"].unique()
        return pd.DataFrame({
            "trade_date": trade_dates,
            "mid_regime": "UNKNOWN",
            "mid_regime_confidence": None,
            "source_run_id": run_id,
        })[MID_OUTPUT_COLUMNS]

    rows = []
    for _, row in spy.iterrows():
        regime = _classify_mid_regime(
            row.get("ret_20d"),
            row.get("vol_20d"),
        )
        assert regime in MID_REGIME_ENUM, f"Invalid regime: {regime}"
        rows.append({
            "trade_date": row["trade_date"],
            "mid_regime": regime,
            "mid_regime_confidence": None,
            "source_run_id": run_id,
        })

    return pd.DataFrame(rows, columns=MID_OUTPUT_COLUMNS)
