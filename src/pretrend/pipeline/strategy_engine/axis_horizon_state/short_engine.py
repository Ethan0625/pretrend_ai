"""
Short Signal Engine — 단기 흐름/심리 판정.

REQUIRED axis: price_volatility, flow_structure, sentiment
OPTIONAL axis: (없음)

Contract: docs/architecture/market_structure_short_v1_contract.md
SOT: docs/strategy_engine_design.md §A3

v0 라벨 로직 (placeholder — 규칙 기반):
  risk spread proxy + vol proxy + flow confirmation → PANIC / STABLE / RELIEF
  결측 시 UNKNOWN (fail-open)
  VIX 입력 없이 동작 (v0 제약)
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

from .schema import SHORT_SIGNAL_ENUM, SHORT_OUTPUT_COLUMNS

logger = logging.getLogger(__name__)


def _classify_short_signal(
    spy_ret_1d: Optional[float],
    spy_vol_20d: Optional[float],
    volume_zscore: Optional[float],
    spy_intraday_range: Optional[float],
) -> str:
    """단일 trade_date에 대한 short signal 판정 (v0 규칙)."""
    if spy_ret_1d is None or pd.isna(spy_ret_1d):
        return "UNKNOWN"
    if spy_vol_20d is None or pd.isna(spy_vol_20d):
        return "UNKNOWN"

    # PANIC: 급락 + 높은 변동성
    # vol_20d = 일간 수익률 std: p90≈0.017, p95≈0.019
    if spy_ret_1d < -0.01 and spy_vol_20d > 0.018:
        return "PANIC"

    # RELIEF: 반등 + 낮은 변동성
    if spy_ret_1d > 0.005 and spy_vol_20d < 0.012:
        return "RELIEF"

    return "STABLE"


def build_short_signal(
    price_vol: pd.DataFrame,
    flow: pd.DataFrame,
    sentiment: pd.DataFrame,
    run_id: str = "",
) -> pd.DataFrame:
    """Short signal을 판정한다.

    Parameters
    ----------
    price_vol : DataFrame
        price_volatility axis (REQUIRED).
    flow : DataFrame
        flow_structure axis (REQUIRED).
    sentiment : DataFrame
        sentiment axis (REQUIRED).
    run_id : str
        Lineage run ID.

    Returns
    -------
    DataFrame with SHORT_OUTPUT_COLUMNS.
    """
    # 어느 하나라도 비어 있으면 UNKNOWN
    all_empty = price_vol.empty or flow.empty or sentiment.empty
    has_trade_date = (
        "trade_date" in price_vol.columns
        and "trade_date" in flow.columns
        and "trade_date" in sentiment.columns
    )

    if all_empty or not has_trade_date:
        logger.warning("[ShortEngine] Missing required axis → all UNKNOWN")
        # 가용 trade_date 수집
        trade_dates = set()
        for df in (price_vol, flow, sentiment):
            if not df.empty and "trade_date" in df.columns:
                trade_dates.update(df["trade_date"].unique())
        if not trade_dates:
            return pd.DataFrame(columns=SHORT_OUTPUT_COLUMNS)
        return pd.DataFrame({
            "trade_date": sorted(trade_dates),
            "short_signal": "UNKNOWN",
            "short_signal_confidence": None,
            "source_run_id": run_id,
        })[SHORT_OUTPUT_COLUMNS]

    # SPY 데이터 추출 (price_vol에서)
    spy_pv = price_vol[price_vol["symbol"] == "SPY"] if "symbol" in price_vol.columns else pd.DataFrame()

    # sentiment는 trade_date grain (symbol 없음)
    # flow에서 평균 volume_zscore 추출
    flow_agg = pd.DataFrame()
    if not flow.empty and "volume_zscore_20d" in flow.columns:
        flow_agg = flow.groupby("trade_date").agg(
            avg_vol_zscore=("volume_zscore_20d", "mean"),
        ).reset_index()

    # 전체 trade_date 집합
    all_dates = set()
    for df in (price_vol, flow, sentiment):
        if "trade_date" in df.columns:
            all_dates.update(df["trade_date"].unique())

    rows = []
    for td in sorted(all_dates):
        # SPY price_vol
        spy_row = spy_pv[spy_pv["trade_date"] == td] if not spy_pv.empty else pd.DataFrame()
        spy_ret_1d = spy_row.iloc[0].get("ret_1d") if not spy_row.empty else None
        spy_vol_20d = spy_row.iloc[0].get("vol_20d") if not spy_row.empty else None
        spy_intraday = spy_row.iloc[0].get("intraday_range") if not spy_row.empty else None

        # flow volume zscore
        flow_row = flow_agg[flow_agg["trade_date"] == td] if not flow_agg.empty else pd.DataFrame()
        vol_zscore = flow_row.iloc[0].get("avg_vol_zscore") if not flow_row.empty else None

        signal = _classify_short_signal(spy_ret_1d, spy_vol_20d, vol_zscore, spy_intraday)
        assert signal in SHORT_SIGNAL_ENUM, f"Invalid signal: {signal}"

        rows.append({
            "trade_date": td,
            "short_signal": signal,
            "short_signal_confidence": None,
            "source_run_id": run_id,
        })

    return pd.DataFrame(rows, columns=SHORT_OUTPUT_COLUMNS)
