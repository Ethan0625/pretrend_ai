"""
Mid Regime Engine 계약 테스트.

Contract: docs/architecture/market_structure_mid_v1_contract.md
DoD: MM1 (컬럼/타입), MM2 (ENUM), MM3 (결측→UNKNOWN), MM4 (macro/flow 통합)
"""
from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest

from pretrend.pipeline.strategy_engine.axis_horizon_state.schema import (
    MID_REGIME_ENUM,
    MID_OUTPUT_COLUMNS,
)
from pretrend.pipeline.strategy_engine.axis_horizon_state.mid_engine import (
    build_mid_regime,
)


@pytest.fixture
def price_vol_sample() -> pd.DataFrame:
    """price_volatility axis 샘플 (SPY + TLT)."""
    # vol_20d = 일간 수익률 std: median≈0.008, p90≈0.017
    return pd.DataFrame([
        {"symbol": "SPY", "trade_date": date(2024, 6, 3),
         "ret_1d": 0.004, "ret_20d": 0.05, "vol_20d": 0.008, "intraday_range": 0.012},
        {"symbol": "TLT", "trade_date": date(2024, 6, 3),
         "ret_1d": -0.002, "ret_20d": -0.03, "vol_20d": 0.006, "intraday_range": 0.008},
        {"symbol": "SPY", "trade_date": date(2024, 6, 4),
         "ret_1d": -0.015, "ret_20d": -0.04, "vol_20d": 0.025, "intraday_range": 0.025},
        {"symbol": "TLT", "trade_date": date(2024, 6, 4),
         "ret_1d": 0.008, "ret_20d": 0.02, "vol_20d": 0.012, "intraday_range": 0.010},
    ])


class TestMidRegimeMM1:
    """MM1: 필수 컬럼 존재 및 타입."""

    def test_output_columns(self, price_vol_sample):
        result = build_mid_regime(price_vol_sample)
        for col in MID_OUTPUT_COLUMNS:
            assert col in result.columns, f"Missing: {col}"

    def test_output_row_count(self, price_vol_sample):
        result = build_mid_regime(price_vol_sample)
        assert len(result) == 2  # 2 trade_dates


class TestMidRegimeMM2:
    """MM2: ENUM 유효성."""

    def test_enum_values_valid(self, price_vol_sample):
        result = build_mid_regime(price_vol_sample)
        for val in result["mid_regime"]:
            assert val in MID_REGIME_ENUM, f"Invalid: {val}"

    def test_risk_on(self, price_vol_sample):
        """SPY ret_20d > 0 + vol_20d < 0.015 → RISK_ON."""
        result = build_mid_regime(price_vol_sample)
        row = result[result["trade_date"] == date(2024, 6, 3)]
        assert row.iloc[0]["mid_regime"] == "RISK_ON"

    def test_risk_off(self, price_vol_sample):
        """SPY ret_20d < 0 + vol_20d > 0.015 → RISK_OFF."""
        result = build_mid_regime(price_vol_sample)
        row = result[result["trade_date"] == date(2024, 6, 4)]
        assert row.iloc[0]["mid_regime"] == "RISK_OFF"


class TestMidRegimeMM3:
    """MM3: 결측 시 UNKNOWN."""

    def test_empty_input(self):
        result = build_mid_regime(pd.DataFrame())
        assert result.empty
        assert set(MID_OUTPUT_COLUMNS).issubset(result.columns)

    def test_no_spy_data(self):
        """SPY가 없으면 UNKNOWN."""
        df = pd.DataFrame([
            {"symbol": "TLT", "trade_date": date(2024, 6, 3),
             "ret_20d": 0.02, "vol_20d": 0.10},
        ])
        result = build_mid_regime(df)
        assert len(result) == 1
        assert result.iloc[0]["mid_regime"] == "UNKNOWN"

    def test_missing_ret_20d(self):
        """ret_20d가 None → UNKNOWN."""
        df = pd.DataFrame([
            {"symbol": "SPY", "trade_date": date(2024, 6, 3),
             "ret_20d": None, "vol_20d": 0.008},
        ])
        result = build_mid_regime(df)
        assert result.iloc[0]["mid_regime"] == "UNKNOWN"


