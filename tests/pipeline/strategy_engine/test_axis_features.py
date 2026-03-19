"""
Axis Feature 계약 테스트.

Contract: docs/architecture/axis_horizon_dependency_contract.md §3
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from pretrend.pipeline.strategy_engine.config import (
    PolicyProfile,
    StrategyEngineConfig,
    DEFAULT_POLICY_V0,
)
from pretrend.pipeline.strategy_engine.axis_features.schema import (
    MACRO_POLICY_COLUMNS,
    MACRO_POLICY_REQUIRED_COLUMNS,
    PRICE_VOL_COLUMNS,
    PRICE_VOL_REQUIRED_COLUMNS,
    FLOW_COLUMNS,
    FLOW_REQUIRED_COLUMNS,
    SENTIMENT_COLUMNS,
    SENTIMENT_REQUIRED_COLUMNS,
    AxisFeatureBundle,
)
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


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def sample_gold_macro() -> pd.DataFrame:
    """Gold Macro Feature 샘플."""
    return pd.DataFrame(
        {
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
        }
    )


@pytest.fixture
def sample_gold_eod() -> pd.DataFrame:
    """Gold EOD Feature 샘플 (SPY, TLT, IAU, IWM 포함)."""
    dates = [date(2024, 6, 3), date(2024, 6, 4)]
    symbols = ["SPY", "TLT", "IAU", "IWM"]
    rows = []
    for td in dates:
        for i, sym in enumerate(symbols):
            rows.append(
                {
                    "symbol": sym,
                    "trade_date": td,
                    "open": 500.0 + i,
                    "high": 505.0 + i,
                    "low": 498.0 + i,
                    "close": 503.0 + i,
                    "adj_close": 503.0 + i,
                    "volume": 1_000_000 * (i + 1),
                    "currency": "USD",
                    "prev_adj_close": 501.0 + i,
                    "ret_1d": 0.004 * ((-1) ** i),
                    "log_ret_1d": 0.004 * ((-1) ** i),
                    "ret_5d": 0.02 * ((-1) ** i),
                    "ret_20d": 0.05 * ((-1) ** i),
                    "vol_20d": 0.15 + 0.02 * i,
                    "vol_60d": 0.14 + 0.02 * i,
                    "ma_5": 500.0,
                    "ma_20": 498.0,
                    "ma_60": 495.0,
                    "ma_120": 490.0,
                    "ma_ratio_5_20": 1.004,
                    "atr_14": 5.0 + i,
                    "rsi_14": 55.0 + i * 3,
                    "intraday_range": 0.014 + 0.002 * i,
                    "gap_open": 0.001,
                    "volume_zscore_20d": 0.5 + i * 0.8,
                    "is_trading_day": True,
                    "is_missing_imputed": False,
                    "is_outlier": False,
                    "is_partial_day": False,
                    "asset_group": "INDEX" if sym in ("SPY", "IWM") else ("BOND" if sym == "TLT" else "COMMODITY"),
                    "asset_name": sym,
                    "asset_subtype": None,
                    "run_id_gold": "test_run",
                    "ingestion_ts_gold": pd.Timestamp.now("UTC"),
                }
            )
    return pd.DataFrame(rows)


# ── Config 테스트 ─────────────────────────────────────────


class TestPolicyProfile:
    def test_default_policy_v0(self):
        p = DEFAULT_POLICY_V0
        assert p.policy_profile_id == "RC_V0_DEFAULT"
        assert p.target_invested_lower <= p.target_invested_upper
        assert p.adjustment_limit > 0
        assert p.step_size > 0

    def test_invalid_range_raises(self):
        with pytest.raises(ValueError, match="target_invested_lower"):
            PolicyProfile(
                policy_profile_id="BAD",
                target_invested_lower=0.8,
                target_invested_upper=0.3,
                adjustment_limit=0.1,
                step_size=0.05,
                rounding_policy="ROUND_DOWN",
                policy_version="v0",
            )

    def test_invalid_adjustment_limit(self):
        with pytest.raises(ValueError, match="adjustment_limit"):
            PolicyProfile(
                policy_profile_id="BAD",
                target_invested_lower=0.3,
                target_invested_upper=0.6,
                adjustment_limit=0.0,
                step_size=0.05,
                rounding_policy="ROUND_DOWN",
                policy_version="v0",
            )


class TestStrategyEngineConfig:
    def test_from_env(self):
        cfg = StrategyEngineConfig.from_env()
        assert cfg.gold_macro_root.name == "macro_features"
        assert cfg.gold_eod_root.name == "eod_features"
        assert cfg.strategy_output_root.name == "strategy"

    def test_meta_root_default(self):
        cfg = StrategyEngineConfig.from_env()
        assert cfg.meta_root == cfg.data_root / "meta"

    def test_strategy_job_log_path(self):
        cfg = StrategyEngineConfig.from_env()
        assert cfg.strategy_job_log_path.name == "strategy_engine_log.parquet"


# ── macro_policy 테스트 ───────────────────────────────────


class TestMacroPolicyAxis:
    def test_columns_present(self, sample_gold_macro):
        result = build_macro_policy_axis(sample_gold_macro)
        for col in MACRO_POLICY_REQUIRED_COLUMNS:
            assert col in result.columns, f"Missing required column: {col}"
        assert "coverage" in result.columns
        assert "is_stale" in result.columns

    def test_empty_input(self):
        result = build_macro_policy_axis(pd.DataFrame())
        assert result.empty
        assert "coverage" in result.columns

    def test_coverage_all_present(self, sample_gold_macro):
        result = build_macro_policy_axis(sample_gold_macro)
        assert (result["coverage"] == 1.0).all()

    def test_coverage_partial(self, sample_gold_macro):
        sample_gold_macro.loc[0, "regime"] = None
        result = build_macro_policy_axis(sample_gold_macro)
        assert result.loc[0, "coverage"] == 0.75  # 3/4 required cols


# ── price_volatility 테스트 ───────────────────────────────


class TestPriceVolatilityAxis:
    def test_columns_present(self, sample_gold_eod):
        result = build_price_volatility_axis(sample_gold_eod)
        for col in PRICE_VOL_REQUIRED_COLUMNS:
            assert col in result.columns, f"Missing required column: {col}"

    def test_empty_input(self):
        result = build_price_volatility_axis(pd.DataFrame())
        assert result.empty

    def test_row_count_preserved(self, sample_gold_eod):
        result = build_price_volatility_axis(sample_gold_eod)
        assert len(result) == len(sample_gold_eod)


# ── flow_structure 테스트 ─────────────────────────────────


class TestFlowStructureAxis:
    def test_columns_present(self, sample_gold_eod):
        result = build_flow_structure_axis(sample_gold_eod)
        for col in FLOW_REQUIRED_COLUMNS:
            assert col in result.columns, f"Missing required column: {col}"
        assert "obv_slope" in result.columns
        assert "turnover_spike_flag" in result.columns
        assert "breadth_iwm_spy_spread" in result.columns

    def test_empty_input(self):
        result = build_flow_structure_axis(pd.DataFrame())
        assert result.empty

    def test_turnover_spike_flag(self, sample_gold_eod):
        result = build_flow_structure_axis(sample_gold_eod)
        # IWM has volume_zscore_20d = 0.5 + 3*0.8 = 2.9 > 2.0
        iwm_rows = result[sample_gold_eod["symbol"] == "IWM"]
        assert iwm_rows["turnover_spike_flag"].any()

    def test_breadth_spread_present(self, sample_gold_eod):
        result = build_flow_structure_axis(sample_gold_eod)
        # IWM과 SPY가 있으므로 breadth spread 산출 가능
        assert result["breadth_iwm_spy_spread"].notna().any()


# ── sentiment 테스트 ──────────────────────────────────────


class TestSentimentAxis:
    def test_columns_present(self, sample_gold_eod):
        result = build_sentiment_proxy_axis(sample_gold_eod)
        for col in SENTIMENT_REQUIRED_COLUMNS:
            assert col in result.columns, f"Missing required column: {col}"

    def test_empty_input(self):
        result = build_sentiment_proxy_axis(pd.DataFrame())
        assert result.empty

    def test_grain_is_trade_date(self, sample_gold_eod):
        """sentiment axis는 trade_date 기준 (심볼 차원 제거)."""
        result = build_sentiment_proxy_axis(sample_gold_eod)
        assert "symbol" not in result.columns
        assert len(result) == len(sample_gold_eod["trade_date"].unique())

    def test_cross_symbol_derivations(self, sample_gold_eod):
        result = build_sentiment_proxy_axis(sample_gold_eod)
        assert result["spy_ret_1d"].notna().any()
        assert result["tlt_ret_1d"].notna().any()
        assert result["iwm_spy_relative_strength"].notna().any()
        assert result["iwm_spy_vol_spread"].notna().any()

    def test_vix_is_optional_column(self, sample_gold_eod):
        """v1.2에서 VIX는 optional 컬럼이지만 없어도 axis는 동작한다."""
        result = build_sentiment_proxy_axis(sample_gold_eod)
        assert "vix_close" in result.columns
        assert result["vix_close"].isna().all()


# ── AxisFeatureBundle 테스트 ──────────────────────────────


class TestAxisFeatureBundle:
    def test_bundle_construction(self, sample_gold_macro, sample_gold_eod):
        bundle = AxisFeatureBundle(
            macro_policy=build_macro_policy_axis(sample_gold_macro),
            price_volatility=build_price_volatility_axis(sample_gold_eod),
            flow_structure=build_flow_structure_axis(sample_gold_eod),
            sentiment=build_sentiment_proxy_axis(sample_gold_eod),
        )
        assert not bundle.macro_policy.empty
        assert not bundle.price_volatility.empty
        assert not bundle.flow_structure.empty
        assert not bundle.sentiment.empty
