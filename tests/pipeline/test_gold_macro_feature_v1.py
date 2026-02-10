"""
Gold Macro Feature v1 — Tests MF1–MF10.

All tests use synthetic fixtures (no external API calls, no real data files).
Contract reference: docs/architecture/gold_design_contract.md §10
"""

from datetime import date, timedelta
from typing import List

import pandas as pd
import pytest

from pretrend.pipeline.features.gold_macro_features import build_gold_macro_features


# ── Schema Constants ────────────────────────────────────────

GOLD_MACRO_FEATURE_COLUMNS = [
    "indicator_id",
    "trade_date",
    "selected_observation_date",
    "selected_value",
    "selected_release_date",
    "delta_1m",
    "delta_3m",
    "delta_6m",
    "direction",
    "regime",
    "zscore_12m",
    "release_source",
    "is_assumption_based",
]

VALID_DIRECTIONS = {"up", "down", "flat"}
VALID_REGIMES = {"tightening", "easing", "neutral"}


# ── Shared Fixtures ─────────────────────────────────────────


def _build_macro_silver() -> pd.DataFrame:
    """Synthetic Silver macro: 7 monthly CPI + 25 daily DGS10."""
    cpi_rows = [
        {"indicator_id": "CPI_US_ALL_ITEMS_SA", "date": date(2024, 1, 1), "value": 300.0},
        {"indicator_id": "CPI_US_ALL_ITEMS_SA", "date": date(2024, 2, 1), "value": 301.0},
        {"indicator_id": "CPI_US_ALL_ITEMS_SA", "date": date(2024, 3, 1), "value": 302.5},
        {"indicator_id": "CPI_US_ALL_ITEMS_SA", "date": date(2024, 4, 1), "value": 303.0},
        {"indicator_id": "CPI_US_ALL_ITEMS_SA", "date": date(2024, 5, 1), "value": 304.0},
        {"indicator_id": "CPI_US_ALL_ITEMS_SA", "date": date(2024, 6, 1), "value": 305.5},
        {"indicator_id": "CPI_US_ALL_ITEMS_SA", "date": date(2024, 7, 1), "value": 306.0},
    ]
    dgs_dates = pd.bdate_range("2024-06-03", periods=25).date.tolist()
    dgs_rows = [
        {
            "indicator_id": "US_TREASURY_10Y_YIELD",
            "date": d,
            "value": round(4.50 - i * 0.01, 2),
        }
        for i, d in enumerate(dgs_dates)
    ]
    return pd.DataFrame(cpi_rows + dgs_rows)


def _build_calendar() -> pd.DataFrame:
    """Synthetic Calendar evidence aligned with _build_macro_silver()."""
    cal_cpi = [
        {"indicator_id": "CPI_US_ALL_ITEMS_SA", "observation_date": date(2024, 1, 1),
         "release_date": date(2024, 2, 13), "release_source": "econ_events",
         "is_assumption_based": False},
        {"indicator_id": "CPI_US_ALL_ITEMS_SA", "observation_date": date(2024, 2, 1),
         "release_date": date(2024, 3, 12), "release_source": "econ_events",
         "is_assumption_based": False},
        {"indicator_id": "CPI_US_ALL_ITEMS_SA", "observation_date": date(2024, 3, 1),
         "release_date": date(2024, 4, 10), "release_source": "econ_events",
         "is_assumption_based": False},
        {"indicator_id": "CPI_US_ALL_ITEMS_SA", "observation_date": date(2024, 4, 1),
         "release_date": date(2024, 5, 15), "release_source": "econ_events",
         "is_assumption_based": False},
        {"indicator_id": "CPI_US_ALL_ITEMS_SA", "observation_date": date(2024, 5, 1),
         "release_date": date(2024, 6, 12), "release_source": "econ_events",
         "is_assumption_based": False},
        {"indicator_id": "CPI_US_ALL_ITEMS_SA", "observation_date": date(2024, 6, 1),
         "release_date": date(2024, 7, 11), "release_source": "econ_events",
         "is_assumption_based": False},
        {"indicator_id": "CPI_US_ALL_ITEMS_SA", "observation_date": date(2024, 7, 1),
         "release_date": date(2024, 8, 14), "release_source": "econ_events",
         "is_assumption_based": False},
    ]
    dgs_dates = pd.bdate_range("2024-06-03", periods=25).date.tolist()
    cal_dgs = [
        {"indicator_id": "US_TREASURY_10Y_YIELD", "observation_date": d,
         "release_date": d + timedelta(days=1), "release_source": "assumed_t_plus_1",
         "is_assumption_based": True}
        for d in dgs_dates
    ]
    return pd.DataFrame(cal_cpi + cal_dgs)


