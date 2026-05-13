from __future__ import annotations

from datetime import date

import pandas as pd

from pretrend.observability.regime.rotation.engine import (
    build_group_transition_signal,
)


def _sample_universe() -> pd.DataFrame:
    rows = []
    for i, td in enumerate(
        [
            date(2026, 1, 5),
            date(2026, 1, 6),
            date(2026, 1, 7),
            date(2026, 1, 8),
            date(2026, 1, 9),
            date(2026, 1, 12),
            date(2026, 1, 13),
        ]
    ):
        rows.extend(
            [
                {
                    "rebalance_date": td,
                    "symbol": "XLE",
                    "asset_group": "SECTOR",
                    "relative_strength": 0.05 if i < 4 else -0.02,
                    "is_candidate": True,
                },
                {
                    "rebalance_date": td,
                    "symbol": "XLV",
                    "asset_group": "SECTOR",
                    "relative_strength": 0.03 if i < 4 else -0.01,
                    "is_candidate": True,
                },
                {
                    "rebalance_date": td,
                    "symbol": "TLT",
                    "asset_group": "BOND",
                    "relative_strength": -0.01 if i < 4 else 0.02,
                    "is_candidate": True,
                },
                {
                    "rebalance_date": td,
                    "symbol": "LQD",
                    "asset_group": "BOND",
                    "relative_strength": -0.02 if i < 4 else 0.01,
                    "is_candidate": True,
                },
            ]
        )
    return pd.DataFrame(rows)


def test_group_transition_signal_columns_and_run_id() -> None:
    df = _sample_universe()
    out = build_group_transition_signal(df, run_id="rid1")
    assert not out.empty
    assert set(
        [
            "trade_date",
            "asset_group",
            "group_state_now",
            "group_expected_10d",
            "group_transition_hazard_10d",
            "source_run_id",
        ]
    ).issubset(set(out.columns))
    assert (out["source_run_id"] == "rid1").all()


def test_group_transition_hazard_range_and_fail_open_unknown() -> None:
    # 표본 부족(COUNTRY 1종목) -> UNKNOWN/fail-open 확인
    df = _sample_universe()
    df = pd.concat(
        [
            df,
            pd.DataFrame(
                [
                    {
                        "rebalance_date": date(2026, 1, 13),
                        "symbol": "EWY",
                        "asset_group": "COUNTRY",
                        "relative_strength": 0.01,
                        "is_candidate": True,
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    out = build_group_transition_signal(df, run_id="rid2")
    assert not out.empty

    hz = out["group_transition_hazard_10d"].dropna()
    if not hz.empty:
        assert ((hz >= 0.0) & (hz <= 1.0)).all()

    country = out[out["asset_group"] == "COUNTRY"]
    if not country.empty:
        assert (country["group_state_now"] == "UNKNOWN").all()


def test_group_transition_state_boundary_pos_ratio() -> None:
    # STRONG 경계: pos_ratio == 0.5 이고 median > 0
    strong_df = pd.DataFrame(
        [
            {"rebalance_date": date(2026, 2, 3), "symbol": "XLE", "asset_group": "SECTOR", "relative_strength": 0.10, "is_candidate": True},
            {"rebalance_date": date(2026, 2, 3), "symbol": "XLV", "asset_group": "SECTOR", "relative_strength": 0.01, "is_candidate": True},
            {"rebalance_date": date(2026, 2, 3), "symbol": "XLF", "asset_group": "SECTOR", "relative_strength": -0.001, "is_candidate": True},
            {"rebalance_date": date(2026, 2, 3), "symbol": "XLI", "asset_group": "SECTOR", "relative_strength": -0.05, "is_candidate": True},
        ]
    )
    out_strong = build_group_transition_signal(strong_df, run_id="rid3")
    assert out_strong.iloc[-1]["group_state_now"] == "STRONG"

    # WEAK 경계: pos_ratio == 0.25(<0.4) 이고 median < 0
    weak_df = pd.DataFrame(
        [
            {"rebalance_date": date(2026, 2, 4), "symbol": "XLE", "asset_group": "SECTOR", "relative_strength": -0.10, "is_candidate": True},
            {"rebalance_date": date(2026, 2, 4), "symbol": "XLV", "asset_group": "SECTOR", "relative_strength": -0.06, "is_candidate": True},
            {"rebalance_date": date(2026, 2, 4), "symbol": "XLF", "asset_group": "SECTOR", "relative_strength": -0.02, "is_candidate": True},
            {"rebalance_date": date(2026, 2, 4), "symbol": "XLI", "asset_group": "SECTOR", "relative_strength": 0.03, "is_candidate": True},
        ]
    )
    out_weak = build_group_transition_signal(weak_df, run_id="rid4")
    assert out_weak.iloc[-1]["group_state_now"] == "WEAK"


def test_group_transition_gts5_fallback_empty() -> None:
    out = build_group_transition_signal(pd.DataFrame(), run_id="rid5")
    assert out.empty
    assert {
        "trade_date",
        "asset_group",
        "group_state_now",
        "group_expected_10d",
        "group_transition_hazard_10d",
        "source_run_id",
    }.issubset(set(out.columns))
