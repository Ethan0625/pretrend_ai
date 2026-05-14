from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, PrimaryKeyConstraint, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pretrend.models.base import Base


class ExplainabilityCache(Base):
    """Cached LLM explanation report by use case and prompt version."""

    __tablename__ = "explainability_cache"
    __table_args__ = (
        PrimaryKeyConstraint(
            "use_case",
            "query_date",
            "model_id",
            "prompt_version",
            name="pk_explainability_cache",
        ),
        CheckConstraint(
            "use_case IN ('similarity_regime','similarity_gold','regime','macro')",
            name="ck_explainability_cache_use_case",
        ),
    )

    use_case: Mapped[str] = mapped_column(Text, nullable=False)
    query_date: Mapped[date] = mapped_column(Date, nullable=False)
    model_id: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    report_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    output_hash: Mapped[str] = mapped_column(Text, nullable=False)
    built_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
