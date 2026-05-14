from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, PrimaryKeyConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pretrend.models.base import Base
from pretrend.observability.similarity.columns import (
    CORE_FEATURE_COLUMNS,
    REGIME_SIMILARITY_FEATURE_COLUMNS,
    ROTATION_FEATURE_COLUMNS,
    TRANSITION_FEATURE_COLUMNS,
)


class GoldMarketStateSimilarityFeature(Base):
    """Canonical fixed-width market-state feature table for regime similarity."""

    __tablename__ = "gold_market_state_similarity_feature"
    __table_args__ = (
        PrimaryKeyConstraint(
            "trade_date",
            name="pk_gold_market_state_similarity_feature",
        ),
    )

    trade_date: Mapped[date] = mapped_column(Date, nullable=False)

    long_phase_expansion: Mapped[int | None] = mapped_column(Integer, nullable=True)
    long_phase_late_cycle: Mapped[int | None] = mapped_column(Integer, nullable=True)
    long_phase_slowdown: Mapped[int | None] = mapped_column(Integer, nullable=True)
    long_phase_recession: Mapped[int | None] = mapped_column(Integer, nullable=True)
    long_phase_recovery: Mapped[int | None] = mapped_column(Integer, nullable=True)
    long_phase_unknown: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mid_regime_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    short_signal_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    long_phase_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    mid_regime_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    short_signal_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    run_universe_flag: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_gate_flag: Mapped[int | None] = mapped_column(Integer, nullable=True)

    state_age_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    sojourn_prob_5d: Mapped[float | None] = mapped_column(Float, nullable=True)
    sojourn_prob_10d: Mapped[float | None] = mapped_column(Float, nullable=True)
    sojourn_prob_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    sojourn_prob_60d: Mapped[float | None] = mapped_column(Float, nullable=True)
    sojourn_prob_120d: Mapped[float | None] = mapped_column(Float, nullable=True)
    transition_hazard_5d: Mapped[float | None] = mapped_column(Float, nullable=True)
    transition_hazard_10d: Mapped[float | None] = mapped_column(Float, nullable=True)
    transition_hazard_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    transition_hazard_60d: Mapped[float | None] = mapped_column(Float, nullable=True)
    transition_hazard_120d: Mapped[float | None] = mapped_column(Float, nullable=True)

    rot_sp500_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_nasdaq100_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_dow30_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_us_dividend_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_russell2000_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_us_dividend_select_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_us_dividend_appreciation_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_south_korea_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_china_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_japan_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_india_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_gold_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_gold_miners_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_silver_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_crude_oil_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_oil_producers_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_natural_gas_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_agriculture_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_us_treasury_20y_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_us_high_yield_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_us_investment_grade_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_us_treasury_1_3y_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_us_tips_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_health_care_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_energy_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_semiconductor_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_financials_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_regional_banks_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_nuclear_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_information_tech_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_materials_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_consumer_discretionary_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_consumer_staples_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_communication_services_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_real_estate_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_utilities_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rot_industrials_state_code: Mapped[int | None] = mapped_column(Integer, nullable=True)

    built_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
