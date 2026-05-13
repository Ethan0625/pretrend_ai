"""
Short Signal Engine — 단기 흐름/심리 판정.

REQUIRED axis: price_volatility, flow_structure, sentiment
OPTIONAL axis: (없음)

Contract: docs/architecture/market_structure_short_v1_contract.md
SOT: docs/strategy_engine_design.md §A3

v1.3 라벨 로직:
  Primary: SPY ret_1d + vol_20d → PANIC / RELIEF / STABLE (v0 조건 유지)
  Secondary PANIC: 약한 원신호 + 보조 신호 3개 이상 (6신호 중 3개)
    - vol_spike      : volume_zscore_20d > 2.0
    - wide_intraday  : spy_intraday_range > 0.020
    - flight_to_safety: tlt_ret_1d > 0.003 AND iau_ret_1d > 0.003
    - smallcap_stress: iwm_spy_vol_spread > 0.005 (IWM vol > SPY vol +0.5%p)  ← v1.1 신규
    - vix_extreme    : vix_close > 35.0  ← v1.2 신규
    - skew_extreme   : skew_extreme_flag == 1  ← v1.3 신규
  Secondary RELIEF: 약한 원신호 + risk_on_confirm
    - risk_on_confirm: tlt_ret_1d < -0.002 AND iau_ret_1d < -0.002
  결측 시 UNKNOWN (fail-open)
  VIX/SKEW 입력 없이도 동작 (vix_close=None → vix_extreme=False, skew load 실패 → 0)
"""
from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from .schema import SHORT_SIGNAL_ENUM, SHORT_OUTPUT_COLUMNS

logger = logging.getLogger(__name__)

# v0 임계값 (primary 조건 — 변경 금지)
_PANIC_RET = -0.01
_PANIC_VOL = 0.018
_RELIEF_RET = 0.005
_RELIEF_VOL = 0.012

# v1 임계값 (secondary 조건)
_SECONDARY_PANIC_RET = -0.005
_SECONDARY_PANIC_VOL = 0.015
_VOL_SPIKE_THRESHOLD = 2.0
_INTRADAY_WIDE_THRESHOLD = 0.020
_FLIGHT_RET_THRESHOLD = 0.003
_SECONDARY_RELIEF_RET = 0.003
_SECONDARY_RELIEF_VOL = 0.015
_RISK_ON_CONFIRM_THRESHOLD = -0.002

# v1.1 임계값 (smallcap_stress)
_IWM_SPY_VOL_SPREAD_THRESHOLD = 0.005  # IWM vol_20d - SPY vol_20d > 0.5%p → 소형주 스트레스

# v1.2 임계값 (vix_extreme)
_VIX_EXTREME_THRESHOLD = 35.0
# SKEW_GOLD_ROOT: config 주입 없을 때 env var 기반 기본값 (하드코딩 제거)
_DEFAULT_SKEW_GOLD_ROOT: str = str(
    Path(os.getenv("PRETREND_DATA_ROOT", "data")) / "gold" / "macro" / "skew" / "put_call"
)


@lru_cache(maxsize=8192)
def _load_skew_extreme(signal_date, skew_root: str = "") -> int:
    """skew_extreme_flag Gold feature 로드. 실패 시 0 반환 (fail-open).

    Parameters
    ----------
    signal_date : date-like
        신호 판정 날짜.
    skew_root : str, optional
        SKEW Gold 데이터 루트 경로 문자열. 빈 문자열이면 환경변수 기반 기본값 사용.
    """
    try:
        root = Path(skew_root) if skew_root else Path(_DEFAULT_SKEW_GOLD_ROOT)
        date_token = pd.Timestamp(signal_date).date().isoformat()
        skew_dir = root / f"date={date_token}"
        files = sorted(skew_dir.glob("*.parquet"))
        if not files:
            return 0
        df = pd.read_parquet(files[0], columns=["skew_extreme_flag"])
        if df.empty:
            return 0
        value = df["skew_extreme_flag"].iloc[0]
        if pd.isna(value):
            return 0
        return int(value)
    except Exception:
        return 0


