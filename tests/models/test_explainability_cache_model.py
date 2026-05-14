from __future__ import annotations

from sqlalchemy import CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB

from pretrend.models import Base, ExplainabilityCache


EXPECTED_COLUMNS = [
    "use_case",
    "query_date",
    "model_id",
    "prompt_version",
    "report_json",
    "output_hash",
    "built_at",
]


def test_explainability_cache_table_registered() -> None:
    assert "explainability_cache" in Base.metadata.tables
    assert ExplainabilityCache.__table__ is Base.metadata.tables["explainability_cache"]


def test_explainability_cache_columns_present() -> None:
    assert list(ExplainabilityCache.__table__.columns.keys()) == EXPECTED_COLUMNS


def test_explainability_cache_pk() -> None:
    table = ExplainabilityCache.__table__
    assert [column.name for column in table.primary_key.columns] == [
        "use_case",
        "query_date",
        "model_id",
        "prompt_version",
    ]


def test_explainability_cache_check_constraint_use_case() -> None:
    constraints = [
        constraint
        for constraint in ExplainabilityCache.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    ]
    assert len(constraints) == 1
    assert constraints[0].name == "ck_explainability_cache_use_case"
    sql = str(constraints[0].sqltext)
    for value in ["similarity_regime", "similarity_gold", "regime", "macro"]:
        assert value in sql


def test_explainability_cache_report_json_is_jsonb() -> None:
    assert isinstance(ExplainabilityCache.__table__.c.report_json.type, JSONB)