TRADE_DATES: List[date] = [
    date(2024, 6, 15),  # CPI: 5 candidates (Jan-May), DGS10: ~9 obs
    date(2024, 8, 15),  # CPI: all 7 candidates, DGS10: all 25 obs
]


def _run_gold() -> pd.DataFrame:
    """Build Gold macro features with standard fixtures."""
    return build_gold_macro_features(
        df_macro_silver=_build_macro_silver(),
        df_calendar=_build_calendar(),
        trade_dates=TRADE_DATES,
    )


# ════════════════════════════════════════════════════════════
# MF1 — Grain Uniqueness
# ════════════════════════════════════════════════════════════


class TestGrainUniqueness:
    """MF1: (indicator_id, trade_date) 당 최대 1행."""

    def test_mf1_no_duplicate_grain(self):
        gold = _run_gold()
        dupes = gold.duplicated(subset=["indicator_id", "trade_date"], keep=False)
        assert dupes.sum() == 0, (
            f"MF1 violated: {dupes.sum()} duplicate (indicator_id, trade_date) rows"
        )

    def test_mf1_output_columns(self):
        gold = _run_gold()
        assert list(gold.columns) == GOLD_MACRO_FEATURE_COLUMNS, (
            f"MF1 schema: expected {GOLD_MACRO_FEATURE_COLUMNS}, "
            f"got {list(gold.columns)}"
        )


# ════════════════════════════════════════════════════════════
# MF2 — PIT Gate
# ════════════════════════════════════════════════════════════


class TestPITGate:
    """MF2: selected_release_date < trade_date for all rows."""

    def test_mf2_release_strictly_before_trade(self):
        gold = _run_gold()
        has_release = gold.dropna(subset=["selected_release_date"])
        violations = has_release[
            has_release["selected_release_date"] >= has_release["trade_date"]
        ]
        assert len(violations) == 0, (
            f"MF2 violated: {len(violations)} rows where "
            f"selected_release_date >= trade_date:\n{violations}"
        )


# ════════════════════════════════════════════════════════════
# MF3 — Latest Release Selection
# ════════════════════════════════════════════════════════════


