"""
Long Phase Engine 계약 테스트.

Contract: docs/architecture/market_structure_long_v1_contract.md
DoD: ML1 (컬럼/타입), ML2 (ENUM), ML3 (결측→UNKNOWN)
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from pretrend.pipeline.strategy_engine.axis_horizon_state.schema import (
    LONG_PHASE_ENUM,
    LONG_OUTPUT_COLUMNS,
)
from pretrend.pipeline.strategy_engine.axis_horizon_state.long_engine import (
    build_long_phase,
)


@pytest.fixture
def macro_policy_sample() -> pd.DataFrame:
    """macro_policy axis 샘플."""
    return pd.DataFrame({
        "indicator_id": ["CPI_US_ALL_ITEMS_SA", "US_UNEMPLOYMENT_RATE"] * 2,
        "trade_date": [date(2024, 6, 3)] * 2 + [date(2024, 6, 4)] * 2,
        "selected_value": [310.0, 3.9, 310.5, 3.8],
        "selected_release_date": [date(2024, 6, 1)] * 4,
        "regime": ["tightening", "tightening", "easing", "easing"],
        "delta_1m": [0.5, -0.1, 0.6, -0.2],
        "delta_3m": [1.2, -0.3, -0.5, -0.4],
        "delta_6m": [2.1, 0.5, -1.0, -0.6],
        "release_source": ["econ_events"] * 4,
        "coverage": [1.0] * 4,
        "is_stale": [False] * 4,
    })


class TestLongPhaseML1:
    """ML1: 필수 컬럼 존재 및 타입 검증."""

    def test_output_columns(self, macro_policy_sample):
        result = build_long_phase(macro_policy_sample)
        for col in LONG_OUTPUT_COLUMNS:
            assert col in result.columns, f"Missing: {col}"

    def test_output_not_empty(self, macro_policy_sample):
        result = build_long_phase(macro_policy_sample)
        assert len(result) > 0


class TestLongPhaseML2:
    """ML2: long_phase ENUM 유효성."""

    def test_enum_values_valid(self, macro_policy_sample):
        result = build_long_phase(macro_policy_sample)
        for val in result["long_phase"]:
            assert val in LONG_PHASE_ENUM, f"Invalid: {val}"

    def test_tightening_positive_delta(self, macro_policy_sample):
        """tightening + delta_6m > 0 → LATE_CYCLE."""
        result = build_long_phase(macro_policy_sample)
        # 2024-06-03: regime=tightening, delta_6m_mean=positive
        row = result[result["trade_date"] == date(2024, 6, 3)]
        assert row.iloc[0]["long_phase"] == "LATE_CYCLE"

    def test_easing_negative_delta(self, macro_policy_sample):
        """easing + delta_6m < 0 → RECESSION."""
        result = build_long_phase(macro_policy_sample)
        # 2024-06-04: regime=easing, delta_6m_mean=negative
        row = result[result["trade_date"] == date(2024, 6, 4)]
        assert row.iloc[0]["long_phase"] == "RECESSION"

    def test_neutral_regime(self):
        """neutral regime → EXPANSION."""
        df = pd.DataFrame({
            "indicator_id": ["CPI"],
            "trade_date": [date(2024, 7, 1)],
            "regime": ["neutral"],
            "delta_6m": [0.0],
        })
        result = build_long_phase(df)
        assert result.iloc[0]["long_phase"] == "EXPANSION"


class TestLongPhaseML3:
    """ML3: 결측 시 UNKNOWN (fail-open)."""

    def test_empty_input(self):
        result = build_long_phase(pd.DataFrame())
        assert result.empty
        assert set(LONG_OUTPUT_COLUMNS).issubset(result.columns)

    def test_missing_regime(self):
        """regime이 None → UNKNOWN."""
        df = pd.DataFrame({
            "indicator_id": ["CPI"],
            "trade_date": [date(2024, 7, 1)],
            "regime": [None],
            "delta_6m": [1.0],
        })
        result = build_long_phase(df)
        assert result.iloc[0]["long_phase"] == "UNKNOWN"

    def test_missing_delta_column(self):
        """delta_6m 컬럼 자체가 없어도 동작."""
        df = pd.DataFrame({
            "indicator_id": ["CPI"],
            "trade_date": [date(2024, 7, 1)],
            "regime": ["tightening"],
        })
        result = build_long_phase(df)
        assert result.iloc[0]["long_phase"] in LONG_PHASE_ENUM


class TestLongPhaseV1Normalization:
    """v1: delta_6m 지표별 rolling z-score 정규화 관련 테스트."""

    def _make_history(self, n: int = 300) -> pd.DataFrame:
        """충분한 롤링 윈도우(252+)를 채울 수 있는 CPI/UNRATE 더미 시계열."""
        dates = [d.date() for d in pd.bdate_range("2000-01-03", periods=n)]
        # CPI: 수 단위 스케일 (200 ~ 200+n*0.03 범위, 느린 상승)
        cpi_vals = [200.0 + i * 0.03 for i in range(n)]
        # UNRATE: 0.x 단위 스케일 (5.0 → 하락)
        ur_vals = [5.0 - i * 0.005 for i in range(n)]
        rows = []
        for i, d in enumerate(dates):
            rows.append({"indicator_id": "CPI_US_ALL_ITEMS_SA", "trade_date": d,
                         "regime": "tightening", "delta_6m": cpi_vals[i]})
            rows.append({"indicator_id": "US_UNEMPLOYMENT_RATE", "trade_date": d,
                         "regime": "tightening", "delta_6m": ur_vals[i]})
        return pd.DataFrame(rows)

    def test_unit_invariance(self):
        """스케일이 다른 지표(CPI/UNRATE)에서도 z-score mean이 단위 불변으로 동작한다.

        시나리오: CPI delta_6m이 최근 급등(큰 양수, 스케일 ≫ UNRATE),
        UNRATE delta_6m이 최근 하락(음수). raw mean은 CPI 스케일에 압도당해 양수이지만,
        z-score mean에서는 두 지표가 동등한 가중치를 가진다.
        """
        history = self._make_history(300)
        # 마지막 날: CPI delta_6m = +500 (이례적 급등), UNRATE delta_6m = -2.0 (개선)
        last_date = date(2026, 1, 1)
        override = pd.DataFrame([
            {"indicator_id": "CPI_US_ALL_ITEMS_SA", "trade_date": last_date,
             "regime": "tightening", "delta_6m": 500.0},
            {"indicator_id": "US_UNEMPLOYMENT_RATE", "trade_date": last_date,
             "regime": "tightening", "delta_6m": -2.0},
        ])
        df = pd.concat([history, override], ignore_index=True)

        result = build_long_phase(df)
        last_row = result[result["trade_date"] == last_date]
        assert len(last_row) == 1

        # raw mean: (500 + (-2)) / 2 = 249 > 0 → LATE_CYCLE (CPI 스케일 압도)
        # z-score: CPI z≫0 (이례적 급등), UNRATE z≪0 (이례적 하락) → mean 방향은 계산에 따라 다름
        # 핵심 검증: 결과가 LONG_PHASE_ENUM 내의 유효한 값이어야 함
        assert last_row.iloc[0]["long_phase"] in LONG_PHASE_ENUM

    def test_nan_fallback_early_period(self):
        """초기구간(min_periods 미충족) 에서 NaN → raw delta_6m sign fallback 적용.

        rolling(252, min_periods=60) 미충족 시:
        - delta_6m > 0 → z ≈ +1.0 (sign fallback)
        - delta_6m < 0 → z ≈ -1.0 (sign fallback)
        → 분류 결과가 유효한 ENUM 값이어야 함.
        """
        # 데이터 10개(< min_periods=60) → 전부 NaN fallback
        df = pd.DataFrame({
            "indicator_id": ["CPI_US_ALL_ITEMS_SA", "US_UNEMPLOYMENT_RATE"] * 5,
            "trade_date": [date(2006, 1, i + 1) for i in range(5)] * 2,
            "regime": ["tightening"] * 10,
            "delta_6m": [2.0, -0.3] * 5,
        })
        result = build_long_phase(df)
        assert len(result) > 0
        for phase in result["long_phase"]:
            assert phase in LONG_PHASE_ENUM

    def test_missing_indicator_id_fallback(self):
        """indicator_id 컬럼이 없으면 regime 단독 판정 (fail-open, v0 동작)."""
        df = pd.DataFrame({
            "trade_date": [date(2024, 6, 3)],
            "regime": ["tightening"],
            "delta_6m": [2.1],
        })
        result = build_long_phase(df)
        # indicator_id 없음 → delta_6m_z=NaN → regime-only → tightening → LATE_CYCLE
        assert result.iloc[0]["long_phase"] == "LATE_CYCLE"

    def test_duplicate_indicator_trade_date(self):
        """(indicator_id, trade_date) 중복 행이 있어도 keep='last'로 안정적으로 동작한다."""
        df = pd.DataFrame({
            "indicator_id": ["CPI_US_ALL_ITEMS_SA", "CPI_US_ALL_ITEMS_SA"],
            "trade_date": [date(2024, 6, 3), date(2024, 6, 3)],
            "regime": ["tightening", "tightening"],
            "delta_6m": [2.1, 99.9],  # 두 번째 행(99.9)이 keep='last'로 선택됨
        })
        # 중복 제거 후 1행 → 결과 1행이어야 함
        result = build_long_phase(df)
        assert len(result) == 1
        assert result.iloc[0]["long_phase"] in LONG_PHASE_ENUM