def _is_valid(val: Optional[float]) -> bool:
    """값이 None이 아니고 NaN도 아닌지 확인."""
    if val is None:
        return False
    try:
        return not pd.isna(val)
    except (TypeError, ValueError):
        return False


def _classify_short_signal(
    spy_ret_1d: Optional[float],
    spy_vol_20d: Optional[float],
    volume_zscore: Optional[float] = None,
    spy_intraday_range: Optional[float] = None,
    tlt_ret_1d: Optional[float] = None,
    iau_ret_1d: Optional[float] = None,
    iwm_spy_vol_spread: Optional[float] = None,
    vix_close: Optional[float] = None,
    skew_extreme: Optional[bool] = None,
) -> str:
    """단일 trade_date에 대한 short signal 판정 (v1.3 규칙).

    Parameters
    ----------
    spy_ret_1d, spy_vol_20d : float
        Primary 판정 기준 (REQUIRED).
    volume_zscore : float, optional
        flow.volume_zscore_20d 평균 — vol_spike 보조 신호.
    spy_intraday_range : float, optional
        price_vol.intraday_range — wide_intraday 보조 신호.
    tlt_ret_1d, iau_ret_1d : float, optional
        sentiment — flight_to_safety / risk_on_confirm 보조 신호.
    iwm_spy_vol_spread : float, optional
        sentiment.iwm_spy_vol_spread (IWM vol_20d - SPY vol_20d) — smallcap_stress 보조 신호.
    vix_close : float, optional
        ^VIX close — vix_extreme 보조 신호.
    skew_extreme : bool, optional
        skew_extreme_flag — skew tail-risk 보조 신호.
    """
    if spy_ret_1d is None or pd.isna(spy_ret_1d):
        return "UNKNOWN"
    if spy_vol_20d is None or pd.isna(spy_vol_20d):
        return "UNKNOWN"

    # ── 보조 신호 계산 ────────────────────────────────────
    vol_spike = _is_valid(volume_zscore) and volume_zscore > _VOL_SPIKE_THRESHOLD
    wide_intraday = _is_valid(spy_intraday_range) and spy_intraday_range > _INTRADAY_WIDE_THRESHOLD
    flight_to_safety = (
        _is_valid(tlt_ret_1d) and tlt_ret_1d > _FLIGHT_RET_THRESHOLD
        and _is_valid(iau_ret_1d) and iau_ret_1d > _FLIGHT_RET_THRESHOLD
    )
    risk_on_confirm = (
        _is_valid(tlt_ret_1d) and tlt_ret_1d < _RISK_ON_CONFIRM_THRESHOLD
        and _is_valid(iau_ret_1d) and iau_ret_1d < _RISK_ON_CONFIRM_THRESHOLD
    )
    # v1.1: 소형주 변동성 스트레스 (4번째 보조 신호)
    smallcap_stress = (
        _is_valid(iwm_spy_vol_spread)
        and iwm_spy_vol_spread > _IWM_SPY_VOL_SPREAD_THRESHOLD
    )
    vix_extreme = _is_valid(vix_close) and vix_close > _VIX_EXTREME_THRESHOLD

    # ── Primary PANIC (v0 조건 — 유지) ────────────────────
    if spy_ret_1d < _PANIC_RET and spy_vol_20d > _PANIC_VOL:
        return "PANIC"

    # ── Secondary PANIC: 약한 원신호 + 6신호 중 3개 이상 ──
    if spy_ret_1d < _SECONDARY_PANIC_RET and spy_vol_20d > _SECONDARY_PANIC_VOL:
        confirmations = (
            int(vol_spike) + int(wide_intraday)
            + int(flight_to_safety) + int(smallcap_stress) + int(vix_extreme)
            + int(bool(skew_extreme))
        )
        if confirmations >= 3:
            return "PANIC"

    # ── Primary RELIEF (v0 조건 — 유지) ───────────────────
    if spy_ret_1d > _RELIEF_RET and spy_vol_20d < _RELIEF_VOL:
        return "RELIEF"

    # ── Secondary RELIEF: 약한 원신호 + risk_on_confirm ───
    if spy_ret_1d > _SECONDARY_RELIEF_RET and spy_vol_20d < _SECONDARY_RELIEF_VOL and risk_on_confirm:
        return "RELIEF"

    return "STABLE"


