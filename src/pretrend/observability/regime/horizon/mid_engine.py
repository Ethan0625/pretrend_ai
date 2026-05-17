"""
Mid Regime Engine — 중기 레짐 판정.

REQUIRED axis: price_volatility
OPTIONAL axis: macro_policy, flow_structure, sentiment

Contract: docs/architecture/market_structure_mid_v1_contract.md
SOT: docs/architecture/strategy_engine_design.md §A3

v1 라벨 로직:
  3-signal majority vote (price_vol + macro + flow) → RISK_ON / NEUTRAL / RISK_OFF
  - price_signal: SPY ret_20d + vol_20d (v0와 동일)
  - macro_signal: macro_policy.regime 다수결 (easing→RISK_ON, tightening→RISK_OFF)
  - breadth_signal: flow.breadth_iwm_spy_spread (IWM-SPY ret_20d)
      v1.1: ratio(나눗셈) → spread(뺄셈) 교체 — SPY 음수 시 부호 반전 버그 수정
      threshold: >+0.005→RISK_ON, <-0.005→RISK_OFF (실증 std=0.028 기준 0.18σ)
  - optional 축 없으면 price_signal 단독 → v0와 동일 동작 (backward compatible)
  결측 시 UNKNOWN (fail-open)
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Any, Dict, Optional

import pandas as pd

from .schema import MID_REGIME_ENUM, MID_OUTPUT_COLUMNS

logger = logging.getLogger(__name__)

# v0 threshold (placeholder, not tunable parameters)
# vol_20d = 일간 수익률 std: median≈0.008, p90≈0.017, max≈0.059
_VOL_HIGH_THRESHOLD = 0.015
_VOL_LOW_THRESHOLD = 0.010

# v1.1: breadth spread threshold (IWM - SPY ret_20d, 실증 std=0.028)
_BREADTH_SPREAD_HIGH = 0.005   # > +0.5% → 스몰캡 아웃퍼폼 → RISK_ON
_BREADTH_SPREAD_LOW  = -0.005  # < -0.5% → 스몰캡 언더퍼폼 → RISK_OFF

# v1: macro regime → signal mapping
_MACRO_TO_SIGNAL = {
    "easing": "RISK_ON",
    "tightening": "RISK_OFF",
    "neutral": "NEUTRAL",
}


def _majority_vote(signals: list) -> str:
    """유효한(non-UNKNOWN) 신호들에서 다수결.

    동점 시 리스트 순서상 먼저 오는 신호(price_signal) 우선.
    모두 UNKNOWN이면 UNKNOWN 반환.
    """
    valid = [s for s in signals if s != "UNKNOWN"]
    if not valid:
        return "UNKNOWN"
    counts = Counter(valid)
    top_count = counts.most_common(1)[0][1]
    top_signals = {s for s, c in counts.items() if c == top_count}
    # 동점이면 signals 리스트 순서에서 먼저 오는 신호 우선 (price_signal)
    for s in signals:
        if s in top_signals:
            return s
    return list(top_signals)[0]


def _majority_source(signals: list, selected_signal: str) -> str:
    if selected_signal == "UNKNOWN":
        return "unknown"
    labels = ["price", "macro", "breadth"]
    for idx, sig in enumerate(signals):
        if sig == selected_signal and idx < len(labels):
            return labels[idx]
    return "unknown"


def _classify_price_signal(
    spy_ret_20d: Optional[float],
    spy_vol_20d: Optional[float],
) -> str:
    """price_vol 기반 단일 신호 판정 (v0 로직)."""
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


def _classify_mid_regime(
    spy_ret_20d: Optional[float],
    spy_vol_20d: Optional[float],
    macro_regime: Optional[str] = None,
    breadth_spread: Optional[float] = None,
) -> str:
    """단일 trade_date에 대한 mid regime 판정 (v1: 3-signal majority vote).

    Parameters
    ----------
    spy_ret_20d, spy_vol_20d : float
        price_vol 기반 기본 신호 (REQUIRED).
    macro_regime : str, optional
        macro_policy.regime 다수결 값 (easing/tightening/neutral).
    breadth_spread : float, optional
        flow.breadth_iwm_spy_spread (IWM ret_20d - SPY ret_20d) 평균값.
        v1.1: ratio 방식에서 spread 방식으로 교체.
    """
    price_signal = _classify_price_signal(spy_ret_20d, spy_vol_20d)

    # optional 축 없으면 price_signal 단독 (v0 backward compat)
    if macro_regime is None and breadth_spread is None:
        return price_signal

    # macro_signal
    macro_signal = "UNKNOWN"
    if macro_regime is not None:
        try:
            if not pd.isna(macro_regime):
                macro_signal = _MACRO_TO_SIGNAL.get(str(macro_regime).lower(), "UNKNOWN")
        except (TypeError, ValueError):
            pass

    # breadth_signal (v1.1: spread 기반)
    breadth_signal = "UNKNOWN"
    if breadth_spread is not None:
        try:
            if not pd.isna(breadth_spread):
                if breadth_spread > _BREADTH_SPREAD_HIGH:
                    breadth_signal = "RISK_ON"
                elif breadth_spread < _BREADTH_SPREAD_LOW:
                    breadth_signal = "RISK_OFF"
                else:
                    breadth_signal = "NEUTRAL"
        except (TypeError, ValueError):
            pass

    return _majority_vote([price_signal, macro_signal, breadth_signal])


def _compute_mid_decision(
    spy_ret_20d: Optional[float],
    spy_vol_20d: Optional[float],
    macro_regime: Optional[str] = None,
    breadth_spread: Optional[float] = None,
) -> Dict[str, Any]:
    price_signal = _classify_price_signal(spy_ret_20d, spy_vol_20d)

    macro_signal = "UNKNOWN"
    macro_regime_norm: Optional[str] = None
    if macro_regime is not None:
        try:
            if not pd.isna(macro_regime):
                macro_regime_norm = str(macro_regime).lower()
                macro_signal = _MACRO_TO_SIGNAL.get(macro_regime_norm, "UNKNOWN")
        except (TypeError, ValueError):
            pass

    breadth_signal = "UNKNOWN"
    if breadth_spread is not None:
        try:
            if not pd.isna(breadth_spread):
                if breadth_spread > _BREADTH_SPREAD_HIGH:
                    breadth_signal = "RISK_ON"
                elif breadth_spread < _BREADTH_SPREAD_LOW:
                    breadth_signal = "RISK_OFF"
                else:
                    breadth_signal = "NEUTRAL"
        except (TypeError, ValueError):
            pass

    signals = [price_signal, macro_signal, breadth_signal]
    selected = _majority_vote(signals)
    return {
        "selected_signal": selected,
        "price_signal": price_signal,
        "macro_signal": macro_signal,
        "breadth_signal": breadth_signal,
        "macro_regime": macro_regime_norm,
        "breadth_spread": None if breadth_spread is None or pd.isna(breadth_spread) else float(breadth_spread),
        "majority_source": _majority_source(signals, selected),
    }


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
    macro_policy : DataFrame, optional
        macro_policy axis — regime 다수결로 macro_signal 생성.
    flow : DataFrame, optional
        flow_structure axis — breadth_iwm_spy_spread 평균으로 breadth_signal 생성.
    sentiment : DataFrame, optional
        sentiment axis (v1 미사용).
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
            "mid_detail_json": None,
            "source_run_id": run_id,
        })[MID_OUTPUT_COLUMNS]

    # v1: macro_policy → trade_date별 regime 다수결
    macro_regime_by_date: dict = {}
    if macro_policy is not None and not macro_policy.empty and "regime" in macro_policy.columns:
        if "trade_date" in macro_policy.columns:
            for td, grp in macro_policy.groupby("trade_date"):
                mode_vals = grp["regime"].dropna().mode()
                if not mode_vals.empty:
                    macro_regime_by_date[td] = mode_vals.iloc[0]

    # v1.1: flow → trade_date별 breadth_iwm_spy_spread 평균 (ratio → spread)
    breadth_by_date: dict = {}
    if flow is not None and not flow.empty and "breadth_iwm_spy_spread" in flow.columns:
        if "trade_date" in flow.columns:
            flow_agg = (
                flow.groupby("trade_date")["breadth_iwm_spy_spread"]
                .mean()
                .dropna()
            )
            breadth_by_date = flow_agg.to_dict()

    rows = []
    for _, row in spy.iterrows():
        td = row["trade_date"]
        macro_regime = macro_regime_by_date.get(td)
        breadth_spread = breadth_by_date.get(td)

        decision = _compute_mid_decision(
            row.get("ret_20d"),
            row.get("vol_20d"),
            macro_regime=macro_regime,
            breadth_spread=breadth_spread,
        )
        regime = decision["selected_signal"]
        assert regime in MID_REGIME_ENUM, f"Invalid regime: {regime}"
        rows.append({
            "trade_date": td,
            "mid_regime": regime,
            "mid_regime_confidence": None,
            "mid_detail_json": json.dumps(decision, sort_keys=True),
            "source_run_id": run_id,
        })

    return pd.DataFrame(rows, columns=MID_OUTPUT_COLUMNS)