class TestLatestReleaseSelection:
    """MF3: 복수 후보 중 release_date 최대값 선택."""

    def test_mf3_cpi_at_jun15(self):
        """
        trade_date=2024-06-15, CPI candidates: Jan-May.
        Latest release < Jun15 is Jun12 (obs=May).
        """
        gold = _run_gold()
        row = gold[
            (gold["indicator_id"] == "CPI_US_ALL_ITEMS_SA")
            & (gold["trade_date"] == date(2024, 6, 15))
        ]
        assert len(row) == 1, "MF3: expected 1 CPI row for 2024-06-15"
        r = row.iloc[0]
        assert r["selected_observation_date"] == date(2024, 5, 1), (
            f"MF3: expected obs=2024-05-01, got {r['selected_observation_date']}"
        )
        assert r["selected_release_date"] == date(2024, 6, 12), (
            f"MF3: expected release=2024-06-12, got {r['selected_release_date']}"
        )
        assert r["selected_value"] == pytest.approx(304.0), (
            f"MF3: expected value=304.0, got {r['selected_value']}"
        )

    def test_mf3_cpi_at_aug15(self):
        """
        trade_date=2024-08-15, all 7 CPI obs available.
        Latest release = Aug14 (obs=Jul).
        """
        gold = _run_gold()
        row = gold[
            (gold["indicator_id"] == "CPI_US_ALL_ITEMS_SA")
            & (gold["trade_date"] == date(2024, 8, 15))
        ]
        assert len(row) == 1, "MF3: expected 1 CPI row for 2024-08-15"
        r = row.iloc[0]
        assert r["selected_observation_date"] == date(2024, 7, 1), (
            f"MF3: expected obs=2024-07-01, got {r['selected_observation_date']}"
        )
        assert r["selected_release_date"] == date(2024, 8, 14), (
            f"MF3: expected release=2024-08-14, got {r['selected_release_date']}"
        )
        assert r["selected_value"] == pytest.approx(306.0), (
            f"MF3: expected value=306.0, got {r['selected_value']}"
        )

    def test_mf3_cpi_delta_values_at_aug15(self):
        """
        CPI obs=2024-07-01 (value=306.0):
          delta_1m = 306.0 - 305.5 = 0.5  (obs Jun)
          delta_3m = 306.0 - 303.0 = 3.0  (obs Apr)
          delta_6m = 306.0 - 300.0 = 6.0  (obs Jan)
        """
        gold = _run_gold()
        r = gold[
            (gold["indicator_id"] == "CPI_US_ALL_ITEMS_SA")
            & (gold["trade_date"] == date(2024, 8, 15))
        ].iloc[0]

        assert r["delta_1m"] == pytest.approx(0.5), (
            f"MF3 delta: expected delta_1m=0.5, got {r['delta_1m']}"
        )
        assert r["delta_3m"] == pytest.approx(3.0), (
            f"MF3 delta: expected delta_3m=3.0, got {r['delta_3m']}"
        )
        assert r["delta_6m"] == pytest.approx(6.0), (
            f"MF3 delta: expected delta_6m=6.0, got {r['delta_6m']}"
        )

    def test_mf3_cpi_delta_6m_null_at_jun15(self):
        """
        CPI obs=2024-05-01: delta_6m needs obs=2023-11-01 (absent) → NULL.
        """
        gold = _run_gold()
        r = gold[
            (gold["indicator_id"] == "CPI_US_ALL_ITEMS_SA")
            & (gold["trade_date"] == date(2024, 6, 15))
        ].iloc[0]

        assert r["delta_1m"] == pytest.approx(1.0), (
            f"MF3 delta: expected delta_1m=1.0, got {r['delta_1m']}"
        )
        assert r["delta_3m"] == pytest.approx(3.0), (
            f"MF3 delta: expected delta_3m=3.0, got {r['delta_3m']}"
        )
        assert pd.isna(r["delta_6m"]), (
            f"MF3 delta: delta_6m should be NULL (no obs 2023-11-01), got {r['delta_6m']}"
        )


# ════════════════════════════════════════════════════════════
# MF4 / MF5 — Observation Date Semantics
# ════════════════════════════════════════════════════════════


class TestObservationDateSemantics:
    """MF4: Monthly → period anchor. MF5: Daily → actual date."""

    def test_mf4_monthly_observation_is_period_anchor(self):
        gold = _run_gold()
        cpi = gold[gold["indicator_id"] == "CPI_US_ALL_ITEMS_SA"].dropna(
            subset=["selected_observation_date"]
        )
        for _, row in cpi.iterrows():
            obs = row["selected_observation_date"]
            assert obs.day == 1, (
                f"MF4: CPI observation_date {obs} day != 1 (not period anchor)"
            )

    def test_mf5_daily_observation_is_actual_date(self):
        gold = _run_gold()
        dgs = gold[gold["indicator_id"] == "US_TREASURY_10Y_YIELD"].dropna(
            subset=["selected_observation_date"]
        )
        assert len(dgs) > 0, "MF5: expected DGS10 rows"
        fixture_dates = set(pd.bdate_range("2024-06-03", periods=25).date)
        for _, row in dgs.iterrows():
            obs = row["selected_observation_date"]
            assert obs in fixture_dates, (
                f"MF5: DGS10 obs {obs} not in source daily dates"
            )


# ════════════════════════════════════════════════════════════
# MF6 — Direction
# ════════════════════════════════════════════════════════════


