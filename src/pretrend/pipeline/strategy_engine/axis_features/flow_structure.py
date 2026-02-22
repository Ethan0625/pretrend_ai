"""
Axis Feature: flow_structure — Gold EOD에서 수급/구조 축 추출 + 파생.

Contract: docs/architecture/axis_horizon_dependency_v1_contract.md §3.2
v0: 부분 수집 상태 허용, 누락 시 UNKNOWN 허용.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

from .schema import FLOW_COLUMNS

logger = logging.getLogger(__name__)

# turnover spike 임계값 (volume_zscore_20d 기준)
_TURNOVER_SPIKE_THRESHOLD = 2.0

# OBV slope 계산 윈도우
_OBV_SLOPE_WINDOW = 20


def build_flow_structure_axis(df_gold_eod: pd.DataFrame) -> pd.DataFrame:
    """Gold EOD → flow_structure axis feature.

    기존 컬럼 선택 + 신규 파생:
    - obv_slope: OBV(On-Balance Volume) 20일 기울기
    - turnover_spike_flag: volume_zscore_20d > threshold
    - breadth_iwm_spy_ratio: IWM ret_20d / SPY ret_20d

    빈 입력이면 빈 DataFrame 반환.
    """
    if df_gold_eod.empty:
        return pd.DataFrame(columns=FLOW_COLUMNS)

    df = df_gold_eod.copy()

    # turnover_spike_flag
    if "volume_zscore_20d" in df.columns:
        df["turnover_spike_flag"] = (
            df["volume_zscore_20d"] > _TURNOVER_SPIKE_THRESHOLD
        )
    else:
        df["turnover_spike_flag"] = None

    # obv_slope: symbol별 OBV 누적 → 20일 기울기
    df["obv_slope"] = _compute_obv_slope(df)

    # breadth_iwm_spy_spread: cross-symbol 파생 (IWM - SPY ret_20d)
    df["breadth_iwm_spy_spread"] = _compute_breadth_spread(df)

    for col in FLOW_COLUMNS:
        if col not in df.columns:
            df[col] = None

    return df[FLOW_COLUMNS].copy().reset_index(drop=True)


def _compute_obv_slope(df: pd.DataFrame) -> pd.Series:
    """OBV 20일 기울기 계산.

    OBV = cumsum(volume * sign(ret_1d))
    slope = (OBV[-1] - OBV[-window]) / window
    """
    if "volume" not in df.columns or "ret_1d" not in df.columns:
        return pd.Series(None, index=df.index, dtype="float64")

    results = pd.Series(np.nan, index=df.index, dtype="float64")

    for symbol, grp in df.groupby("symbol"):
        grp = grp.sort_values("trade_date")
        sign = np.sign(grp["ret_1d"].fillna(0))
        obv = (grp["volume"].fillna(0) * sign).cumsum()

        slope = (obv - obv.shift(_OBV_SLOPE_WINDOW)) / _OBV_SLOPE_WINDOW
        results.loc[grp.index] = slope.values

    return results


def _compute_breadth_spread(df: pd.DataFrame) -> pd.Series:
    """IWM ret_20d - SPY ret_20d spread (breadth proxy).

    ratio(나눗셈) 방식은 SPY가 음수일 때 부호 반전 발생:
      SPY=-5%, IWM=-3% → ratio=0.6 → 잘못된 RISK_OFF
    spread(뺄셈) 방식은 방향 무관하게 상대 성과를 정확히 측정:
      SPY=-5%, IWM=-3% → spread=+2% → 올바른 RISK_ON
    SPY=0인 경우도 spread=IWM (나눗셈 불필요, None 처리 불필요)

    trade_date별로 IWM ret_20d - SPY ret_20d를 계산하여
    전체 행에 브로드캐스트한다.
    """
    if "ret_20d" not in df.columns or "symbol" not in df.columns:
        return pd.Series(None, index=df.index, dtype="float64")

    iwm = df.loc[df["symbol"] == "IWM", ["trade_date", "ret_20d"]].rename(
        columns={"ret_20d": "iwm_ret_20d"}
    )
    spy = df.loc[df["symbol"] == "SPY", ["trade_date", "ret_20d"]].rename(
        columns={"ret_20d": "spy_ret_20d"}
    )

    if iwm.empty or spy.empty:
        return pd.Series(None, index=df.index, dtype="float64")

    ratio_df = iwm.merge(spy, on="trade_date", how="inner")
    ratio_df["spread"] = ratio_df["iwm_ret_20d"] - ratio_df["spy_ret_20d"]

    merged = df[["trade_date"]].merge(
        ratio_df[["trade_date", "spread"]], on="trade_date", how="left"
    )
    return merged["spread"].astype("float64")
