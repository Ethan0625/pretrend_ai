"""
Axis Feature schema definitions.

Contract: docs/architecture/axis_horizon_dependency_v1_contract.md §3
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pandas as pd

# ── macro_policy axis ──────────────────────────────────────

MACRO_POLICY_REQUIRED_COLUMNS: List[str] = [
    "indicator_id",
    "trade_date",
    "selected_value",
    "selected_release_date",
    "regime",
]

MACRO_POLICY_OPTIONAL_COLUMNS: List[str] = [
    "delta_1m",
    "delta_3m",
    "delta_6m",
    "zscore_12m",
    "release_source",
    "direction",
]

MACRO_POLICY_COLUMNS: List[str] = (
    MACRO_POLICY_REQUIRED_COLUMNS + MACRO_POLICY_OPTIONAL_COLUMNS
)

# ── price_volatility axis ─────────────────────────────────

PRICE_VOL_REQUIRED_COLUMNS: List[str] = [
    "symbol",
    "trade_date",
    "ret_1d",
    "ret_5d",
    "ret_20d",
    "vol_20d",
    "vol_60d",
]

PRICE_VOL_OPTIONAL_COLUMNS: List[str] = [
    "atr_14",
    "rsi_14",
    "intraday_range",
    "asset_group",
]

PRICE_VOL_COLUMNS: List[str] = (
    PRICE_VOL_REQUIRED_COLUMNS + PRICE_VOL_OPTIONAL_COLUMNS
)

# ── flow_structure axis ───────────────────────────────────

FLOW_REQUIRED_COLUMNS: List[str] = [
    "symbol",
    "trade_date",
    "volume",
    "asset_group",
]

FLOW_OPTIONAL_COLUMNS: List[str] = [
    "volume_zscore_20d",
    "obv_slope",
    "turnover_spike_flag",
    "breadth_iwm_spy_spread",
]

FLOW_COLUMNS: List[str] = FLOW_REQUIRED_COLUMNS + FLOW_OPTIONAL_COLUMNS

# ── sentiment axis (v0: proxy) ────────────────────────────

SENTIMENT_REQUIRED_COLUMNS: List[str] = [
    "trade_date",
]

SENTIMENT_OPTIONAL_COLUMNS: List[str] = [
    "spy_ret_1d",
    "tlt_ret_1d",
    "iau_ret_1d",
    "spy_vol_20d",
    "spy_intraday_range",
    "iwm_spy_relative_strength",
    "iwm_spy_vol_spread",
]

SENTIMENT_COLUMNS: List[str] = (
    SENTIMENT_REQUIRED_COLUMNS + SENTIMENT_OPTIONAL_COLUMNS
)


# ── Bundle ─────────────────────────────────────────────────


@dataclass
class AxisFeatureBundle:
    """4축 Axis Feature를 묶는 컨테이너."""

    macro_policy: pd.DataFrame
    price_volatility: pd.DataFrame
    flow_structure: pd.DataFrame
    sentiment: pd.DataFrame
