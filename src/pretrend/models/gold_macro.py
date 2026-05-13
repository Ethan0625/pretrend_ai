from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Date, Float, PrimaryKeyConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column

from pretrend.models.base import Base


class GoldMacroFeature(Base):
    """Gold macro feature mirror table."""

    __tablename__ = "gold_macro_features"
    __table_args__ = (
        PrimaryKeyConstraint(
            "indicator_id",
            "trade_date",
            name="pk_gold_macro_features",
        ),
        CheckConstraint(
            "selected_release_date < trade_date",
            name="ck_gold_macro_features_pit",
        ),
        CheckConstraint(
            "direction IN ('up','down','flat')",
            name="ck_gold_macro_features_direction",
        ),
        CheckConstraint(
            "regime IN ('tightening','easing','neutral')",
            name="ck_gold_macro_features_regime",
        ),
        CheckConstraint(
            "release_source IN ('econ_events','fred_vintages','assumed_t_plus_1')",
            name="ck_gold_macro_features_release_source",
        ),
    )

    indicator_id: Mapped[str] = mapped_column(Text, nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    selected_observation_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    selected_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    selected_release_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    delta_1m: Mapped[float | None] = mapped_column(Float, nullable=True)
    delta_3m: Mapped[float | None] = mapped_column(Float, nullable=True)
    delta_6m: Mapped[float | None] = mapped_column(Float, nullable=True)
    direction: Mapped[str | None] = mapped_column(Text, nullable=True)
    regime: Mapped[str | None] = mapped_column(Text, nullable=True)
    zscore_12m: Mapped[float | None] = mapped_column(Float, nullable=True)
    release_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_assumption_based: Mapped[bool] = mapped_column(Boolean, nullable=False)
