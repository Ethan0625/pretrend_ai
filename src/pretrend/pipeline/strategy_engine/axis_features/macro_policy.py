"""
Axis Feature: macro_policy — Gold Macro에서 정책/매크로 축 추출.

Contract: docs/architecture/axis_horizon_dependency_v1_contract.md §3.2
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import List, Optional

import pandas as pd

from .schema import MACRO_POLICY_COLUMNS

logger = logging.getLogger(__name__)


def load_gold_macro(
    gold_macro_root: Path,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> pd.DataFrame:
    """Gold Macro parquet를 로드한다.

    Parameters
    ----------
    gold_macro_root : Gold Macro root (e.g. data/gold/macro/macro_features)
    start_date, end_date : trade_date 필터 (optional)
    """
    files = list(gold_macro_root.rglob("*.parquet"))
    if not files:
        logger.warning("[AxisMacro] No Gold Macro parquet under %s", gold_macro_root)
        return pd.DataFrame()

    df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)

    if "trade_date" in df.columns:
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date

    if start_date is not None:
        df = df[df["trade_date"] >= start_date]
    if end_date is not None:
        df = df[df["trade_date"] <= end_date]

    return df


def build_macro_policy_axis(df_gold_macro: pd.DataFrame) -> pd.DataFrame:
    """Gold Macro → macro_policy axis feature.

    컬럼 선택 + coverage 플래그 추가.
    빈 입력이면 빈 DataFrame 반환.
    """
    if df_gold_macro.empty:
        return pd.DataFrame(columns=MACRO_POLICY_COLUMNS + ["coverage", "is_stale"])

    df = df_gold_macro.copy()

    # 필요한 컬럼만 선택 (없는 컬럼은 None으로 채움)
    for col in MACRO_POLICY_COLUMNS:
        if col not in df.columns:
            df[col] = None

    df = df[MACRO_POLICY_COLUMNS].copy()

    # coverage: 필수 컬럼 중 non-null 비율
    required = ["indicator_id", "trade_date", "selected_value", "regime"]
    non_null_count = df[required].notna().sum(axis=1)
    df["coverage"] = non_null_count / len(required)

    # is_stale: selected_release_date가 없으면 stale로 간주
    df["is_stale"] = df["selected_release_date"].isna()

    return df.reset_index(drop=True)
