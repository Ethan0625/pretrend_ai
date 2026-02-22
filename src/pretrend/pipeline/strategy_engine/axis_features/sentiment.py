"""
Axis Feature: sentiment — Gold EOD에서 심리 proxy 축 추출.

Contract: docs/architecture/axis_horizon_dependency_contract.md §3.2
v0: Risk Spread(SPY/TLT/IAU) + Volatility Proxy(SPY vol, IWM/SPY vol, intraday_range)
VIX는 v0에서 필수 입력이 아님.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .schema import SENTIMENT_COLUMNS

logger = logging.getLogger(__name__)


def build_sentiment_proxy_axis(df_gold_eod: pd.DataFrame) -> pd.DataFrame:
    """Gold EOD → sentiment proxy axis feature (v0).

    Cross-symbol 파생:
    - spy_ret_1d, tlt_ret_1d, iau_ret_1d: 개별 심볼 1일 수익률
    - spy_vol_20d, spy_intraday_range: SPY 변동성 proxy
    - iwm_spy_relative_strength: IWM ret_20d / SPY ret_20d
    - iwm_spy_vol_spread: IWM vol_20d - SPY vol_20d

    출력 grain: trade_date (심볼 차원 제거 — cross-symbol 집계)
    빈 입력이면 빈 DataFrame 반환.
    """
    if df_gold_eod.empty:
        return pd.DataFrame(columns=SENTIMENT_COLUMNS)

    df = df_gold_eod.copy()
    if "trade_date" in df.columns:
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date

    trade_dates = sorted(df["trade_date"].dropna().unique())
    if not trade_dates:
        return pd.DataFrame(columns=SENTIMENT_COLUMNS)

    # 심볼별 피벗
    pivots = {}
    for sym in ("SPY", "TLT", "IAU", "IWM"):
        sub = df.loc[df["symbol"] == sym, ["trade_date", "ret_1d", "ret_20d", "vol_20d", "intraday_range"]]
        if not sub.empty:
            pivots[sym] = sub.set_index("trade_date")

    rows = []
    for td in trade_dates:
        row = {"trade_date": td}

        # Risk Spread proxy: SPY/TLT/IAU 1일 수익률
        for sym, col_name in [("SPY", "spy_ret_1d"), ("TLT", "tlt_ret_1d"), ("IAU", "iau_ret_1d")]:
            row[col_name] = _get_val(pivots, sym, td, "ret_1d")

        # Volatility proxy
        row["spy_vol_20d"] = _get_val(pivots, "SPY", td, "vol_20d")
        row["spy_intraday_range"] = _get_val(pivots, "SPY", td, "intraday_range")

        # IWM/SPY relative strength
        iwm_ret = _get_val(pivots, "IWM", td, "ret_20d")
        spy_ret = _get_val(pivots, "SPY", td, "ret_20d")
        if iwm_ret is not None and spy_ret is not None and abs(spy_ret) > 1e-10:
            row["iwm_spy_relative_strength"] = iwm_ret / spy_ret
        else:
            row["iwm_spy_relative_strength"] = None

        # IWM/SPY vol spread
        iwm_vol = _get_val(pivots, "IWM", td, "vol_20d")
        spy_vol = _get_val(pivots, "SPY", td, "vol_20d")
        if iwm_vol is not None and spy_vol is not None:
            row["iwm_spy_vol_spread"] = iwm_vol - spy_vol
        else:
            row["iwm_spy_vol_spread"] = None

        rows.append(row)

    result = pd.DataFrame(rows)

    for col in SENTIMENT_COLUMNS:
        if col not in result.columns:
            result[col] = None

    return result[SENTIMENT_COLUMNS].reset_index(drop=True)


def _get_val(pivots: dict, sym: str, td, col: str):
    """피벗 딕셔너리에서 특정 심볼/날짜/컬럼 값을 안전하게 추출."""
    if sym not in pivots:
        return None
    p = pivots[sym]
    if td not in p.index:
        return None
    val = p.loc[td, col]
    if isinstance(val, pd.Series):
        val = val.iloc[0]
    if pd.isna(val):
        return None
    return float(val)
