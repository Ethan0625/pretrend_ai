from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from sqlalchemy import Engine, text

from pretrend.observability.similarity.columns import (
    REGIME_SIMILARITY_FEATURE_COLUMNS,
)
from pretrend.observability.similarity.producer import (
    build_market_state_feature_frame,
    build_market_state_similarity_features,
    encode_bool,
    encode_risk_direction,
    encode_rotation_state,
    encode_short_signal,
    pivot_rotation_features,
)
from tests.observability.db_test_utils import isolated_test_engine


REQUIRED_TABLES = {"gold_market_state_similarity_feature"}


@pytest.fixture(scope="module")
def pg_engine() -> Engine:
    return isolated_test_engine(REQUIRED_TABLES)


@pytest.fixture()
def clean_similarity_feature_table(pg_engine: Engine) -> None:
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE gold_market_state_similarity_feature"))


def _market_state_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": date(2026, 5, 1),
                "long_phase": "RECOVERY",
                "mid_regime": "RISK_ON",
                "short_signal": "RELIEF",
                "long_phase_confidence": 0.8,
                "mid_regime_confidence": 0.7,
                "short_signal_confidence": 0.6,
                "run_universe": True,
                "risk_gate": True,
                "state_age_days": 4,
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
            }
        ]
    )


def _rotation_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": date(2026, 5, 1),
                "asset_group": "SECTOR",
                "asset_name": "ENERGY",
                "group_state_now": "STRONG",
            },
            {
                "trade_date": date(2026, 5, 1),
                "asset_group": "SECTOR",
                "asset_name": "HEALTH_CARE",
                "group_state_now": "WEAK",
            },
            {
                "trade_date": date(2026, 5, 1),
                "asset_group": "VOLATILITY_INDEX",
                "asset_name": "CBOE_VOLATILITY_INDEX",
                "group_state_now": "STRONG",
            },
        ]
    )


def test_enum_mapping() -> None:
    assert encode_risk_direction("RISK_ON") == 1
    assert encode_risk_direction("NEUTRAL") == 0
    assert encode_risk_direction("RISK_OFF") == -1
    assert encode_risk_direction("other") is None
    assert encode_short_signal("RELIEF") == 1
    assert encode_short_signal("STABLE") == 0
    assert encode_short_signal("PANIC") == -1
    assert encode_rotation_state("STRONG") == 1
    assert encode_rotation_state("WEAK") == -1
    assert encode_bool(True) == 1
    assert encode_bool(False) == 0
    assert encode_bool(None) is None


def test_rotation_pivot_excludes_vix_skew() -> None:
    pivot = pivot_rotation_features(_rotation_rows())
    assert len(pivot) == 1
    row = pivot.iloc[0]
    assert row["rot_energy_state_code"] == 1
    assert row["rot_health_care_state_code"] == -1
    assert "rot_cboe_volatility_index_state_code" not in pivot.columns


def test_market_state_feature_frame_has_61_features() -> None:
    frame = build_market_state_feature_frame(_market_state_rows(), _rotation_rows())
    assert len(frame) == 1
    assert len(REGIME_SIMILARITY_FEATURE_COLUMNS) == 61
    assert list(frame.columns) == ["trade_date", *REGIME_SIMILARITY_FEATURE_COLUMNS]
    row = frame.iloc[0]
    assert row["long_phase_recovery"] == 1
    assert row["mid_regime_code"] == 1
    assert row["short_signal_code"] == 1
    assert row["rot_energy_state_code"] == 1
    assert pd.isna(row["rot_utilities_state_code"])


def test_build_market_state_similarity_features_idempotent(
    pg_engine: Engine,
    clean_similarity_feature_table: None,
) -> None:
    result = build_market_state_similarity_features(
        date(2026, 5, 1),
        date(2026, 5, 1),
        engine=pg_engine,
        market_state_df=_market_state_rows(),
        rotation_df=_rotation_rows(),
    )
    assert result == {
        "rows_upserted": 1,
        "query_count": 1,
        "table": "gold_market_state_similarity_feature",
    }
    second = build_market_state_similarity_features(
        date(2026, 5, 1),
        date(2026, 5, 1),
        engine=pg_engine,
        market_state_df=_market_state_rows(),
        rotation_df=_rotation_rows(),
    )
    assert second["rows_upserted"] == 1

    with pg_engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT COUNT(*), MAX(rot_energy_state_code)
                FROM gold_market_state_similarity_feature
                """
            )
        ).one()
    assert row[0] == 1
    assert row[1] == 1
