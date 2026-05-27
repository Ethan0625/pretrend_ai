export type DateString = string;
export type DateTimeString = string;

export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };

export interface ErrorResponse {
  detail: string;
  resource?: string | null;
  query?: Record<string, JsonValue> | null;
  reason?: string | null;
  latest_available?: DateString | null;
  request_id?: string | null;
}

export interface HealthResponse {
  status: "ok";
  alembic: string;
}

export interface MetaTableInfo {
  row_count: number;
  max_trade_date?: DateString | null;
  max_query_date?: DateString | null;
}

export interface MetaResponse {
  alembic: string;
  tables: Record<string, MetaTableInfo>;
  explainability_use_cases: Record<string, number>;
}

export type RegimeFeatureValue = string | number | null;
export type RegimeFeature = Record<string, RegimeFeatureValue>;

export interface RegimeResponse {
  trade_date: DateString;
  feature: RegimeFeature;
  built_at: DateTimeString;
}

export interface RegimeTimelineResponse {
  start: DateString;
  end: DateString;
  data: RegimeResponse[];
}

export type SimilarityView = "regime" | "gold";

export interface SimilarityNeighbor {
  neighbor_date: DateString;
  rank: number;
  score: number;
  gap_days: number;
}

export interface SimilarityResponse {
  query_date: DateString;
  view: SimilarityView;
  neighbors: SimilarityNeighbor[];
}

export interface EventSimilarityItem {
  event_name: string;
  anchor_date: DateString;
  actual_date: DateString | null;
  similarity_score: number | null;
}

export interface EventSimilarityResponse {
  query_date: DateString;
  data: EventSimilarityItem[];
}

export interface MacroFeature {
  indicator_id: string;
  trade_date: DateString;
  selected_observation_date?: DateString | null;
  selected_value?: number | null;
  selected_release_date?: DateString | null;
  delta_1m?: number | null;
  delta_3m?: number | null;
  delta_6m?: number | null;
  direction?: string | null;
  regime?: string | null;
  zscore_12m?: number | null;
  release_source?: string | null;
  is_assumption_based: boolean;
}

export interface MacroResponse {
  data: MacroFeature;
}

export interface MacroTimelineResponse {
  indicator_id: string;
  start: DateString;
  end: DateString;
  data: MacroFeature[];
}

export interface EodFeature {
  symbol: string;
  trade_date: DateString;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  close?: number | null;
  adj_close?: number | null;
  volume?: number | null;
  currency?: string | null;
  ret_1d?: number | null;
  ret_5d?: number | null;
  ret_20d?: number | null;
  vol_20d?: number | null;
  vol_60d?: number | null;
  is_trading_day: boolean;
  asset_group: string;
  asset_name: string;
}

export interface EodResponse {
  data: EodFeature;
}

export interface EodTimelineResponse {
  symbol: string;
  start: DateString;
  end: DateString;
  data: EodFeature[];
}

export type ExplainUseCase = "similarity_regime" | "similarity_gold" | "similarity_events" | "regime" | "macro";

export interface ExplainResponse {
  use_case: ExplainUseCase;
  query_date: DateString;
  model_id: string;
  prompt_version: string;
  report: Record<string, JsonValue>;
  built_at: DateTimeString;
}
