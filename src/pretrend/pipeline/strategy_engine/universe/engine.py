"""
Universe Selector Engine — WHAT_TO_HOLD 경계 입력.

Composer(policy_selection) 출력의 run_universe + Gold EOD에서
Observability ETF 후보를 선별한다.

Contract: docs/architecture/universe_contract.md
SOT: docs/strategy_engine_design.md §D1

v0 로직:
  run_universe=false → 0 candidates
  run_universe=true → asset_group 내 ret_20d 기준 상대강도 산출, 전체 후보 표시
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from ..registries import CORE_HOLD_REGISTRY, TACTICAL_GROUP_REGISTRY
from .schema import ASSET_GROUP_ENUM, UNIVERSE_OUTPUT_COLUMNS

logger = logging.getLogger(__name__)


def build_universe(
    policy_selection: pd.DataFrame,
    gold_eod: pd.DataFrame,
) -> pd.DataFrame:
    """Universe 후보를 선별한다.

    Parameters
    ----------
    policy_selection : DataFrame
        build_policy_selection() 출력. run_universe, trade_date 포함.
    gold_eod : DataFrame
        Gold EOD features (symbol, trade_date, asset_group, ret_20d 등).

    Returns
    -------
    DataFrame with UNIVERSE_OUTPUT_COLUMNS.
    Grain: (rebalance_date, symbol).
    """
    if policy_selection.empty:
        return pd.DataFrame(columns=UNIVERSE_OUTPUT_COLUMNS)

    # trade_date별로 run_universe 확인
    rows = []
    for _, ps_row in policy_selection.iterrows():
        td = ps_row["trade_date"]
        run_univ = ps_row.get("run_universe", True)

        if not run_univ:
            # run_universe=false → 0 candidates
            continue

        # 해당 trade_date의 Gold EOD 추출
        eod_td = gold_eod[gold_eod["trade_date"] == td] if not gold_eod.empty else pd.DataFrame()

        if eod_td.empty:
            continue

        # Observability ETF만 필터 (Core + Tactical)
        all_symbols = set(CORE_HOLD_REGISTRY)
        for syms in TACTICAL_GROUP_REGISTRY.values():
            all_symbols.update(syms)

        eod_filtered = eod_td[eod_td["symbol"].isin(all_symbols)] if "symbol" in eod_td.columns else pd.DataFrame()

        if eod_filtered.empty:
            continue

        # asset_group별 relative_strength 산출 (ret_20d 기준 순위)
        for _, eod_row in eod_filtered.iterrows():
            sym = eod_row["symbol"]
            ag = eod_row.get("asset_group", "UNKNOWN")
            ret_20d = eod_row.get("ret_20d")

            # asset_group ENUM 강제
            if ag not in ASSET_GROUP_ENUM:
                ag = "INDEX"  # fallback

            rows.append({
                "rebalance_date": td,
                "symbol": sym,
                "asset_group": ag,
                "relative_strength": ret_20d,
                "is_candidate": True,
            })

    if not rows:
        return pd.DataFrame(columns=UNIVERSE_OUTPUT_COLUMNS)

    return pd.DataFrame(rows, columns=UNIVERSE_OUTPUT_COLUMNS)
