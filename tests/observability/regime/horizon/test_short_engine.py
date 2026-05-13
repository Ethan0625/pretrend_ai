"""
Short Signal Engine 계약 테스트.

Contract: docs/architecture/market_structure_short_v1_contract.md
DoD: MSH1 (컬럼/타입), MSH2 (ENUM), MSH3 (결측→UNKNOWN), MSH4 (VIX 없이 동작),
     MSH5 (sentiment 통합), MSH6 (flow volume spike)
"""
from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest

from pretrend.observability.regime.horizon.schema import (
    SHORT_SIGNAL_ENUM,
    SHORT_OUTPUT_COLUMNS,
)
from pretrend.observability.regime.horizon.short_engine import (
    _load_skew_extreme,
    build_short_signal,
)


@pytest.fixture
def pv_sample() -> pd.DataFrame:
    """price_volatility axis (SPY).
    vol_20d = 일간 수익률 std: median≈0.008, p90≈0.017
    """
    return pd.DataFrame([
        {"symbol": "SPY", "trade_date": date(2024, 6, 3),
         "ret_1d": -0.025, "ret_20d": -0.05, "vol_20d": 0.025,
         "intraday_range": 0.03, "asset_group": "INDEX"},
        {"symbol": "SPY", "trade_date": date(2024, 6, 4),
         "ret_1d": 0.01, "ret_20d": 0.03, "vol_20d": 0.008,
         "intraday_range": 0.01, "asset_group": "INDEX"},
    ])


@pytest.fixture
def flow_sample() -> pd.DataFrame:
    """flow_structure axis."""
    return pd.DataFrame([
        {"symbol": "SPY", "trade_date": date(2024, 6, 3),
         "volume": 5_000_000, "volume_zscore_20d": 2.5, "asset_group": "INDEX"},
        {"symbol": "SPY", "trade_date": date(2024, 6, 4),
         "volume": 2_000_000, "volume_zscore_20d": 0.3, "asset_group": "INDEX"},
    ])


@pytest.fixture
def sentiment_sample() -> pd.DataFrame:
    """sentiment axis (trade_date grain)."""
    return pd.DataFrame([
        {"trade_date": date(2024, 6, 3),
         "spy_ret_1d": -0.025, "tlt_ret_1d": 0.01, "iau_ret_1d": 0.005,
         "vix_close": None, "spy_vol_20d": 0.025, "iwm_spy_relative_strength": 0.8,
         "iwm_spy_vol_spread": 0.005, "spy_intraday_range": 0.03},
        {"trade_date": date(2024, 6, 4),
         "spy_ret_1d": 0.01, "tlt_ret_1d": -0.003, "iau_ret_1d": 0.001,
         "vix_close": None, "spy_vol_20d": 0.008, "iwm_spy_relative_strength": 1.1,
         "iwm_spy_vol_spread": -0.002, "spy_intraday_range": 0.01},
    ])


class TestShortSignalMSH1:
    """MSH1: 필수 컬럼 존재 및 타입."""

    def test_output_columns(self, pv_sample, flow_sample, sentiment_sample):
        result = build_short_signal(pv_sample, flow_sample, sentiment_sample)
        for col in SHORT_OUTPUT_COLUMNS:
            assert col in result.columns, f"Missing: {col}"

    def test_output_row_count(self, pv_sample, flow_sample, sentiment_sample):
        result = build_short_signal(pv_sample, flow_sample, sentiment_sample)
        assert len(result) == 2


class TestShortSignalMSH2:
    """MSH2: ENUM 유효성."""

    def test_enum_values_valid(self, pv_sample, flow_sample, sentiment_sample):
        result = build_short_signal(pv_sample, flow_sample, sentiment_sample)
        for val in result["short_signal"]:
            assert val in SHORT_SIGNAL_ENUM, f"Invalid: {val}"

    def test_panic_signal(self, pv_sample, flow_sample, sentiment_sample):
        """급락 + 높은 vol → PANIC."""
        result = build_short_signal(pv_sample, flow_sample, sentiment_sample)
        row = result[result["trade_date"] == date(2024, 6, 3)]
        assert row.iloc[0]["short_signal"] == "PANIC"

    def test_relief_signal(self, pv_sample, flow_sample, sentiment_sample):
        """반등 + 낮은 vol → RELIEF."""
        result = build_short_signal(pv_sample, flow_sample, sentiment_sample)
        row = result[result["trade_date"] == date(2024, 6, 4)]
        assert row.iloc[0]["short_signal"] == "RELIEF"


