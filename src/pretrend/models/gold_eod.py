from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Float, PrimaryKeyConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column

from pretrend.models.base import Base


class GoldEodFeature(Base):
    """Gold EOD feature mirror table."""

    __tablename__ = "gold_eod_features"
    __table_args__ = (
        PrimaryKeyConstraint(
            "symbol",
            "trade_date",
            name="pk_gold_eod_features",
        ),
    )

    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    close: Mapped[float | None] = mapped_column(Float, nullable=True)
    adj_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str | None] = mapped_column(Text, nullable=True)
    prev_adj_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    ret_1d: Mapped[float | None] = mapped_column(Float, nullable=True)
    log_ret_1d: Mapped[float | None] = mapped_column(Float, nullable=True)
    ret_5d: Mapped[float | None] = mapped_column(Float, nullable=True)
    ret_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    vol_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    vol_60d: Mapped[float | None] = mapped_column(Float, nullable=True)
    ma_5: Mapped[float | None] = mapped_column(Float, nullable=True)
    ma_20: Mapped[float | None] = mapped_column(Float, nullable=True)
    ma_60: Mapped[float | None] = mapped_column(Float, nullable=True)
    ma_120: Mapped[float | None] = mapped_column(Float, nullable=True)
    ma_ratio_5_20: Mapped[float | None] = mapped_column(Float, nullable=True)
    atr_14: Mapped[float | None] = mapped_column(Float, nullable=True)
    rsi_14: Mapped[float | None] = mapped_column(Float, nullable=True)
    intraday_range: Mapped[float | None] = mapped_column(Float, nullable=True)
    gap_open: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_zscore_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_trading_day: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_missing_imputed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_outlier: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_partial_day: Mapped[bool] = mapped_column(Boolean, nullable=False)
    asset_group: Mapped[str] = mapped_column(Text, nullable=False)
    asset_name: Mapped[str] = mapped_column(Text, nullable=False)
    asset_subtype: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_id_gold: Mapped[str] = mapped_column(Text, nullable=False)
    ingestion_ts_gold: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
