from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import MetaData

from pretrend.models import Base, BaseSchema


def test_models_package_imports_base_types() -> None:
    assert Base is not None
    assert BaseSchema is not None


def test_base_exposes_empty_metadata() -> None:
    assert isinstance(Base.metadata, MetaData)
    assert Base.metadata.tables == {}


def test_base_schema_supports_model_dump() -> None:
    class ExampleSchema(BaseSchema):
        name: str

    schema = ExampleSchema(name="  alpha  ")

    assert schema.model_dump() == {"name": "alpha"}
    assert isinstance(schema, BaseModel)


def test_base_schema_sets_from_attributes() -> None:
    assert BaseSchema.model_config["from_attributes"] is True
