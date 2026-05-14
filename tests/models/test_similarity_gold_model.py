from __future__ import annotations

from sqlalchemy import CheckConstraint, UniqueConstraint

from pretrend.models import Base, SimilarityGold


EXPECTED_COLUMNS = [
    "query_date",
    "neighbor_date",
    "rank",
    "score",
    "gap_days",
    "built_at",
]


def test_similarity_gold_table_registered() -> None:
    assert "similarity_gold" in Base.metadata.tables
    assert SimilarityGold.__table__ is Base.metadata.tables["similarity_gold"]


def test_similarity_gold_columns_present() -> None:
    table = SimilarityGold.__table__
    assert list(table.columns.keys()) == EXPECTED_COLUMNS


def test_similarity_gold_pk() -> None:
    table = SimilarityGold.__table__
    assert [column.name for column in table.primary_key.columns] == [
        "query_date",
        "neighbor_date",
    ]


def test_similarity_gold_check_constraints() -> None:
    constraints = {
        constraint.name
        for constraint in SimilarityGold.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert constraints == {
        "ck_similarity_gold_rank",
        "ck_similarity_gold_score",
        "ck_similarity_gold_min_gap",
    }


def test_similarity_gold_unique_constraint() -> None:
    constraints = [
        constraint
        for constraint in SimilarityGold.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    ]
    assert len(constraints) == 1
    assert constraints[0].name == "uq_similarity_gold_query_rank"
    assert [column.name for column in constraints[0].columns] == [
        "query_date",
        "rank",
    ]
