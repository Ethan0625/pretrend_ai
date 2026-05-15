"""Axis feature builders."""
from __future__ import annotations

import pandas as pd

from .flow_structure import build_flow_structure_axis
from .macro_policy import build_macro_policy_axis
from .price_volatility import build_price_volatility_axis
from .schema import (
    FLOW_COLUMNS,
    FLOW_OPTIONAL_COLUMNS,
    FLOW_REQUIRED_COLUMNS,
    MACRO_POLICY_COLUMNS,
    MACRO_POLICY_OPTIONAL_COLUMNS,
    MACRO_POLICY_REQUIRED_COLUMNS,
    PRICE_VOL_COLUMNS,
    PRICE_VOL_OPTIONAL_COLUMNS,
    PRICE_VOL_REQUIRED_COLUMNS,
    SENTIMENT_COLUMNS,
    SENTIMENT_OPTIONAL_COLUMNS,
    SENTIMENT_REQUIRED_COLUMNS,
    AxisFeatureBundle,
)
from .sentiment import build_sentiment_proxy_axis


def build_axis_features(
    df_gold_macro: pd.DataFrame,
    df_gold_eod: pd.DataFrame,
) -> AxisFeatureBundle:
    """Build the four axis feature frames as one bundle."""
    return AxisFeatureBundle(
        macro_policy=build_macro_policy_axis(df_gold_macro),
        price_volatility=build_price_volatility_axis(df_gold_eod),
        flow_structure=build_flow_structure_axis(df_gold_eod),
        sentiment=build_sentiment_proxy_axis(df_gold_eod),
    )


__all__ = [
    "AxisFeatureBundle",
    "FLOW_COLUMNS",
    "FLOW_OPTIONAL_COLUMNS",
    "FLOW_REQUIRED_COLUMNS",
    "MACRO_POLICY_COLUMNS",
    "MACRO_POLICY_OPTIONAL_COLUMNS",
    "MACRO_POLICY_REQUIRED_COLUMNS",
    "PRICE_VOL_COLUMNS",
    "PRICE_VOL_OPTIONAL_COLUMNS",
    "PRICE_VOL_REQUIRED_COLUMNS",
    "SENTIMENT_COLUMNS",
    "SENTIMENT_OPTIONAL_COLUMNS",
    "SENTIMENT_REQUIRED_COLUMNS",
    "build_axis_features",
    "build_flow_structure_axis",
    "build_macro_policy_axis",
    "build_price_volatility_axis",
    "build_sentiment_proxy_axis",
]
