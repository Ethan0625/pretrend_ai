"""
Axis Feature: price_volatility — Gold EOD에서 가격/변동성 축 추출.

Contract: docs/architecture/axis_horizon_dependency_contract.md §3.2
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import List, Optional

import pandas as pd

from .schema import PRICE_VOL_COLUMNS

logger = logging.getLogger(__name__)


def load_gold_eod(
    gold_eod_root: Path,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    symbols: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Gold EOD parquet를 로드한다.

    Parameters
    ----------
    gold_eod_root : Gold EOD root (e.g. data/gold/eod/eod_features)
    start_date, end_date : trade_date 필터 (optional)
    symbols : 심볼 필터 (optional)
    """
    files = list(gold_eod_root.rglob("*.parquet"))
    if not files:
        logger.warning("[AxisEOD] No Gold EOD parquet under %s", gold_eod_root)
        return pd.DataFrame()

    df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)

    if "trade_date" in df.columns:
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date

    if start_date is not None:
        df = df[df["trade_date"] >= start_date]
    if end_date is not None:
        df = df[df["trade_date"] <= end_date]
    if symbols:
        df = df[df["symbol"].isin(symbols)]

    return df


def build_price_volatility_axis(df_gold_eod: pd.DataFrame) -> pd.DataFrame:
    """Gold EOD → price_volatility axis feature.

    컬럼 선택만 수행. 빈 입력이면 빈 DataFrame 반환.
    """
    if df_gold_eod.empty:
        return pd.DataFrame(columns=PRICE_VOL_COLUMNS)

    df = df_gold_eod.copy()

    for col in PRICE_VOL_COLUMNS:
        if col not in df.columns:
            df[col] = None

    return df[PRICE_VOL_COLUMNS].copy().reset_index(drop=True)
