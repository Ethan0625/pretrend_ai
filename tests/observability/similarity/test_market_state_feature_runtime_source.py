from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import Engine, text

from pretrend.observability.similarity.runtime_source import (
    _default_strategy_root,
    build_market_state_similarity_features_from_runtime,
    load_market_state_runtime_source,
)
from tests.observability.db_test_utils import isolated_test_engine


REQUIRED_TABLES = {"gold_market_state_similarity_feature"}


@pytest.fixture(scope="module")
def pg_engine() -> Engine:
    return isolated_test_engine(REQUIRED_TABLES)


@pytest.fixture()
def strategy_root(tmp_path: Path) -> Path:
    root = tmp_path / "strategy"
    _write_stage(
        root,
        "axis_horizon_state",
        pd.DataFrame(
            [
                {
                    "trade_date": date(2026, 5, 12),
                    "long_phase": "LATE_CYCLE",
                    "long_phase_confidence": 0.8,
                    "mid_regime": "RISK_OFF",
                    "mid_regime_confidence": 0.7,
                    "short_signal": "STABLE",
                    "short_signal_confidence": 0.6,
                    "source_run_id": "test",
                }
            ]
        ),
        date(2026, 5, 12),
    )
    _write_stage(
        root,
        "market_position",
        pd.DataFrame(
            [
                {
                    "trade_date": date(2026, 5, 12),
                    "long_phase": "LATE_CYCLE",
                    "mid_regime": "RISK_OFF",
                    "short_signal": "STABLE",
                    "run_universe": True,
                    "risk_gate": False,
                    "source_run_id": "test",
                }
            ]
        ),
        date(2026, 5, 12),
    )
    _write_stage(
        root,
        "next_step_signal",
        pd.DataFrame(
            [
                {
                    "trade_date": date(2026, 5, 12),
                    "state_age_days": 3,
                    "sojourn_prob_5d": 0.8,
                    "sojourn_prob_10d": 0.7,
                    "sojourn_prob_20d": 0.6,
                    "sojourn_prob_60d": 0.5,
                    "sojourn_prob_120d": 0.4,
                    "transition_hazard_5d": 0.2,
                    "transition_hazard_10d": 0.3,
                    "transition_hazard_20d": 0.4,
                    "transition_hazard_60d": 0.5,
                    "transition_hazard_120d": 0.6,
                    "source_run_id": "test",
                }
            ]
        ),
        date(2026, 5, 12),
    )
    _write_stage(
        root,
        "what_to_hold",
        pd.DataFrame(
            [
                {
                    "decision_date": date(2026, 5, 12),
                    "symbol": "SPY",
                    "asset_group": "INDEX",
                    "relative_strength": 0.0,
                    "is_candidate": True,
                },
                {
                    "decision_date": date(2026, 5, 12),
                    "symbol": "XLK",
                    "asset_group": "SECTOR",
                    "relative_strength": 0.12,
                    "is_candidate": True,
                },
                {
                    "decision_date": date(2026, 5, 12),
                    "symbol": "XLV",
                    "asset_group": "SECTOR",
                    "relative_strength": -0.04,
                    "is_candidate": False,
                },
            ]
        ),
        date(2026, 5, 12),
    )
    return root


def test_load_market_state_runtime_source(strategy_root: Path) -> None:
    market_state, rotation = load_market_state_runtime_source(
        date(2026, 5, 1),
        date(2026, 5, 13),
        strategy_root=strategy_root,
    )

    assert len(market_state) == 1
    row = market_state.iloc[0]
    assert row["trade_date"] == date(2026, 5, 12)
    assert row["mid_regime"] == "RISK_OFF"
    assert bool(row["risk_gate"]) is False
    assert row["transition_hazard_120d"] == 0.6

    assert set(rotation["asset_name"]) == {"SP500", "INFORMATION_TECH", "HEALTH_CARE"}
    assert dict(zip(rotation["asset_name"], rotation["group_state_now"]))[
        "INFORMATION_TECH"
    ] == "STRONG"


def test_default_strategy_root_uses_data_root_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "mounted-data"
    monkeypatch.setenv("PRETREND_DATA_ROOT", str(data_root))
    monkeypatch.delenv("PRETREND_DATA_DIR", raising=False)

    assert _default_strategy_root() == data_root / "strategy"


def test_build_market_state_similarity_features_from_runtime_idempotent(
    pg_engine: Engine,
    strategy_root: Path,
) -> None:
    with pg_engine.begin() as conn:
        conn.execute(
            text(
                """
                DELETE FROM gold_market_state_similarity_feature
                WHERE trade_date BETWEEN '2026-05-01' AND '2026-05-13'
                """
            )
        )

    first = build_market_state_similarity_features_from_runtime(
        date(2026, 5, 1),
        date(2026, 5, 13),
        engine=pg_engine,
        strategy_root=strategy_root,
    )
    second = build_market_state_similarity_features_from_runtime(
        date(2026, 5, 1),
        date(2026, 5, 13),
        engine=pg_engine,
        strategy_root=strategy_root,
    )

    assert first["rows_upserted"] == 1
    assert second["rows_upserted"] == 1
    with pg_engine.connect() as conn:
        count = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM gold_market_state_similarity_feature
                WHERE trade_date BETWEEN '2026-05-01' AND '2026-05-13'
                """
            )
        ).scalar_one()
        row = conn.execute(
            text(
                """
                SELECT mid_regime_code, short_signal_code,
                       rot_information_tech_state_code,
                       rot_health_care_state_code
                FROM gold_market_state_similarity_feature
                WHERE trade_date = '2026-05-12'
                """
            )
        ).one()
    assert count == 1
    assert row[0] == -1
    assert row[1] == 0
    assert row[2] == 1
    assert row[3] == -1


def _write_stage(root: Path, stage: str, df: pd.DataFrame, decision_date: date) -> None:
    out_dir = root / stage / f"decision_date={decision_date.isoformat()}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{stage}_{decision_date.strftime('%Y%m%d')}.parquet"
    df.to_parquet(out, index=False)