class TestDirection:
    """MF6: direction in {up, down, flat} or NULL."""

    def test_mf6_valid_direction_values(self):
        gold = _run_gold()
        non_null = gold.dropna(subset=["direction"])
        invalid = non_null[~non_null["direction"].isin(VALID_DIRECTIONS)]
        assert len(invalid) == 0, (
            f"MF6 violated: invalid directions {invalid['direction'].unique().tolist()}"
        )

    def test_mf6_cpi_direction_up(self):
        """CPI at Aug15: delta_1m=0.5 > 0 → 'up'."""
        gold = _run_gold()
        r = gold[
            (gold["indicator_id"] == "CPI_US_ALL_ITEMS_SA")
            & (gold["trade_date"] == date(2024, 8, 15))
        ].iloc[0]
        assert r["direction"] == "up", (
            f"MF6: delta_1m=0.5>0, expected 'up', got '{r['direction']}'"
        )

    def test_mf6_dgs10_direction_down(self):
        """DGS10 at Aug15: values decrease → delta_1m < 0 → 'down'."""
        gold = _run_gold()
        row = gold[
            (gold["indicator_id"] == "US_TREASURY_10Y_YIELD")
            & (gold["trade_date"] == date(2024, 8, 15))
        ]
        assert len(row) == 1, "MF6: expected 1 DGS10 row for 2024-08-15"
        r = row.iloc[0]
        if pd.notna(r["delta_1m"]):
            assert r["direction"] == "down", (
                f"MF6: DGS10 delta_1m={r['delta_1m']}<0, "
                f"expected 'down', got '{r['direction']}'"
            )

    def test_mf6_direction_flat_when_zero_delta(self):
        """delta_1m == 0 → direction = 'flat'."""
        macro = pd.DataFrame([
            {"indicator_id": "CPI_US_ALL_ITEMS_SA", "date": date(2024, 1, 1),
             "value": 300.0},
            {"indicator_id": "CPI_US_ALL_ITEMS_SA", "date": date(2024, 2, 1),
             "value": 300.0},
        ])
        cal = pd.DataFrame([
            {"indicator_id": "CPI_US_ALL_ITEMS_SA",
             "observation_date": date(2024, 1, 1),
             "release_date": date(2024, 2, 13),
             "release_source": "econ_events", "is_assumption_based": False},
            {"indicator_id": "CPI_US_ALL_ITEMS_SA",
             "observation_date": date(2024, 2, 1),
             "release_date": date(2024, 3, 12),
             "release_source": "econ_events", "is_assumption_based": False},
        ])
        gold = build_gold_macro_features(macro, cal, [date(2024, 3, 15)])
        r = gold[gold["indicator_id"] == "CPI_US_ALL_ITEMS_SA"].iloc[0]
        assert r["delta_1m"] == pytest.approx(0.0), (
            f"MF6 flat: expected delta_1m=0.0, got {r['delta_1m']}"
        )
        assert r["direction"] == "flat", (
            f"MF6 flat: delta_1m=0 → 'flat', got '{r['direction']}'"
        )


# ════════════════════════════════════════════════════════════
# MF7 — Regime
# ════════════════════════════════════════════════════════════


