from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for Observability Track domain models."""


class BaseSchema(BaseModel):
    """Pydantic v2 base schema with shared config."""

    model_config = ConfigDict(
        from_attributes=True,
        arbitrary_types_allowed=False,
        str_strip_whitespace=True,
    )
