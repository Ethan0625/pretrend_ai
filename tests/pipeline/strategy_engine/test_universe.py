from __future__ import annotations

from datetime import date

import pandas as pd

from pretrend.pipeline.strategy_engine.registries import CORE_HOLD_REGISTRY
from pretrend.pipeline.strategy_engine.universe.engine import build_universe


def _policy_selection() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_date": [date(2026, 5, 15)],
            "run_universe": [True],
            "long_phase": ["EXPANSION"],
            "mid_regime": ["RISK_ON"],
        }
    )


def _eod(rows: list[tuple[str, str, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": symbol,
                "trade_date": date(2026, 5, 15),
                "asset_group": asset_group,
                "ret_20d": ret_20d,
            }
            for symbol, asset_group, ret_20d in rows
        ]
    )


def test_universe_disables_tactical_ranking_when_spy_ret_missing() -> None:
    """OFS-004: SPY warmup 부족이면 relative_strength는 NULL이고 tactical 후보를 열지 않는다."""
    result = build_universe(
        _policy_selection(),
        _eod(
            [
                ("SPY", "INDEX", float("nan")),
                ("TLT", "BOND", 0.02),
                ("IAU", "COMMODITY", 0.03),
                ("XLK", "SECTOR", 0.20),
            ]
        ),
    )

    tactical = result[~result["symbol"].isin(CORE_HOLD_REGISTRY)]
    assert not tactical["is_candidate"].any()
    assert result["relative_strength"].isna().all()

    core = result[result["symbol"].isin(CORE_HOLD_REGISTRY)]
    assert core["is_candidate"].all()


def test_universe_excludes_non_finite_tactical_ret_from_ranking() -> None:
    """OFS-004: 개별 tactical ret_20d가 비정상이면 RS ranking에서 제외한다."""
    result = build_universe(
        _policy_selection(),
        _eod(
            [
                ("SPY", "INDEX", 0.01),
                ("TLT", "BOND", 0.02),
                ("IAU", "COMMODITY", 0.03),
                ("XLK", "SECTOR", float("inf")),
                ("XLV", "SECTOR", 0.04),
            ]
        ),
    )

    xlk = result[result["symbol"] == "XLK"].iloc[0]
    xlv = result[result["symbol"] == "XLV"].iloc[0]

    assert not bool(xlk["is_candidate"])
    assert pd.isna(xlk["relative_strength"])
    assert bool(xlv["is_candidate"])
    assert abs(xlv["relative_strength"] - 0.03) < 1e-9
