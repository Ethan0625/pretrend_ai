from __future__ import annotations

from datetime import date

import pandas as pd

from pretrend.pipeline.strategy_engine.group_transition.engine import (
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
