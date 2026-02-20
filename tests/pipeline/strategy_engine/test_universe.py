"""
Universe Selector 계약 테스트.

Contract: docs/architecture/universe_contract.md
DoD:
  UV1: run_universe=false → 0 rows
  UV2: 필수 컬럼/타입, CORE 항상 is_candidate=True
  UV3: asset_group ENUM 위반 금지
  UV4: Phase eligible pool — 제외 종목 is_candidate=False
  UV5: mid_regime Top-N — TACTICAL 후보 수 제한
  UV6: relative_strength = ret_20d - ret_20d(SPY)
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from pretrend.pipeline.strategy_engine.registries import CORE_HOLD_REGISTRY
from pretrend.pipeline.strategy_engine.universe.engine import build_universe
from pretrend.pipeline.strategy_engine.universe.schema import (
    ASSET_GROUP_ENUM,
    UNIVERSE_OUTPUT_COLUMNS,
)


# ── 공통 픽스처 ───────────────────────────────────────────────

def _make_ps(
    long_phase: str = "EXPANSION",
    mid_regime: str = "RISK_ON",
    run_universe: bool = True,
) -> pd.DataFrame:
    return pd.DataFrame({
        "trade_date":           [date(2024, 6, 3)],
        "run_universe":         [run_universe],
        "risk_gate":            [False],
        "long_phase":           [long_phase],
        "mid_regime":           [mid_regime],
        "short_signal":         ["NEUTRAL"],
        "policy_profile_id":    ["RC_V0_DEFAULT"],
        "target_invested_lower":[0.3],
        "target_invested_upper":[0.6],
        "adjustment_limit":     [0.1],
        "step_size":            [0.05],
        "policy_version":       ["v0"],
        "notes":                [[]],
        "source_run_id":        ["run1"],
    })


def _make_eod(symbols_ret: dict[str, tuple[str, float]]) -> pd.DataFrame:
    """symbol → (asset_group, ret_20d) 매핑으로 gold_eod 픽스처 생성."""
    rows = []
    for sym, (ag, ret) in symbols_ret.items():
        rows.append({
            "symbol": sym,
            "trade_date": date(2024, 6, 3),
            "asset_group": ag,
            "asset_name": sym,
            "ret_20d": ret,
            "vol_20d": 0.15,
        })
    return pd.DataFrame(rows)


@pytest.fixture
def gold_eod_basic() -> pd.DataFrame:
    """CORE 3개 + TACTICAL 1개 (XLV)."""
    return _make_eod({
        "SPY": ("INDEX",     0.05),
        "TLT": ("BOND",     -0.02),
        "IAU": ("COMMODITY", 0.03),
        "XLV": ("SECTOR",    0.04),
    })


@pytest.fixture
def gold_eod_with_excluded() -> pd.DataFrame:
    """RECESSION 제외 대상(USO, UNG) + 허용 종목 혼합."""
    return _make_eod({
        "SPY": ("INDEX",     0.03),
        "TLT": ("BOND",      0.01),
        "IAU": ("COMMODITY", 0.02),
        "XLV": ("SECTOR",    0.04),
        "XLU": ("SECTOR",    0.03),
        "USO": ("COMMODITY",-0.01),
        "UNG": ("COMMODITY",-0.02),
    })


@pytest.fixture
def gold_eod_many_tactical() -> pd.DataFrame:
    """TACTICAL 10개 (Top-N 제한 검증용). SPY ret=0.02 기준."""
    return _make_eod({
        "SPY":  ("INDEX",     0.020),
        "TLT":  ("BOND",      0.010),
        "IAU":  ("COMMODITY", 0.015),
        "XLK":  ("SECTOR",    0.090),
        "XLV":  ("SECTOR",    0.080),
        "XLF":  ("SECTOR",    0.070),
        "XLE":  ("SECTOR",    0.060),
        "XLU":  ("SECTOR",    0.050),
        "XLRE": ("SECTOR",    0.040),
        "EWJ":  ("COUNTRY",   0.035),
        "EWY":  ("COUNTRY",   0.030),
        "SLV":  ("COMMODITY", 0.025),
        "DBA":  ("COMMODITY", 0.020),
    })


# ── UV1: run_universe=false → 0 rows ─────────────────────────

class TestUniverseUV1:
    def test_zero_rows_when_run_false(self, gold_eod_basic):
        ps = _make_ps(run_universe=False)
        result = build_universe(ps, gold_eod_basic)
        assert len(result) == 0


# ── UV2: 컬럼/타입, CORE 항상 is_candidate=True ───────────────

class TestUniverseUV2:
    def test_output_columns_present(self, gold_eod_basic):
        ps = _make_ps()
        result = build_universe(ps, gold_eod_basic)
        for col in UNIVERSE_OUTPUT_COLUMNS:
            assert col in result.columns, f"Missing column: {col}"

    def test_has_rows(self, gold_eod_basic):
        ps = _make_ps()
        result = build_universe(ps, gold_eod_basic)
        assert len(result) > 0

    def test_empty_input(self):
        result = build_universe(pd.DataFrame(), pd.DataFrame())
        assert result.empty

    def test_core_always_is_candidate(self, gold_eod_basic):
        """CORE(SPY, TLT, IAU)는 phase·Top-N 무관하게 항상 is_candidate=True."""
        ps = _make_ps(long_phase="RECOVERY", mid_regime="RISK_OFF")
        result = build_universe(ps, gold_eod_basic)
        for sym in CORE_HOLD_REGISTRY:
            rows = result[result["symbol"] == sym]
            if not rows.empty:
                assert rows["is_candidate"].all(), f"CORE {sym} must be candidate"


# ── UV3: asset_group ENUM 위반 금지 ───────────────────────────

class TestUniverseUV3:
    def test_asset_group_enum(self, gold_eod_basic):
        ps = _make_ps()
        result = build_universe(ps, gold_eod_basic)
        for val in result["asset_group"]:
            assert val in ASSET_GROUP_ENUM, f"Invalid asset_group: {val}"


# ── UV4: Phase eligible pool — 제외 종목 ─────────────────────

class TestUniverseUV4:
    def test_recession_excludes_uso_ung(self, gold_eod_with_excluded):
        """RECESSION: USO·UNG는 is_candidate=False."""
        ps = _make_ps(long_phase="RECESSION", mid_regime="RISK_ON")
        result = build_universe(ps, gold_eod_with_excluded)
        for sym in ("USO", "UNG"):
            rows = result[result["symbol"] == sym]
            if not rows.empty:
                assert not rows["is_candidate"].any(), f"{sym} should not be candidate in RECESSION"

    def test_recovery_excludes_xle(self, gold_eod_many_tactical):
        """RECOVERY: XLE는 is_candidate=False."""
        ps = _make_ps(long_phase="RECOVERY", mid_regime="RISK_ON")
        result = build_universe(ps, gold_eod_many_tactical)
        rows = result[result["symbol"] == "XLE"]
        if not rows.empty:
            assert not rows["is_candidate"].any(), "XLE should not be candidate in RECOVERY"

    def test_late_cycle_allows_all(self, gold_eod_with_excluded):
        """LATE_CYCLE: 제외 종목 없음 (live RS에 위임)."""
        ps = _make_ps(long_phase="LATE_CYCLE", mid_regime="RISK_ON")
        result = build_universe(ps, gold_eod_with_excluded)
        # Top-N=9이고 TACTICAL이 USO, UNG, XLV, XLU 4개뿐 → 전부 is_candidate
        tactical_rows = result[~result["symbol"].isin(CORE_HOLD_REGISTRY)]
        assert tactical_rows["is_candidate"].all()

    def test_unknown_phase_failopen(self, gold_eod_with_excluded):
        """UNKNOWN phase: 제외 없음 (fail-open)."""
        ps = _make_ps(long_phase="UNKNOWN", mid_regime="NEUTRAL")
        result = build_universe(ps, gold_eod_with_excluded)
        assert len(result) > 0


# ── UV5: mid_regime Top-N ─────────────────────────────────────

class TestUniverseUV5:
    def test_risk_off_top5_tactical(self, gold_eod_many_tactical):
        """RISK_OFF → TACTICAL is_candidate 수 ≤ 5."""
        ps = _make_ps(long_phase="EXPANSION", mid_regime="RISK_OFF")
        result = build_universe(ps, gold_eod_many_tactical)
        tactical = result[~result["symbol"].isin(CORE_HOLD_REGISTRY)]
        candidate_count = tactical["is_candidate"].sum()
        assert candidate_count <= 5, f"Expected ≤5, got {candidate_count}"

    def test_risk_on_top9_tactical(self, gold_eod_many_tactical):
        """RISK_ON → TACTICAL is_candidate 수 ≤ 9."""
        ps = _make_ps(long_phase="EXPANSION", mid_regime="RISK_ON")
        result = build_universe(ps, gold_eod_many_tactical)
        tactical = result[~result["symbol"].isin(CORE_HOLD_REGISTRY)]
        candidate_count = tactical["is_candidate"].sum()
        assert candidate_count <= 9, f"Expected ≤9, got {candidate_count}"

    def test_risk_off_fewer_than_risk_on(self, gold_eod_many_tactical):
        """RISK_OFF가 RISK_ON보다 후보 수가 적거나 같다."""
        ps_off = _make_ps(long_phase="EXPANSION", mid_regime="RISK_OFF")
        ps_on  = _make_ps(long_phase="EXPANSION", mid_regime="RISK_ON")
        r_off = build_universe(ps_off, gold_eod_many_tactical)
        r_on  = build_universe(ps_on,  gold_eod_many_tactical)
        n_off = r_off[~r_off["symbol"].isin(CORE_HOLD_REGISTRY)]["is_candidate"].sum()
        n_on  = r_on[~r_on["symbol"].isin(CORE_HOLD_REGISTRY)]["is_candidate"].sum()
        assert n_off <= n_on


# ── UV6: relative_strength = ret_20d - ret_20d(SPY) ──────────

class TestUniverseUV6:
    def test_rs_is_relative_to_spy(self, gold_eod_basic):
        """relative_strength = 해당 종목 ret_20d - SPY ret_20d."""
        ps = _make_ps()
        result = build_universe(ps, gold_eod_basic)
        spy_ret = 0.05  # gold_eod_basic에서 SPY ret_20d
        # XLV ret_20d=0.04 → rs = 0.04 - 0.05 = -0.01
        xlv_rs = result.loc[result["symbol"] == "XLV", "relative_strength"].iloc[0]
        assert abs(xlv_rs - (-0.01)) < 1e-9, f"Expected -0.01, got {xlv_rs}"

    def test_spy_rs_is_zero(self, gold_eod_basic):
        """SPY의 relative_strength = 0 (자기 자신 대비)."""
        ps = _make_ps()
        result = build_universe(ps, gold_eod_basic)
        spy_rs = result.loc[result["symbol"] == "SPY", "relative_strength"].iloc[0]
        assert abs(spy_rs) < 1e-9, f"SPY RS should be ~0, got {spy_rs}"