def _evaluate_short_signal(
    spy_ret_1d: Optional[float],
    spy_vol_20d: Optional[float],
    volume_zscore: Optional[float] = None,
    spy_intraday_range: Optional[float] = None,
    tlt_ret_1d: Optional[float] = None,
    iau_ret_1d: Optional[float] = None,
    iwm_spy_vol_spread: Optional[float] = None,
    vix_close: Optional[float] = None,
    skew_extreme: Optional[bool] = None,
) -> Tuple[str, Dict[str, Any]]:
    if spy_ret_1d is None or pd.isna(spy_ret_1d) or spy_vol_20d is None or pd.isna(spy_vol_20d):
        detail = {
            "primary_panic": False,
            "primary_relief": False,
            "secondary_panic_candidate": False,
            "secondary_relief_candidate": False,
            "secondary_confirm_count": 0,
            "secondary_confirmations": [],
            "risk_on_confirm": False,
            "smallcap_stress": False,
            "vix_extreme": False,
            "skew_extreme": False,
            "vix_close": vix_close,
            "used_unknown_fallback": True,
        }
        return "UNKNOWN", detail

    vol_spike = _is_valid(volume_zscore) and volume_zscore > _VOL_SPIKE_THRESHOLD
    wide_intraday = _is_valid(spy_intraday_range) and spy_intraday_range > _INTRADAY_WIDE_THRESHOLD
    flight_to_safety = (
        _is_valid(tlt_ret_1d) and tlt_ret_1d > _FLIGHT_RET_THRESHOLD
        and _is_valid(iau_ret_1d) and iau_ret_1d > _FLIGHT_RET_THRESHOLD
    )
    risk_on_confirm = (
        _is_valid(tlt_ret_1d) and tlt_ret_1d < _RISK_ON_CONFIRM_THRESHOLD
        and _is_valid(iau_ret_1d) and iau_ret_1d < _RISK_ON_CONFIRM_THRESHOLD
    )
    smallcap_stress = (
        _is_valid(iwm_spy_vol_spread)
        and iwm_spy_vol_spread > _IWM_SPY_VOL_SPREAD_THRESHOLD
    )
    vix_extreme = _is_valid(vix_close) and vix_close > _VIX_EXTREME_THRESHOLD
    confirmation_flags = {
        "vol_spike": bool(vol_spike),
        "wide_intraday": bool(wide_intraday),
        "flight_to_safety": bool(flight_to_safety),
        "smallcap_stress": bool(smallcap_stress),
        "vix_extreme": bool(vix_extreme),
        "skew_extreme": bool(skew_extreme),
    }
    confirmations = [k for k, v in confirmation_flags.items() if v]
    confirm_count = len(confirmations)

    primary_panic = spy_ret_1d < _PANIC_RET and spy_vol_20d > _PANIC_VOL
    secondary_panic_candidate = (
        spy_ret_1d < _SECONDARY_PANIC_RET and spy_vol_20d > _SECONDARY_PANIC_VOL
    )
    primary_relief = spy_ret_1d > _RELIEF_RET and spy_vol_20d < _RELIEF_VOL
    secondary_relief_candidate = (
        spy_ret_1d > _SECONDARY_RELIEF_RET and spy_vol_20d < _SECONDARY_RELIEF_VOL
    )

    signal = "STABLE"
    if primary_panic:
        signal = "PANIC"
    elif secondary_panic_candidate and confirm_count >= 3:
        signal = "PANIC"
    elif primary_relief:
        signal = "RELIEF"
    elif secondary_relief_candidate and risk_on_confirm:
        signal = "RELIEF"

    detail = {
        "spy_ret_1d": float(spy_ret_1d),
        "spy_vol_20d": float(spy_vol_20d),
        "primary_panic": bool(primary_panic),
        "primary_relief": bool(primary_relief),
        "secondary_panic_candidate": bool(secondary_panic_candidate),
        "secondary_relief_candidate": bool(secondary_relief_candidate),
        "secondary_confirm_count": int(confirm_count),
        "secondary_confirmations": confirmations,
        "risk_on_confirm": bool(risk_on_confirm),
        "smallcap_stress": bool(smallcap_stress),
        "vix_extreme": bool(vix_extreme),
        "skew_extreme": bool(skew_extreme),
        "vix_close": None if not _is_valid(vix_close) else float(vix_close),
        "used_unknown_fallback": False,
    }
    return signal, detail


