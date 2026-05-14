from __future__ import annotations

from sqlalchemy import DateTime, Float, Integer

from pretrend.models import Base, GoldMarketStateSimilarityFeature
from pretrend.models.gold_market_state_similarity_feature import (
    REGIME_SIMILARITY_FEATURE_COLUMNS,
)


EXPECTED_COLUMNS = [
    "trade_date",
    *REGIME_SIMILARITY_FEATURE_COLUMNS,
    "built_at",
]


def test_gold_market_state_similarity_feature_table_registered() -> None:
    assert "gold_market_state_similarity_feature" in Base.metadata.tables
    assert (
        GoldMarketStateSimilarityFeature.__table__
        is Base.metadata.tables["gold_market_state_similarity_feature"]
    )


def test_gold_market_state_similarity_feature_columns_present() -> None:
    table = GoldMarketStateSimilarityFeature.__table__
    assert list(table.columns.keys()) == EXPECTED_COLUMNS


def test_gold_market_state_similarity_feature_pk() -> None:
    table = GoldMarketStateSimilarityFeature.__table__
    assert [column.name for column in table.primary_key.columns] == ["trade_date"]


def test_gold_market_state_similarity_feature_numeric_schema() -> None:
    table = GoldMarketStateSimilarityFeature.__table__
    feature_columns = [
        table.columns[name] for name in REGIME_SIMILARITY_FEATURE_COLUMNS
    ]
    assert len(feature_columns) == 61
    assert all(
        isinstance(column.type, (Integer, Float))
        for column in feature_columns
    )


def test_gold_market_state_similarity_feature_code_columns_nullable() -> None:
    table = GoldMarketStateSimilarityFeature.__table__
    code_columns = [
        column
        for column in REGIME_SIMILARITY_FEATURE_COLUMNS
        if column.startswith("long_phase_")
        or column.endswith("_code")
        or column.endswith("_flag")
    ]
    assert code_columns
    assert all(table.columns[column].nullable is True for column in code_columns)


def test_gold_market_state_similarity_feature_built_at() -> None:
    column = GoldMarketStateSimilarityFeature.__table__.columns["built_at"]
    assert isinstance(column.type, DateTime)
    assert column.type.timezone is True
    assert column.nullable is False
