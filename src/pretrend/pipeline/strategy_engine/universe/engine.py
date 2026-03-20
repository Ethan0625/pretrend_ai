"""
Universe Selector Engine — WHAT_TO_HOLD 경계 입력.

v0: run_universe=true → 전체 후보 표시 (phase 필터 없음)
v1: Phase별 eligible pool + mid_regime별 Top-N 선택

Phase eligible pool (데이터 기반 도출, 2006~2024):
  - RECESSION  : USO·UNG 제외 (에너지 선물 구조적 약세)
  - SLOWDOWN   : UNG 제외
  - LATE_CYCLE : 전체 허용 (강세 섹터 부재 → live RS에 위임)
  - EXPANSION  : UNG 제외
  - RECOVERY   : USO·UNG·XLE 제외 (에너지 전반 약세)
  - UNKNOWN    : 전체 허용 (fail-open)

mid_regime Top-N:
  - RISK_OFF: 5  (보수적)
  - NEUTRAL : 7
  - RISK_ON : 9  (공격적)

CORE(SPY, TLT, IAU)는 phase 필터·Top-N 적용 제외, 항상 is_candidate=True.

Contract: docs/architecture/universe_contract.md
SOT: docs/strategy_engine_design.md §D1
"""
from __future__ import annotations

import logging
from typing import Dict, FrozenSet

import pandas as pd

from ..registries import CORE_HOLD_REGISTRY, TACTICAL_GROUP_REGISTRY
from .schema import ASSET_GROUP_ENUM, UNIVERSE_OUTPUT_COLUMNS

logger = logging.getLogger(__name__)


# ── Phase별 제외 종목 ─────────────────────────────────────────
# 데이터 분석(2006~2024 RS 집계) 기반. 에너지 선물 ETF 구조적 약세.
_PHASE_EXCLUDE: Dict[str, FrozenSet[str]] = {
    "RECESSION":  frozenset({"USO", "UNG"}),
    "SLOWDOWN":   frozenset({"UNG"}),
    "LATE_CYCLE": frozenset(),
    "EXPANSION":  frozenset({"UNG"}),
    "RECOVERY":   frozenset({"USO", "UNG", "XLE"}),
    "UNKNOWN":    frozenset(),   # fail-open
}

# ── mid_regime별 TACTICAL Top-N ──────────────────────────────
_MID_TOP_N: Dict[str, int] = {
    "RISK_OFF": 5,
    "NEUTRAL":  7,
    "RISK_ON":  9,
    "UNKNOWN":  7,  # fallback
}


def build_universe(
    policy_selection: pd.DataFrame,
    gold_eod: pd.DataFrame,
) -> pd.DataFrame:
    """Universe 후보를 선별한다.

    Parameters
    ----------
    policy_selection : DataFrame
        build_policy_selection() 출력.
        long_phase, mid_regime, run_universe, trade_date 포함.
    gold_eod : DataFrame
        Gold EOD features (symbol, trade_date, asset_group, ret_20d 등).

    Returns
    -------
    DataFrame with UNIVERSE_OUTPUT_COLUMNS.
    Grain: (decision_date, symbol).
    is_candidate=True → CORE 전체 + TACTICAL Top-N.
    """
    if policy_selection.empty:
        return pd.DataFrame(columns=UNIVERSE_OUTPUT_COLUMNS)

    core_symbols: FrozenSet[str] = frozenset(CORE_HOLD_REGISTRY)
    tactical_symbols: FrozenSet[str] = frozenset(
        sym for syms in TACTICAL_GROUP_REGISTRY.values() for sym in syms
    )
    all_symbols = core_symbols | tactical_symbols

    rows = []
    for _, ps_row in policy_selection.iterrows():
        td = ps_row["trade_date"]
        run_univ = ps_row.get("run_universe", True)

        if not run_univ:
            continue

        long_phase = str(ps_row.get("long_phase", "UNKNOWN"))
        mid_regime = str(ps_row.get("mid_regime", "UNKNOWN"))

        # 해당 trade_date Gold EOD 추출
        eod_td = (
            gold_eod[gold_eod["trade_date"] == td]
            if not gold_eod.empty
            else pd.DataFrame()
        )
        if eod_td.empty:
            continue

        eod_filtered = eod_td[eod_td["symbol"].isin(all_symbols)].copy()
        if eod_filtered.empty:
            continue

        # ── RS 산출: ret_20d(symbol) - ret_20d(SPY) ──────────
        spy_ret = eod_filtered.loc[
            eod_filtered["symbol"] == "SPY", "ret_20d"
        ]
        spy_ret_val = float(spy_ret.iloc[0]) if not spy_ret.empty else 0.0

        eod_filtered["rs_vs_spy"] = eod_filtered["ret_20d"] - spy_ret_val

        # ── Phase eligible pool: 제외 종목 필터 ──────────────
        exclude = _PHASE_EXCLUDE.get(long_phase, frozenset())

        # ── TACTICAL: eligible → RS 정렬 → Top-N 선택 ────────
        top_n = _MID_TOP_N.get(mid_regime, 7)

        tactical_eligible = eod_filtered[
            eod_filtered["symbol"].isin(tactical_symbols)
            & ~eod_filtered["symbol"].isin(exclude)
        ].sort_values("rs_vs_spy", ascending=False)

        top_tactical = set(tactical_eligible.head(top_n)["symbol"].tolist())

        # ── 출력 조립 ─────────────────────────────────────────
        for _, eod_row in eod_filtered.iterrows():
            sym = eod_row["symbol"]
            ag = eod_row.get("asset_group", "UNKNOWN")
            if ag not in ASSET_GROUP_ENUM:
                ag = "INDEX"

            is_core = sym in core_symbols
            is_tactical_top = sym in top_tactical

            # 제외 종목은 CORE라도 is_candidate=False (향후 확장 여지)
            # 현재 CORE는 항상 True
            is_candidate = is_core or is_tactical_top

            rows.append({
                "decision_date": td,
                "symbol": sym,
                "asset_group": ag,
                "relative_strength": eod_row.get("rs_vs_spy", eod_row.get("ret_20d")),
                "is_candidate": is_candidate,
            })

    if not rows:
        return pd.DataFrame(columns=UNIVERSE_OUTPUT_COLUMNS)

    return pd.DataFrame(rows, columns=UNIVERSE_OUTPUT_COLUMNS)
