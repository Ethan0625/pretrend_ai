"""
Axis × Horizon State 12-slot 통합 테스트.

SOT: docs/strategy_engine_design.md §A3, §F
DoD: 12 슬롯 존재 검증, ENUM 유효성, 결측→UNKNOWN
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from pretrend.pipeline.strategy_engine.axis_features.schema import AxisFeatureBundle
from pretrend.pipeline.strategy_engine.axis_features.macro_policy import (
    build_macro_policy_axis,
)
from pretrend.pipeline.strategy_engine.axis_features.price_volatility import (
    build_price_volatility_axis,
)
from pretrend.pipeline.strategy_engine.axis_features.flow_structure import (
    build_flow_structure_axis,
)
from pretrend.pipeline.strategy_engine.axis_features.sentiment import (
    build_sentiment_proxy_axis,
)
from pretrend.pipeline.strategy_engine.axis_horizon_state.schema import (
    AXIS_HORIZON_STATE_COLUMNS,
    LONG_PHASE_ENUM,
    MID_REGIME_ENUM,
    SHORT_SIGNAL_ENUM,
)
from pretrend.pipeline.strategy_engine.axis_horizon_state.builder import (
    build_axis_horizon_state,
)


@pytest.fixture
def gold_macro() -> pd.DataFrame:
    return pd.DataFrame({
        "indicator_id": ["CPI_US_ALL_ITEMS_SA", "US_UNEMPLOYMENT_RATE"] * 2,
        "trade_date": [date(2024, 6, 3)] * 2 + [date(2024, 6, 4)] * 2,
        "selected_observation_date": [date(2024, 5, 1)] * 4,
        "selected_value": [310.0, 3.9, 310.5, 3.8],
        "selected_release_date": [date(2024, 6, 1)] * 4,
        "delta_1m": [0.5, -0.1, 0.6, -0.2],
        "delta_3m": [1.2, -0.3, 1.3, -0.4],
        "delta_6m": [2.1, -0.5, 2.2, -0.6],
        "direction": ["up", "down", "up", "down"],
        "regime": ["tightening", "easing", "tightening", "easing"],
        "zscore_12m": [1.1, -0.8, 1.2, -0.9],
        "release_source": ["econ_events"] * 4,
        "is_assumption_based": [False] * 4,
    })


@pytest.fixture
def gold_eod() -> pd.DataFrame:
    dates = [date(2024, 6, 3), date(2024, 6, 4)]
    symbols = ["SPY", "TLT", "IAU", "IWM"]
    rows = []
    for td in dates:
        for i, sym in enumerate(symbols):
            rows.append({
                "symbol": sym, "trade_date": td,
                "open": 500.0 + i, "high": 505.0 + i, "low": 498.0 + i,
                "close": 503.0 + i, "adj_close": 503.0 + i,
                "volume": 1_000_000 * (i + 1), "currency": "USD",
                "prev_adj_close": 501.0 + i,
                "ret_1d": 0.004 * ((-1) ** i),
                "log_ret_1d": 0.004 * ((-1) ** i),
                "ret_5d": 0.02 * ((-1) ** i),
                "ret_20d": 0.05 * ((-1) ** i),
                "vol_20d": 0.15 + 0.02 * i,
                "vol_60d": 0.14 + 0.02 * i,
                "ma_5": 500.0, "ma_20": 498.0, "ma_60": 495.0, "ma_120": 490.0,
                "ma_ratio_5_20": 1.004,
                "atr_14": 5.0 + i, "rsi_14": 55.0 + i * 3,
                "intraday_range": 0.014 + 0.002 * i,
                "gap_open": 0.001,
                "volume_zscore_20d": 0.5 + i * 0.8,
                "is_trading_day": True, "is_missing_imputed": False,
                "is_outlier": False, "is_partial_day": False,
                "asset_group": "INDEX" if sym in ("SPY", "IWM") else ("BOND" if sym == "TLT" else "COMMODITY"),
                "asset_name": sym, "asset_subtype": None,
                "run_id_gold": "test_run",
                "ingestion_ts_gold": pd.Timestamp.now("UTC"),
            })
    return pd.DataFrame(rows)


@pytest.fixture
def full_bundle(gold_macro, gold_eod) -> AxisFeatureBundle:
    return AxisFeatureBundle(
        macro_policy=build_macro_policy_axis(gold_macro),
        price_volatility=build_price_volatility_axis(gold_eod),
        flow_structure=build_flow_structure_axis(gold_eod),
        sentiment=build_sentiment_proxy_axis(gold_eod),
    )


class TestAxisHorizonState12Slot:
    def test_columns_present(self, full_bundle):
        result = build_axis_horizon_state(full_bundle, run_id="test_run")
        for col in AXIS_HORIZON_STATE_COLUMNS:
            assert col in result.columns, f"Missing: {col}"

    def test_grain_is_trade_date(self, full_bundle):
        result = build_axis_horizon_state(full_bundle, run_id="test_run")
        assert result["trade_date"].is_unique

    def test_all_enums_valid(self, full_bundle):
        result = build_axis_horizon_state(full_bundle, run_id="test_run")
        for val in result["long_phase"]:
            assert val in LONG_PHASE_ENUM
        for val in result["mid_regime"]:
            assert val in MID_REGIME_ENUM
        for val in result["short_signal"]:
            assert val in SHORT_SIGNAL_ENUM

    def test_no_null_state_columns(self, full_bundle):
        """상태 컬럼에 NULL 없음 (UNKNOWN으로 채움)."""
        result = build_axis_horizon_state(full_bundle, run_id="test_run")
        assert result["long_phase"].notna().all()
        assert result["mid_regime"].notna().all()
        assert result["short_signal"].notna().all()

    def test_run_id_propagated(self, full_bundle):
        result = build_axis_horizon_state(full_bundle, run_id="my_run_123")
        assert (result["source_run_id"] == "my_run_123").all()


class TestAxisHorizonStateFailOpen:
    def test_empty_bundle(self):
        """빈 bundle → 빈 결과."""
        empty_bundle = AxisFeatureBundle(
            macro_policy=pd.DataFrame(),
            price_volatility=pd.DataFrame(),
            flow_structure=pd.DataFrame(),
            sentiment=pd.DataFrame(),
        )
        result = build_axis_horizon_state(empty_bundle)
        assert result.empty
        assert set(AXIS_HORIZON_STATE_COLUMNS).issubset(result.columns)

    def test_missing_macro_only(self, gold_eod):
        """macro 결측 → long_phase=UNKNOWN, mid/short는 판정."""
        bundle = AxisFeatureBundle(
            macro_policy=pd.DataFrame(),
            price_volatility=build_price_volatility_axis(gold_eod),
            flow_structure=build_flow_structure_axis(gold_eod),
            sentiment=build_sentiment_proxy_axis(gold_eod),
        )
        result = build_axis_horizon_state(bundle, run_id="test")
        assert (result["long_phase"] == "UNKNOWN").all()
        assert result["mid_regime"].notna().all()
        assert result["short_signal"].notna().all()
