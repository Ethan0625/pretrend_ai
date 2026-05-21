from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    detail: str
    resource: str | None = None
    query: dict[str, Any] | None = None
    request_id: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    alembic: str


class MetaTableInfo(BaseModel):
    row_count: int
    max_trade_date: date | None = None
    max_query_date: date | None = None


class MetaResponse(BaseModel):
    alembic: str
    tables: dict[str, MetaTableInfo]
    explainability_use_cases: dict[str, int] = Field(default_factory=dict)


class RegimeResponse(BaseModel):
    trade_date: date
    feature: dict[str, int | float | str | None]
    built_at: datetime


class SimilarityNeighbor(BaseModel):
    neighbor_date: date
    rank: int
    score: float
    gap_days: int


class SimilarityResponse(BaseModel):
    query_date: date
    view: Literal["regime", "gold"]
    neighbors: list[SimilarityNeighbor]


class MacroFeature(BaseModel):
    indicator_id: str
    trade_date: date
    selected_observation_date: date | None = None
    selected_value: float | None = None
    selected_release_date: date | None = None
    delta_1m: float | None = None
    delta_3m: float | None = None
    delta_6m: float | None = None
    direction: str | None = None
    regime: str | None = None
    zscore_12m: float | None = None
    release_source: str | None = None
    is_assumption_based: bool


class MacroResponse(BaseModel):
    data: MacroFeature


class MacroTimelineResponse(BaseModel):
    indicator_id: str
    start: date
    end: date
    data: list[MacroFeature]


class EodFeature(BaseModel):
    symbol: str
    trade_date: date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    adj_close: float | None = None
    volume: int | None = None
    currency: str | None = None
    ret_1d: float | None = None
    ret_5d: float | None = None
    ret_20d: float | None = None
    vol_20d: float | None = None
    vol_60d: float | None = None
    is_trading_day: bool
    asset_group: str
    asset_name: str


class EodResponse(BaseModel):
    data: EodFeature


class EodTimelineResponse(BaseModel):
    symbol: str
    start: date
    end: date
    data: list[EodFeature]


class ExplainResponse(BaseModel):
    use_case: Literal["similarity_regime", "similarity_gold", "regime", "macro"]
    query_date: date
    model_id: str
    prompt_version: str
    report: dict[str, Any]
    built_at: datetime


class StrategyReportAnalyzeRequest(BaseModel):
    payload: dict[str, Any]
    model: str | None = None
    base_url: str | None = None
    timeout: int | None = None


class StrategyReportAnalyzeResponse(BaseModel):
    analysis_text: str | None = None


class ExplainabilityAnalyzeRequest(BaseModel):
    system_prompt: str
    user_prompt: str
    timeout: int | None = None


class ExplainabilityAnalyzeResponse(BaseModel):
    raw_text: str | None = None