class TestShortSignalMSH3:
    """MSH3: 결측 시 UNKNOWN."""

    def test_empty_all_inputs(self):
        result = build_short_signal(pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
        assert result.empty

    def test_empty_flow(self, pv_sample, sentiment_sample):
        """flow가 비어도 동작 (UNKNOWN or partial)."""
        result = build_short_signal(pv_sample, pd.DataFrame(), sentiment_sample)
        assert len(result) > 0

    def test_missing_spy(self, flow_sample, sentiment_sample):
        """SPY 없으면 UNKNOWN."""
        pv_no_spy = pd.DataFrame([
            {"symbol": "TLT", "trade_date": date(2024, 6, 3),
             "ret_1d": 0.01, "vol_20d": 0.10, "intraday_range": 0.008},
        ])
        result = build_short_signal(pv_no_spy, flow_sample, sentiment_sample)
        for _, row in result.iterrows():
            assert row["short_signal"] in SHORT_SIGNAL_ENUM


class TestShortSignalMSH4:
    """MSH4: VIX 없이 동작 (v0 제약)."""

    def test_no_vix_column(self, pv_sample, flow_sample, sentiment_sample):
        """VIX 관련 컬럼이 없어도 에러 없이 동작."""
        assert "vix_close" not in pv_sample.columns
        assert "vix_level" not in sentiment_sample.columns
        result = build_short_signal(pv_sample, flow_sample, sentiment_sample)
        assert len(result) > 0
        for val in result["short_signal"]:
            assert val in SHORT_SIGNAL_ENUM


class TestShortSignalMSH5:
    """MSH5: sentiment 통합 — secondary PANIC/RELIEF."""

    def test_flight_to_safety_triggers_secondary_panic(self):
        """ret_1d=-0.008 + vol=0.017(primary 미달) + 3확인 신호 → Secondary PANIC."""
        # Secondary PANIC 조건: ret_1d < -0.005 ✓ + vol > 0.015 ✓ + confirmations >= 3
        # confirmations: vol_spike + flight_to_safety + wide_intraday
        pv = pd.DataFrame([
            {"symbol": "SPY", "trade_date": date(2024, 6, 3),
             "ret_1d": -0.008, "vol_20d": 0.017, "intraday_range": 0.022},
        ])
        flow = pd.DataFrame([
            {"symbol": "SPY", "trade_date": date(2024, 6, 3),
             "volume": 5_000_000, "volume_zscore_20d": 2.5, "asset_group": "INDEX"},
        ])
        sentiment = pd.DataFrame([
            {"trade_date": date(2024, 6, 3),
             "spy_ret_1d": -0.008, "tlt_ret_1d": 0.005, "iau_ret_1d": 0.004,
             "spy_vol_20d": 0.017, "iwm_spy_relative_strength": 0.8,
             "iwm_spy_vol_spread": 0.003, "spy_intraday_range": 0.022},
        ])
        result = build_short_signal(pv, flow, sentiment)
        assert result.iloc[0]["short_signal"] == "PANIC"

    def test_risk_on_confirm_triggers_secondary_relief(self):
        """ret_1d=+0.004 + vol=0.013(primary 미달) + TLT/IAU 동시 하락 → Secondary RELIEF."""
        # Secondary RELIEF 조건: ret > 0.003 ✓ + vol < 0.015 ✓ + risk_on_confirm(tlt/iau <-0.002)
        pv = pd.DataFrame([
            {"symbol": "SPY", "trade_date": date(2024, 6, 3),
             "ret_1d": 0.004, "vol_20d": 0.013, "intraday_range": 0.010},
        ])
        flow = pd.DataFrame([
            {"symbol": "SPY", "trade_date": date(2024, 6, 3),
             "volume": 2_000_000, "volume_zscore_20d": 0.2, "asset_group": "INDEX"},
        ])
        sentiment = pd.DataFrame([
            {"trade_date": date(2024, 6, 3),
             "spy_ret_1d": 0.004, "tlt_ret_1d": -0.003, "iau_ret_1d": -0.003,
             "spy_vol_20d": 0.013, "iwm_spy_relative_strength": 1.1,
             "iwm_spy_vol_spread": -0.002, "spy_intraday_range": 0.010},
        ])
        result = build_short_signal(pv, flow, sentiment)
        assert result.iloc[0]["short_signal"] == "RELIEF"

    def test_primary_conditions_unchanged(self, pv_sample, flow_sample, sentiment_sample):
        """Primary PANIC/RELIEF 조건은 v0와 동일하게 동작."""
        result = build_short_signal(pv_sample, flow_sample, sentiment_sample)
        # 2024-06-03: ret_1d=-0.025 < -0.01 AND vol=0.025 > 0.018 → Primary PANIC
        row_panic = result[result["trade_date"] == date(2024, 6, 3)]
        assert row_panic.iloc[0]["short_signal"] == "PANIC"
        # 2024-06-04: ret_1d=0.01 > 0.005 AND vol=0.008 < 0.012 → Primary RELIEF
        row_relief = result[result["trade_date"] == date(2024, 6, 4)]
        assert row_relief.iloc[0]["short_signal"] == "RELIEF"


class TestShortSignalMSH6:
    """MSH6: flow volume spike 보조 신호."""

    def test_volume_spike_alone_insufficient_for_secondary_panic(self):
        """vol_spike 단독(confirmations=1) → STABLE (임계 미달 2 필요)."""
        # Secondary 조건 진입: ret_1d=-0.007 < -0.005, vol=0.016 > 0.015
        # vol_spike=True(1), wide_intraday=False, flight_to_safety=False → total=1 < 2 → STABLE
        pv = pd.DataFrame([
            {"symbol": "SPY", "trade_date": date(2024, 6, 3),
             "ret_1d": -0.007, "vol_20d": 0.016, "intraday_range": 0.015},
        ])
        flow = pd.DataFrame([
            {"symbol": "SPY", "trade_date": date(2024, 6, 3),
             "volume": 5_000_000, "volume_zscore_20d": 2.5, "asset_group": "INDEX"},
        ])
        sentiment = pd.DataFrame([
            {"trade_date": date(2024, 6, 3),
             "spy_ret_1d": -0.007, "tlt_ret_1d": 0.001, "iau_ret_1d": 0.001,
             "spy_vol_20d": 0.016, "iwm_spy_relative_strength": 0.9,
             "iwm_spy_vol_spread": 0.001, "spy_intraday_range": 0.015},
        ])
        result = build_short_signal(pv, flow, sentiment)
        assert result.iloc[0]["short_signal"] == "STABLE"

    def test_volume_spike_plus_wide_intraday_triggers_secondary_panic(self):
        """vol_spike + wide_intraday + vix_extreme(confirmations=3) → Secondary PANIC."""
        # Secondary 조건: ret=-0.007 < -0.005, vol=0.016 > 0.015
        # vol_spike + wide_intraday + vix_extreme → total=3 → PANIC
        pv = pd.DataFrame([
            {"symbol": "SPY", "trade_date": date(2024, 6, 3),
             "ret_1d": -0.007, "vol_20d": 0.016, "intraday_range": 0.022},
        ])
        flow = pd.DataFrame([
            {"symbol": "SPY", "trade_date": date(2024, 6, 3),
             "volume": 5_000_000, "volume_zscore_20d": 2.5, "asset_group": "INDEX"},
        ])
        sentiment = pd.DataFrame([
            {"trade_date": date(2024, 6, 3),
             "spy_ret_1d": -0.007, "tlt_ret_1d": 0.001, "iau_ret_1d": 0.001,
             "vix_close": 36.0,
             "spy_vol_20d": 0.016, "iwm_spy_relative_strength": 0.9,
             "iwm_spy_vol_spread": 0.001, "spy_intraday_range": 0.022},
        ])
        result = build_short_signal(pv, flow, sentiment)
        assert result.iloc[0]["short_signal"] == "PANIC"

    def test_secondary_panic_requires_both_ret_and_vol_in_range(self):
        """ret_1d가 -0.005 이상이면 secondary 조건 진입 불가 → STABLE."""
        # ret_1d=-0.003 > _SECONDARY_PANIC_RET(-0.005) → secondary 미진입
        pv = pd.DataFrame([
            {"symbol": "SPY", "trade_date": date(2024, 6, 3),
             "ret_1d": -0.003, "vol_20d": 0.016, "intraday_range": 0.022},
        ])
        flow = pd.DataFrame([
            {"symbol": "SPY", "trade_date": date(2024, 6, 3),
             "volume": 5_000_000, "volume_zscore_20d": 2.5, "asset_group": "INDEX"},
        ])
        sentiment = pd.DataFrame([
            {"trade_date": date(2024, 6, 3),
             "spy_ret_1d": -0.003, "tlt_ret_1d": 0.005, "iau_ret_1d": 0.004,
             "spy_vol_20d": 0.016, "iwm_spy_relative_strength": 0.8,
             "iwm_spy_vol_spread": 0.003, "spy_intraday_range": 0.022},
        ])
        result = build_short_signal(pv, flow, sentiment)
        assert result.iloc[0]["short_signal"] == "STABLE"


class TestShortSignalMSH7:
    """MSH7: smallcap_stress (IWM vol spread) — v1.1 신규 4번째 secondary PANIC 신호.

    iwm_spy_vol_spread = IWM vol_20d - SPY vol_20d > 0.005 → 소형주 변동성 스트레스.
    """

    def test_smallcap_stress_plus_vol_spike_triggers_secondary_panic(self):
        """vol_spike + smallcap_stress + vix_extreme → Secondary PANIC.

        flight_to_safety=False(tlt/iau 모두 임계 미달), wide_intraday=False.
        """
        pv = pd.DataFrame([{
            "symbol": "SPY", "trade_date": date(2024, 6, 3),
            "ret_1d": -0.007, "vol_20d": 0.016, "intraday_range": 0.012,
        }])
        flow = pd.DataFrame([{
            "symbol": "SPY", "trade_date": date(2024, 6, 3),
            "volume": 5_000_000, "volume_zscore_20d": 2.5, "asset_group": "INDEX",
        }])
        sentiment = pd.DataFrame([{
            "trade_date": date(2024, 6, 3),
            "spy_ret_1d": -0.007, "tlt_ret_1d": 0.001, "iau_ret_1d": 0.001,
            "vix_close": 36.0,
            "spy_vol_20d": 0.016, "iwm_spy_relative_strength": 0.9,
            "iwm_spy_vol_spread": 0.008,   # > 0.005 → smallcap_stress=True
            "spy_intraday_range": 0.012,
        }])
        result = build_short_signal(pv, flow, sentiment)
        # ret=-0.007<-0.005, vol=0.016>0.015 → secondary 진입
        # vol_spike(2.5>2.0)=1, wide_intraday(0.012<0.020)=0
        # flight_to_safety(tlt=0.001<0.003)=0, smallcap_stress(0.008>0.005)=1, vix_extreme=1 → total=3 → PANIC
        assert result.iloc[0]["short_signal"] == "PANIC"

    def test_smallcap_stress_below_threshold_stays_stable(self):
        """iwm_spy_vol_spread=0.003 < 0.005 → smallcap_stress=False → confirmations=1 → STABLE."""
        pv = pd.DataFrame([{
            "symbol": "SPY", "trade_date": date(2024, 6, 3),
            "ret_1d": -0.007, "vol_20d": 0.016, "intraday_range": 0.012,
        }])
        flow = pd.DataFrame([{
            "symbol": "SPY", "trade_date": date(2024, 6, 3),
            "volume": 5_000_000, "volume_zscore_20d": 2.5, "asset_group": "INDEX",
        }])
        sentiment = pd.DataFrame([{
            "trade_date": date(2024, 6, 3),
            "spy_ret_1d": -0.007, "tlt_ret_1d": 0.001, "iau_ret_1d": 0.001,
            "spy_vol_20d": 0.016, "iwm_spy_relative_strength": 0.9,
            "iwm_spy_vol_spread": 0.003,   # < 0.005 → smallcap_stress=False
            "spy_intraday_range": 0.012,
        }])
        result = build_short_signal(pv, flow, sentiment)
        # vol_spike(2.5>2.0)=1, smallcap_stress(0.003<0.005)=0 → total=1 < 2 → STABLE
        assert result.iloc[0]["short_signal"] == "STABLE"


class TestShortSignalDetail:
    """short detail JSON 출력 검증."""

    def test_detail_contains_confirmation_fields(self, pv_sample, flow_sample, sentiment_sample):
        result = build_short_signal(pv_sample, flow_sample, sentiment_sample)
        detail = json.loads(result.iloc[0]["short_detail_json"])
        assert "secondary_confirm_count" in detail
        assert "secondary_confirmations" in detail
        assert "smallcap_stress" in detail
        assert "vix_extreme" in detail
        assert "skew_extreme" in detail
        assert "vix_close" in detail


class TestShortSignalVIXV12:
    """v1.2: vix_extreme 5번째 secondary PANIC 보조 신호."""

    def test_vix_none_preserves_v11_behavior(self):
        pv = pd.DataFrame([{
            "symbol": "SPY", "trade_date": date(2024, 6, 3),
            "ret_1d": -0.007, "vol_20d": 0.016, "intraday_range": 0.012,
        }])
        flow = pd.DataFrame([{
            "symbol": "SPY", "trade_date": date(2024, 6, 3),
            "volume": 5_000_000, "volume_zscore_20d": 2.5, "asset_group": "INDEX",
        }])
        sentiment = pd.DataFrame([{
            "trade_date": date(2024, 6, 3),
            "spy_ret_1d": -0.007, "tlt_ret_1d": 0.001, "iau_ret_1d": 0.001,
            "vix_close": None,
            "spy_vol_20d": 0.016, "iwm_spy_relative_strength": 0.9,
            "iwm_spy_vol_spread": 0.003, "spy_intraday_range": 0.012,
        }])
        result = build_short_signal(pv, flow, sentiment)
        assert result.iloc[0]["short_signal"] == "STABLE"

    def test_vix_extreme_plus_vol_spike_and_flight_to_safety_triggers_secondary_panic(self):
        pv = pd.DataFrame([{
            "symbol": "SPY", "trade_date": date(2024, 6, 3),
            "ret_1d": -0.007, "vol_20d": 0.016, "intraday_range": 0.012,
        }])
        flow = pd.DataFrame([{
            "symbol": "SPY", "trade_date": date(2024, 6, 3),
            "volume": 5_000_000, "volume_zscore_20d": 2.5, "asset_group": "INDEX",
        }])
        sentiment = pd.DataFrame([{
            "trade_date": date(2024, 6, 3),
            "spy_ret_1d": -0.007, "tlt_ret_1d": 0.004, "iau_ret_1d": 0.004,
            "vix_close": 36.0,
            "spy_vol_20d": 0.016, "iwm_spy_relative_strength": 0.9,
            "iwm_spy_vol_spread": 0.003, "spy_intraday_range": 0.012,
        }])
        result = build_short_signal(pv, flow, sentiment)
        assert result.iloc[0]["short_signal"] == "PANIC"
        detail = json.loads(result.iloc[0]["short_detail_json"])
        assert detail["vix_extreme"] is True
        assert detail["secondary_confirm_count"] == 3

    def test_vix_extreme_alone_is_insufficient(self):
        pv = pd.DataFrame([{
            "symbol": "SPY", "trade_date": date(2024, 6, 3),
            "ret_1d": -0.007, "vol_20d": 0.016, "intraday_range": 0.012,
        }])
        flow = pd.DataFrame([{
            "symbol": "SPY", "trade_date": date(2024, 6, 3),
            "volume": 1_000_000, "volume_zscore_20d": 0.5, "asset_group": "INDEX",
        }])
        sentiment = pd.DataFrame([{
            "trade_date": date(2024, 6, 3),
            "spy_ret_1d": -0.007, "tlt_ret_1d": 0.001, "iau_ret_1d": 0.001,
            "vix_close": 36.0,
            "spy_vol_20d": 0.016, "iwm_spy_relative_strength": 0.9,
            "iwm_spy_vol_spread": 0.003, "spy_intraday_range": 0.012,
        }])
        result = build_short_signal(pv, flow, sentiment)
        assert result.iloc[0]["short_signal"] == "STABLE"

    def test_vix_threshold_boundary(self):
        pv = pd.DataFrame([{
            "symbol": "SPY", "trade_date": date(2024, 6, 3),
            "ret_1d": -0.007, "vol_20d": 0.016, "intraday_range": 0.012,
        }])
        flow = pd.DataFrame([{
            "symbol": "SPY", "trade_date": date(2024, 6, 3),
            "volume": 5_000_000, "volume_zscore_20d": 2.5, "asset_group": "INDEX",
        }])
        sentiment = pd.DataFrame([{
            "trade_date": date(2024, 6, 3),
            "spy_ret_1d": -0.007, "tlt_ret_1d": 0.001, "iau_ret_1d": 0.001,
            "vix_close": 35.0,
            "spy_vol_20d": 0.016, "iwm_spy_relative_strength": 0.9,
            "iwm_spy_vol_spread": 0.003, "spy_intraday_range": 0.012,
        }])
        result = build_short_signal(pv, flow, sentiment)
        detail = json.loads(result.iloc[0]["short_detail_json"])
        assert detail["vix_extreme"] is False


class TestShortSignalSkewV13:
    """v1.3: skew_extreme 추가 및 6신호 중 3개 이상 threshold."""

    def test_skew_fail_open_returns_zero(self):
        assert _load_skew_extreme(date(1900, 1, 1)) == 0

    def test_skew_extreme_third_confirmation_triggers_secondary_panic(self, tmp_path, monkeypatch):
        pv = pd.DataFrame([{
            "symbol": "SPY", "trade_date": date(2024, 6, 3),
            "ret_1d": -0.007, "vol_20d": 0.016, "intraday_range": 0.012,
        }])
        flow = pd.DataFrame([{
            "symbol": "SPY", "trade_date": date(2024, 6, 3),
            "volume": 5_000_000, "volume_zscore_20d": 2.5, "asset_group": "INDEX",
        }])
        sentiment = pd.DataFrame([{
            "trade_date": date(2024, 6, 3),
            "spy_ret_1d": -0.007, "tlt_ret_1d": 0.004, "iau_ret_1d": 0.004,
            "vix_close": None,
            "spy_vol_20d": 0.016, "iwm_spy_relative_strength": 0.9,
            "iwm_spy_vol_spread": 0.003, "spy_intraday_range": 0.012,
        }])

        result = build_short_signal(pv, flow, sentiment)
        assert result.iloc[0]["short_signal"] == "STABLE"

        skew_root = tmp_path / "skew"
        monkeypatch.setattr(
            "pretrend.observability.regime.horizon.short_engine._DEFAULT_SKEW_GOLD_ROOT",
            str(skew_root),
        )
        skew_path = skew_root / "date=2024-06-03"
        skew_path.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([{
            "trade_date": date(2024, 6, 3),
            "skew_close": 150.0,
            "skew_zscore_252": 2.5,
            "skew_extreme_flag": 1,
            "run_id": "test",
            "ingestion_ts": pd.Timestamp("2026-03-12T00:00:00Z"),
        }]).to_parquet(skew_path / "skew_20240603.parquet", index=False)
        _load_skew_extreme.cache_clear()

        result = build_short_signal(pv, flow, sentiment)
        assert result.iloc[0]["short_signal"] == "PANIC"
        detail = json.loads(result.iloc[0]["short_detail_json"])
        assert detail["secondary_confirm_count"] == 3
        assert detail["skew_extreme"] is True

    def test_vix_and_vol_spike_only_stays_stable_under_v13_threshold(self, tmp_path, monkeypatch):
        pv = pd.DataFrame([{
            "symbol": "SPY", "trade_date": date(2024, 6, 4),
            "ret_1d": -0.007, "vol_20d": 0.016, "intraday_range": 0.012,
        }])
        flow = pd.DataFrame([{
            "symbol": "SPY", "trade_date": date(2024, 6, 4),
            "volume": 5_000_000, "volume_zscore_20d": 2.5, "asset_group": "INDEX",
        }])
        sentiment = pd.DataFrame([{
            "trade_date": date(2024, 6, 4),
            "spy_ret_1d": -0.007, "tlt_ret_1d": 0.001, "iau_ret_1d": 0.001,
            "vix_close": 36.0,
            "spy_vol_20d": 0.016, "iwm_spy_relative_strength": 0.9,
            "iwm_spy_vol_spread": 0.003, "spy_intraday_range": 0.012,
        }])
        monkeypatch.setattr(
            "pretrend.observability.regime.horizon.short_engine._DEFAULT_SKEW_GOLD_ROOT",
            str(tmp_path / "missing_skew"),
        )
        _load_skew_extreme.cache_clear()
        result = build_short_signal(pv, flow, sentiment)
        assert result.iloc[0]["short_signal"] == "STABLE"
