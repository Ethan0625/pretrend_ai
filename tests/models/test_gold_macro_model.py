from __future__ import annotations

from sqlalchemy import CheckConstraint

from pretrend.models import Base, GoldMacroFeature


EXPECTED_COLUMNS = [
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

EXPECTED_NULLABILITY = {
    "indicator_id": False,
    "trade_date": False,
    "selected_observation_date": True,
    "selected_value": True,
    "selected_release_date": True,
    "delta_1m": True,
    "delta_3m": True,
    "delta_6m": True,
    "direction": True,
    "regime": True,
    "zscore_12m": True,
    "release_source": True,
    "is_assumption_based": False,
}


def test_gold_macro_table_registered() -> None:
    assert "gold_macro_features" in Base.metadata.tables
    assert GoldMacroFeature.__table__ is Base.metadata.tables["gold_macro_features"]


def test_gold_macro_columns_present() -> None:
    table = GoldMacroFeature.__table__
    assert list(table.columns.keys()) == EXPECTED_COLUMNS


def test_gold_macro_pk() -> None:
    table = GoldMacroFeature.__table__
    assert [column.name for column in table.primary_key.columns] == [
        "indicator_id",
        "trade_date",
    ]


def test_gold_macro_check_constraints() -> None:
    constraints = {
        constraint.name
        for constraint in GoldMacroFeature.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert constraints == {
        "ck_gold_macro_features_pit",
        "ck_gold_macro_features_direction",
        "ck_gold_macro_features_regime",
        "ck_gold_macro_features_release_source",
    }


def test_gold_macro_column_nullability() -> None:
    table = GoldMacroFeature.__table__
    assert {
        column.name: column.nullable
        for column in table.columns
    } == EXPECTED_NULLABILITY