@pytest.fixture
def price_vol_neutral() -> pd.DataFrame:
    """price_vol=NEUTRAL 샘플: ret_20d > 0 이지만 vol_20d > 0.015 → NEUTRAL."""
    return pd.DataFrame([
        {"symbol": "SPY", "trade_date": date(2024, 6, 3),
         "ret_20d": 0.01, "vol_20d": 0.018, "intraday_range": 0.012},
    ])


@pytest.fixture
def price_vol_risk_on() -> pd.DataFrame:
    """price_vol=RISK_ON 샘플: ret_20d > 0 + vol_20d < 0.015."""
    return pd.DataFrame([
        {"symbol": "SPY", "trade_date": date(2024, 6, 3),
         "ret_20d": 0.05, "vol_20d": 0.008, "intraday_range": 0.010},
    ])


class TestMidRegimeMM4:
    """MM4: macro_policy/flow 통합 — 선택 축이 regime override."""

    def test_macro_tightening_overrides_neutral(self, price_vol_neutral):
        """price_vol=NEUTRAL + macro tightening → RISK_OFF (다수결 2:1)."""
        macro_df = pd.DataFrame([{
            "trade_date": date(2024, 6, 3), "indicator_id": "CPI_US_ALL_ITEMS_SA",
            "regime": "tightening", "delta_6m": 1.0,
        }])
        # breadth도 RISK_OFF로 맞춰 2:1 확보
        flow_df = pd.DataFrame([{
            "trade_date": date(2024, 6, 3), "symbol": "IWM",
            "asset_group": "INDEX", "breadth_iwm_spy_spread": -0.010,
        }])
        result = build_mid_regime(price_vol_neutral, macro_policy=macro_df, flow=flow_df)
        assert result.iloc[0]["mid_regime"] == "RISK_OFF"

    def test_macro_easing_overrides_neutral(self, price_vol_neutral):
        """price_vol=NEUTRAL + macro easing + breadth 높음 → RISK_ON (다수결 2:1)."""
        macro_df = pd.DataFrame([{
            "trade_date": date(2024, 6, 3), "indicator_id": "CPI_US_ALL_ITEMS_SA",
            "regime": "easing", "delta_6m": -1.0,
        }])
        flow_df = pd.DataFrame([{
            "trade_date": date(2024, 6, 3), "symbol": "IWM",
            "asset_group": "INDEX", "breadth_iwm_spy_spread": 0.010,
        }])
        result = build_mid_regime(price_vol_neutral, macro_policy=macro_df, flow=flow_df)
        assert result.iloc[0]["mid_regime"] == "RISK_ON"

    def test_breadth_high_alone_overrides_neutral(self, price_vol_neutral):
        """price_vol=NEUTRAL + breadth > +0.005 단독 → NEUTRAL or RISK_ON (1:1 동점 → price_signal 우선)."""
        flow_df = pd.DataFrame([{
            "trade_date": date(2024, 6, 3), "symbol": "IWM",
            "asset_group": "INDEX", "breadth_iwm_spy_spread": 0.010,
        }])
        # price=NEUTRAL, macro=UNKNOWN, breadth=RISK_ON(0.010>0.005) → valid=[NEUTRAL, RISK_ON] → 동점
        result = build_mid_regime(price_vol_neutral, flow=flow_df)
        # macro 없으므로 valid=[NEUTRAL, RISK_ON] → 동점 → price_signal(NEUTRAL) 우선
        assert result.iloc[0]["mid_regime"] in {"NEUTRAL", "RISK_ON"}

    def test_price_vol_wins_when_optional_missing(self, price_vol_risk_on):
        """optional 축 없으면 price_vol 결과 그대로 (v0 backward compat)."""
        result = build_mid_regime(price_vol_risk_on)
        assert result.iloc[0]["mid_regime"] == "RISK_ON"

    def test_macro_multiple_indicators_mode(self, price_vol_neutral):
        """여러 indicator가 있을 때 regime 다수결 적용."""
        macro_df = pd.DataFrame([
            {"trade_date": date(2024, 6, 3), "indicator_id": "CPI_US_ALL_ITEMS_SA",
             "regime": "tightening", "delta_6m": 1.0},
            {"trade_date": date(2024, 6, 3), "indicator_id": "US_UNEMPLOYMENT_RATE",
             "regime": "tightening", "delta_6m": 0.5},
            {"trade_date": date(2024, 6, 3), "indicator_id": "CPI_US_CORE_SA",
             "regime": "easing", "delta_6m": -0.3},
        ])
        # flow도 RISK_OFF로 추가 → 3신호: price=NEUTRAL, macro=RISK_OFF, breadth=RISK_OFF → 2:1 → RISK_OFF
        flow_df = pd.DataFrame([{
            "trade_date": date(2024, 6, 3), "symbol": "IWM",
            "asset_group": "INDEX", "breadth_iwm_spy_spread": -0.010,
        }])
        result = build_mid_regime(price_vol_neutral, macro_policy=macro_df, flow=flow_df)
        # tightening 2, easing 1 → macro_signal=RISK_OFF; breadth<-0.005 → RISK_OFF
        # 3신호 [NEUTRAL, RISK_OFF, RISK_OFF] → RISK_OFF (2:1)
        assert result.iloc[0]["mid_regime"] == "RISK_OFF"