class TestRegime:
    """MF7: regime in {tightening, easing, neutral} or NULL."""

    def test_mf7_valid_regime_values(self):
        gold = _run_gold()
        non_null = gold.dropna(subset=["regime"])
        invalid = non_null[~non_null["regime"].isin(VALID_REGIMES)]
        assert len(invalid) == 0, (
            f"MF7 violated: invalid regimes {invalid['regime'].unique().tolist()}"
        )

    def test_mf7_cpi_tightening(self):
        """CPI at Aug15: delta_3m=3.0>0 AND delta_6m=6.0>0 → 'tightening'."""
        gold = _run_gold()
        r = gold[
            (gold["indicator_id"] == "CPI_US_ALL_ITEMS_SA")
            & (gold["trade_date"] == date(2024, 8, 15))
        ].iloc[0]
        assert r["regime"] == "tightening", (
            f"MF7: delta_3m>0 AND delta_6m>0 → 'tightening', got '{r['regime']}'"
        )

    def test_mf7_easing_regime(self):
        """Declining values → delta_3m<0 AND delta_6m<0 → 'easing'."""
        macro = pd.DataFrame([
            {"indicator_id": "CPI_US_ALL_ITEMS_SA",
             "date": date(2024, m, 1), "value": 310.0 - m}
            for m in range(1, 8)
        ])
        cal = pd.DataFrame([
            {"indicator_id": "CPI_US_ALL_ITEMS_SA",
             "observation_date": date(2024, m, 1),
             "release_date": date(2024, m + 1, 12) if m < 12
             else date(2025, 1, 12),
             "release_source": "econ_events", "is_assumption_based": False}
            for m in range(1, 8)
        ])
        gold = build_gold_macro_features(macro, cal, [date(2024, 8, 15)])
        r = gold[gold["indicator_id"] == "CPI_US_ALL_ITEMS_SA"].iloc[0]
        # obs=Jul(303.0), delta_3m=303-306=-3, delta_6m=303-309=-6
        assert r["regime"] == "easing", (
            f"MF7: both deltas<0 → 'easing', got '{r['regime']}'"
        )

    def test_mf7_neutral_regime(self):
        """Mixed delta signs → 'neutral'."""
        macro = pd.DataFrame([
            {"indicator_id": "CPI_US_ALL_ITEMS_SA", "date": date(2024, 1, 1), "value": 305.0},
            {"indicator_id": "CPI_US_ALL_ITEMS_SA", "date": date(2024, 2, 1), "value": 303.0},
            {"indicator_id": "CPI_US_ALL_ITEMS_SA", "date": date(2024, 3, 1), "value": 301.0},
            {"indicator_id": "CPI_US_ALL_ITEMS_SA", "date": date(2024, 4, 1), "value": 300.0},
            {"indicator_id": "CPI_US_ALL_ITEMS_SA", "date": date(2024, 5, 1), "value": 301.0},
            {"indicator_id": "CPI_US_ALL_ITEMS_SA", "date": date(2024, 6, 1), "value": 302.0},
            {"indicator_id": "CPI_US_ALL_ITEMS_SA", "date": date(2024, 7, 1), "value": 303.0},
        ])
        cal = pd.DataFrame([
            {"indicator_id": "CPI_US_ALL_ITEMS_SA",
             "observation_date": date(2024, m, 1),
             "release_date": date(2024, m + 1, 12) if m < 12
             else date(2025, 1, 12),
             "release_source": "econ_events", "is_assumption_based": False}
            for m in range(1, 8)
        ])
        gold = build_gold_macro_features(macro, cal, [date(2024, 8, 15)])
        r = gold[gold["indicator_id"] == "CPI_US_ALL_ITEMS_SA"].iloc[0]
        # obs=Jul(303), delta_3m=303-300=+3, delta_6m=303-305=-2 → mixed
        assert r["regime"] == "neutral", (
            f"MF7: mixed signs → 'neutral', got '{r['regime']}'"
        )


# ════════════════════════════════════════════════════════════
# MF8 — Cross-Indicator Isolation
# ════════════════════════════════════════════════════════════


class TestCrossIndicatorIsolation:
    """MF8: removing one indicator must not change another."""

    def test_mf8_removing_dgs10_does_not_change_cpi(self):
        macro_full = _build_macro_silver()
        cal_full = _build_calendar()
        gold_full = build_gold_macro_features(macro_full, cal_full, TRADE_DATES)
        cpi_full = (
            gold_full[gold_full["indicator_id"] == "CPI_US_ALL_ITEMS_SA"]
            .reset_index(drop=True)
        )

        macro_cpi = macro_full[
            macro_full["indicator_id"] == "CPI_US_ALL_ITEMS_SA"
        ].reset_index(drop=True)
        cal_cpi = cal_full[
            cal_full["indicator_id"] == "CPI_US_ALL_ITEMS_SA"
        ].reset_index(drop=True)
        gold_cpi = build_gold_macro_features(macro_cpi, cal_cpi, TRADE_DATES)
        cpi_only = (
            gold_cpi[gold_cpi["indicator_id"] == "CPI_US_ALL_ITEMS_SA"]
            .reset_index(drop=True)
        )

        pd.testing.assert_frame_equal(
            cpi_full[GOLD_MACRO_FEATURE_COLUMNS],
            cpi_only[GOLD_MACRO_FEATURE_COLUMNS],
            check_exact=False,
            atol=1e-9,
            obj="MF8: CPI with/without DGS10",
        )


# ════════════════════════════════════════════════════════════
# MF9 — NULL Propagation & Insufficient History
# ════════════════════════════════════════════════════════════


