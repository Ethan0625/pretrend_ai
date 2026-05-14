from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Float, Integer, PrimaryKeyConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pretrend.models.base import Base


class SimilarityRegime(Base):
    """Top-N historical neighbors for regime-view similarity."""

    __tablename__ = "similarity_regime"
    __table_args__ = (
        PrimaryKeyConstraint(
            "query_date",
            "neighbor_date",
            name="pk_similarity_regime",
        ),
        CheckConstraint("rank >= 1 AND rank <= 1000", name="ck_similarity_regime_rank"),
        CheckConstraint("score >= 0.0 AND score <= 1.0", name="ck_similarity_regime_score"),
        CheckConstraint("gap_days >= 30", name="ck_similarity_regime_min_gap"),
        UniqueConstraint("query_date", "rank", name="uq_similarity_regime_query_rank"),
    )

    query_date: Mapped[date] = mapped_column(Date, nullable=False)
    neighbor_date: Mapped[date] = mapped_column(Date, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    gap_days: Mapped[int] = mapped_column(Integer, nullable=False)
    built_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
