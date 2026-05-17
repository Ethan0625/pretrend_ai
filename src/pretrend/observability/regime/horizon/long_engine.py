"""
Long Phase Engine — 장기 사이클 위치 판정.

REQUIRED axis: macro_policy
OPTIONAL axis: price_volatility, flow_structure

Contract: docs/architecture/market_structure_long_v1_contract.md
SOT: docs/architecture/strategy_engine_design.md §A3

v1 라벨 로직:
  regime 다수결 + delta_6m 지표별 rolling z-score 평균 → phase 매핑
  - delta_6m을 지표별 rolling z-score로 정규화 (단위 불변, window=252, min_periods=60)
  - 초기구간(z-score NaN) 시 raw delta_6m 부호(sign)로 fallback
  - indicator_id 또는 delta_6m 컬럼 없으면 regime 단독 판정 (fail-open)
  결측 시 UNKNOWN (fail-open)

전제:
  - macro_policy의 (indicator_id, trade_date) 중복은 keep="last"로 제거
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import numpy as np
import pandas as pd

from .schema import LONG_PHASE_ENUM, LONG_OUTPUT_COLUMNS

logger = logging.getLogger(__name__)


def _safe_float(val: Optional[float]) -> Optional[float]:
    if val is None or pd.isna(val):
        return None
    return float(val)


def _classify_long_phase(
    regime: Optional[str],
    delta_6m: Optional[float],
    threshold: float = 0.0,
) -> str:
    """단일 trade_date에 대한 long phase 판정.

    Parameters
    ----------
    regime : str
        tightening / easing / neutral
    delta_6m : float
        z-score 정규화된 delta_6m (v1) 또는 raw delta_6m (v0/fallback)
    threshold : float
        SLOWDOWN/RECESSION 분류 임계값 (default=0.0).
        delta_6m_z < -threshold 일 때만 SLOWDOWN/RECESSION으로 분류.
        0.0이면 부호만으로 판정 (v0 동작), 양수이면 "확실히 음수"일 때만 분류.
    """
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

    # regime + delta_6m 조합 판정 (threshold 적용)
    if regime == "tightening":
        return "SLOWDOWN" if delta_6m < -threshold else "LATE_CYCLE"
    elif regime == "easing":
        return "RECESSION" if delta_6m < -threshold else "RECOVERY"
    elif regime == "neutral":
        return "EXPANSION"

    return "UNKNOWN"


def build_long_phase(
    macro_policy: pd.DataFrame,
    price_vol: Optional[pd.DataFrame] = None,
    flow: Optional[pd.DataFrame] = None,
    run_id: str = "",
    z_threshold: float = 0.0,
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

    # v1: 지표별 rolling z-score로 delta_6m 정규화 (단위 불변)
    # 전제: (indicator_id, trade_date) 중복은 keep="last"로 제거
    mac = macro_policy.copy()
    if "delta_6m" in mac.columns and "indicator_id" in mac.columns:
        # 중복 제거: (indicator_id, trade_date) 기준, keep="last"
        mac = mac.drop_duplicates(subset=["indicator_id", "trade_date"], keep="last")
        mac = mac.sort_values(["indicator_id", "trade_date"])
        mac["delta_6m"] = pd.to_numeric(mac["delta_6m"], errors="coerce")

        # 지표별 rolling z-score (window=252거래일, min_periods=60)
        def _rolling_zscore(x: pd.Series) -> pd.Series:
            mean = x.rolling(252, min_periods=60).mean()
            std = x.rolling(252, min_periods=60).std()
            std = std.where(std > 0, other=float("nan"))
            return (x - mean) / std

        mac["delta_6m_z"] = mac.groupby("indicator_id", sort=False)["delta_6m"].transform(
            _rolling_zscore
        )

        # NaN fallback: z-score 미계산 시 raw delta_6m 부호(sign)로 대체
        # 초기구간(min_periods 미충족) 또는 std=0 케이스
        nan_mask = mac["delta_6m_z"].isna()
        raw_sign = np.sign(mac.loc[nan_mask, "delta_6m"]).replace(0, float("nan"))
        mac.loc[nan_mask, "delta_6m_z"] = raw_sign
    else:
        # delta_6m 또는 indicator_id 컬럼 없음 → regime 단독 판정 (fail-open)
        logger.debug("[LongEngine] delta_6m or indicator_id missing → regime-only classification")
        mac["delta_6m_z"] = float("nan")

    # trade_date별로 regime 다수결 + z-score 평균 집계
    rows = []
    for td, grp in mac.groupby("trade_date", sort=True):
        regime_vals = grp["regime"].dropna() if "regime" in grp.columns else pd.Series(dtype=object)
        regime_mode = regime_vals.mode().iloc[0] if not regime_vals.mode().empty else None
        delta_6m_z_mean = grp["delta_6m_z"].mean() if "delta_6m_z" in grp.columns else None
        phase = _classify_long_phase(regime_mode, delta_6m_z_mean, threshold=z_threshold)
        assert phase in LONG_PHASE_ENUM, f"Invalid phase: {phase}"

        regime_votes = (
            regime_vals.astype(str).str.lower().value_counts().to_dict()
            if not regime_vals.empty else {}
        )
        detail = {
            "regime_mode": None if regime_mode is None or pd.isna(regime_mode) else str(regime_mode).lower(),
            "regime_votes": regime_votes,
            "delta_6m_z_mean": _safe_float(delta_6m_z_mean),
            "z_threshold": float(z_threshold),
            "used_regime_only": delta_6m_z_mean is None or pd.isna(delta_6m_z_mean),
        }
        rows.append({
            "trade_date": td,
            "long_phase": phase,
            "long_phase_confidence": None,
            "long_detail_json": json.dumps(detail, sort_keys=True),
            "source_run_id": run_id,
        })

    return pd.DataFrame(rows, columns=LONG_OUTPUT_COLUMNS)