class TestMidRegimeMM5:
    """MM5: spread 방식 — ratio(나눗셈)가 틀렸던 케이스 검증.

    ratio 방식: SPY 음수 시 부호 반전 → IWM이 덜 하락해도 RISK_OFF 판정
    spread 방식: 방향 무관하게 상대 성과를 정확히 측정
    """

    def test_both_negative_iwm_less_negative_gives_risk_on_breadth(self, price_vol_neutral):
        """IWM -3% + SPY -5% → spread=+2% > +0.005 → breadth RISK_ON.

        ratio 방식: 0.6 < 0.8 → RISK_OFF (틀림).
        spread 방식: +2% > +0.005 → RISK_ON (올바름).
        price=NEUTRAL, breadth=RISK_ON, macro=UNKNOWN → 동점 → NEUTRAL or RISK_ON
        """
        flow_df = pd.DataFrame([{
            "trade_date": date(2024, 6, 3), "symbol": "IWM",
            "asset_group": "INDEX", "breadth_iwm_spy_spread": 0.020,
        }])
        result = build_mid_regime(price_vol_neutral, flow=flow_df)
        # valid=[NEUTRAL, RISK_ON] → 동점(1:1) → price 우선 → NEUTRAL
        assert result.iloc[0]["mid_regime"] in {"NEUTRAL", "RISK_ON"}

    def test_both_positive_iwm_lagging_gives_risk_off_breadth(self, price_vol_neutral):
        """IWM +3% + SPY +5% → spread=-2% < -0.005 → breadth RISK_OFF.

        price=NEUTRAL, breadth=RISK_OFF, macro=UNKNOWN → 동점 → NEUTRAL or RISK_OFF
        """
        flow_df = pd.DataFrame([{
            "trade_date": date(2024, 6, 3), "symbol": "IWM",
            "asset_group": "INDEX", "breadth_iwm_spy_spread": -0.020,
        }])
        result = build_mid_regime(price_vol_neutral, flow=flow_df)
        # valid=[NEUTRAL, RISK_OFF] → 동점(1:1) → price 우선 → NEUTRAL
        assert result.iloc[0]["mid_regime"] in {"NEUTRAL", "RISK_OFF"}

    def test_spread_in_neutral_zone_preserves_price_signal(self, price_vol_neutral):
        """spread=+0.003 (|spread| < 0.005) → breadth NEUTRAL → price_signal 그대로.

        price=NEUTRAL, breadth=NEUTRAL, macro=UNKNOWN → valid=[NEUTRAL, NEUTRAL] → NEUTRAL
        """
        flow_df = pd.DataFrame([{
            "trade_date": date(2024, 6, 3), "symbol": "IWM",
            "asset_group": "INDEX", "breadth_iwm_spy_spread": 0.003,
        }])
        result = build_mid_regime(price_vol_neutral, flow=flow_df)
        assert result.iloc[0]["mid_regime"] == "NEUTRAL"


class TestMidRegimeDetail:
    """detail JSON 출력 검증."""

    def test_detail_contains_signal_sources(self, price_vol_neutral):
        flow_df = pd.DataFrame([{
            "trade_date": date(2024, 6, 3), "symbol": "IWM",
            "asset_group": "INDEX", "breadth_iwm_spy_spread": 0.010,
        }])
        result = build_mid_regime(price_vol_neutral, flow=flow_df)
        detail = json.loads(result.iloc[0]["mid_detail_json"])
        assert "price_signal" in detail
        assert "macro_signal" in detail
        assert "breadth_signal" in detail
        assert "majority_source" in detail