class TestNullPropagation:
    """MF9: NULL value → derived NULL; insufficient history → delta NULL."""

    def test_mf9_null_value_propagates(self):
        """selected_value=NULL → all derived columns NULL."""
        macro = pd.DataFrame([
            {"indicator_id": "CPI_US_ALL_ITEMS_SA",
             "date": date(2024, 1, 1), "value": None},
        ])
        cal = pd.DataFrame([
            {"indicator_id": "CPI_US_ALL_ITEMS_SA",
             "observation_date": date(2024, 1, 1),
             "release_date": date(2024, 2, 13),
             "release_source": "econ_events", "is_assumption_based": False},
        ])
        gold = build_gold_macro_features(macro, cal, [date(2024, 2, 15)])
        r = gold[gold["indicator_id"] == "CPI_US_ALL_ITEMS_SA"].iloc[0]

        assert pd.isna(r["selected_value"]), "MF9: selected_value should be NULL"
        assert pd.isna(r["delta_1m"]), "MF9: delta_1m should be NULL"
        assert pd.isna(r["delta_3m"]), "MF9: delta_3m should be NULL"
        assert pd.isna(r["delta_6m"]), "MF9: delta_6m should be NULL"
        assert pd.isna(r["direction"]) or r["direction"] is None, (
            "MF9: direction should be NULL when value is NULL"
        )
        assert pd.isna(r["regime"]) or r["regime"] is None, (
            "MF9: regime should be NULL when value is NULL"
        )

    def test_mf9_insufficient_monthly_history(self):
        """2 months → delta_1m OK, delta_3m/6m NULL."""
        macro = pd.DataFrame([
            {"indicator_id": "CPI_US_ALL_ITEMS_SA",
             "date": date(2024, 1, 1), "value": 300.0},
            {"indicator_id": "CPI_US_ALL_ITEMS_SA",
             "date": date(2024, 2, 1), "value": 301.0},
        ])
        cal = pd.DataFrame([
            {"indicator_id": "CPI_US_ALL_ITEMS_SA",
             "observation_date": date(2024, 1, 1),
             "release_date": date(2024, 2, 13),
             "release_source": "econ_events", "is_assumption_based": False},
            {"indicator_id": "CPI_US_ALL_ITEMS_SA",
             "observation_date": date(2024, 2, 1),
             "release_date": date(2024, 3, 12),
             "release_source": "econ_events", "is_assumption_based": False},
        ])
        gold = build_gold_macro_features(macro, cal, [date(2024, 3, 15)])
        r = gold[gold["indicator_id"] == "CPI_US_ALL_ITEMS_SA"].iloc[0]

        assert r["delta_1m"] == pytest.approx(1.0), (
            f"MF9: delta_1m=301-300=1.0, got {r['delta_1m']}"
        )
        assert pd.isna(r["delta_3m"]), (
            f"MF9: delta_3m NULL with 2 months, got {r['delta_3m']}"
        )
        assert pd.isna(r["delta_6m"]), (
            f"MF9: delta_6m NULL with 2 months, got {r['delta_6m']}"
        )

    def test_mf9_daily_insufficient_for_shift21(self):
        """DGS10 with 10 rows → shift(21) exceeds range → delta_1m NULL."""
        dgs_dates = pd.bdate_range("2024-06-03", periods=10).date.tolist()
        macro = pd.DataFrame([
            {"indicator_id": "US_TREASURY_10Y_YIELD",
             "date": d, "value": 4.50 - i * 0.01}
            for i, d in enumerate(dgs_dates)
        ])
        cal = pd.DataFrame([
            {"indicator_id": "US_TREASURY_10Y_YIELD",
             "observation_date": d,
             "release_date": d + timedelta(days=1),
             "release_source": "assumed_t_plus_1",
             "is_assumption_based": True}
            for d in dgs_dates
        ])
        gold = build_gold_macro_features(macro, cal, [date(2024, 6, 20)])
        r = gold[gold["indicator_id"] == "US_TREASURY_10Y_YIELD"].iloc[0]

        assert pd.isna(r["delta_1m"]), (
            f"MF9: DGS10 10 rows, shift(21) out of range, "
            f"expected NULL, got {r['delta_1m']}"
        )


# ════════════════════════════════════════════════════════════
# MF10 — zscore_12m not computed in v1
# ════════════════════════════════════════════════════════════


class TestZscoreV1:
    """MF10: zscore_12m column present, always NULL in v1."""

    def test_mf10_zscore_always_null(self):
        gold = _run_gold()
        assert "zscore_12m" in gold.columns, (
            "MF10: zscore_12m column must exist in output schema"
        )
        assert gold["zscore_12m"].isna().all(), (
            f"MF10: zscore_12m must be NULL for all rows, "
            f"found {gold['zscore_12m'].notna().sum()} non-NULL"
        )