def build_short_signal(
    price_vol: pd.DataFrame,
    flow: pd.DataFrame,
    sentiment: pd.DataFrame,
    run_id: str = "",
    skew_gold_root: Optional[Path] = None,
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
    skew_gold_root : Path, optional
        SKEW Gold 데이터 루트 경로. None이면 PRETREND_DATA_ROOT 환경변수 기반 기본값 사용.

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
            "short_detail_json": None,
            "source_run_id": run_id,
        })[SHORT_OUTPUT_COLUMNS]

    # SPY 데이터 추출 (price_vol에서)
    spy_pv = price_vol[price_vol["symbol"] == "SPY"] if "symbol" in price_vol.columns else pd.DataFrame()

    # flow에서 평균 volume_zscore 추출
    flow_agg = pd.DataFrame()
    if not flow.empty and "volume_zscore_20d" in flow.columns:
        flow_agg = flow.groupby("trade_date").agg(
            avg_vol_zscore=("volume_zscore_20d", "mean"),
        ).reset_index()

    # sentiment에서 tlt_ret_1d, iau_ret_1d, iwm_spy_vol_spread, vix_close 추출 (trade_date grain)
    sent_tlt: dict = {}
    sent_iau: dict = {}
    sent_iwm_vol_spread: dict = {}
    sent_vix_close: dict = {}
    if not sentiment.empty:
        for _, srow in sentiment.iterrows():
            td = srow["trade_date"]
            sent_tlt[td] = srow.get("tlt_ret_1d") if "tlt_ret_1d" in srow.index else None
            sent_iau[td] = srow.get("iau_ret_1d") if "iau_ret_1d" in srow.index else None
            sent_iwm_vol_spread[td] = (
                srow.get("iwm_spy_vol_spread") if "iwm_spy_vol_spread" in srow.index else None
            )
            sent_vix_close[td] = srow.get("vix_close") if "vix_close" in srow.index else None

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

        # sentiment: tlt/iau/iwm_vol_spread/vix + skew gold
        tlt_ret = sent_tlt.get(td)
        iau_ret = sent_iau.get(td)
        iwm_vol_spread = sent_iwm_vol_spread.get(td)
        vix_close = sent_vix_close.get(td)
        skew_extreme = bool(_load_skew_extreme(td, str(skew_gold_root) if skew_gold_root is not None else ""))

        signal, detail = _evaluate_short_signal(
            spy_ret_1d, spy_vol_20d,
            volume_zscore=vol_zscore,
            spy_intraday_range=spy_intraday,
            tlt_ret_1d=tlt_ret,
            iau_ret_1d=iau_ret,
            iwm_spy_vol_spread=iwm_vol_spread,
            vix_close=vix_close,
            skew_extreme=skew_extreme,
        )
        assert signal in SHORT_SIGNAL_ENUM, f"Invalid signal: {signal}"

        rows.append({
            "trade_date": td,
            "short_signal": signal,
            "short_signal_confidence": None,
            "short_detail_json": json.dumps(detail, sort_keys=True),
            "source_run_id": run_id,
        })

    return pd.DataFrame(rows, columns=SHORT_OUTPUT_COLUMNS)
