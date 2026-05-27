import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { apiFetch, ApiError } from "./client";
import type {
  DateString,
  EodResponse,
  EodTimelineResponse,
  EventSimilarityResponse,
  ExplainResponse,
  HealthResponse,
  MacroResponse,
  MacroTimelineResponse,
  MetaResponse,
  RegimeResponse,
  RegimeTimelineResponse,
  SimilarityReplayResponse,
  SimilarityResponse,
  SimilarityView,
} from "./types";

type OptionalParam = string | null | undefined;

export function useHealth(): UseQueryResult<HealthResponse, ApiError> {
  return useQuery({
    queryKey: ["health"],
    queryFn: () => apiFetch<HealthResponse>("/health"),
  });
}

export function useMeta(): UseQueryResult<MetaResponse, ApiError> {
  return useQuery({
    queryKey: ["meta"],
    queryFn: () => apiFetch<MetaResponse>("/api/v1/meta"),
  });
}

export function useRegime(tradeDate: OptionalParam): UseQueryResult<RegimeResponse, ApiError> {
  return useQuery({
    queryKey: ["regime", tradeDate],
    queryFn: () => apiFetch<RegimeResponse>(withQuery("/api/v1/regime", { trade_date: tradeDate })),
    enabled: hasValue(tradeDate),
  });
}

export function useRegimeTimeline(
  start: OptionalParam,
  end: OptionalParam,
): UseQueryResult<RegimeTimelineResponse, ApiError> {
  return useQuery({
    queryKey: ["regime", "timeline", start, end],
    queryFn: () => apiFetch<RegimeTimelineResponse>(withQuery("/api/v1/regime/timeline", { start, end })),
    enabled: hasValue(start) && hasValue(end),
  });
}

export function useRegimeExplain(
  tradeDate: OptionalParam,
): UseQueryResult<ExplainResponse, ApiError> {
  return useQuery({
    queryKey: ["regimeExplain", tradeDate],
    queryFn: () =>
      apiFetch<ExplainResponse>(withQuery("/api/v1/regime/explain", { trade_date: tradeDate })),
    enabled: hasValue(tradeDate),
  });
}

export function useSimilarity(
  queryDate: OptionalParam,
  view: SimilarityView | null | undefined,
  topN = 10,
): UseQueryResult<SimilarityResponse, ApiError> {
  return useQuery({
    queryKey: ["similarity", queryDate, view, topN],
    queryFn: () =>
      apiFetch<SimilarityResponse>(
        withQuery("/api/v1/similarity", {
          query_date: queryDate,
          view,
          top_n: String(topN),
        }),
      ),
    enabled: hasValue(queryDate) && hasValue(view),
  });
}

export function useSimilarityEvents(
  queryDate: OptionalParam,
  enabled = true,
): UseQueryResult<EventSimilarityResponse, ApiError> {
  return useQuery({
    queryKey: ["similarity", "events", queryDate],
    queryFn: () => apiFetch<EventSimilarityResponse>(withQuery("/api/v1/similarity/events", { query_date: queryDate })),
    enabled: enabled && hasValue(queryDate),
  });
}

export function useSimilarityReplay(
  queryDate: OptionalParam,
  view: "events" | SimilarityView,
  symbol: string,
  enabled = true,
  topN = 5,
  compareDays = 60,
  forwardDays = 30,
  topAssets = 5,
  rankingSymbols: string[] = [],
): UseQueryResult<SimilarityReplayResponse, ApiError> {
  return useQuery({
    queryKey: [
      "similarity",
      "replay",
      queryDate,
      view,
      symbol,
      topN,
      compareDays,
      forwardDays,
      topAssets,
      rankingSymbols.join(","),
    ],
    queryFn: () =>
      apiFetch<SimilarityReplayResponse>(
        withQuery("/api/v1/similarity/replay", {
          query_date: queryDate,
          view,
          top_n: String(topN),
          compare_days: String(compareDays),
          forward_days: String(forwardDays),
          top_assets: String(topAssets),
          symbol,
          ranking_symbols: rankingSymbols.join(","),
        }),
      ),
    enabled: enabled && hasValue(queryDate) && hasValue(symbol),
  });
}

export function useSimilarityExplain(
  queryDate: OptionalParam,
  view: SimilarityView | null | undefined,
): UseQueryResult<ExplainResponse, ApiError> {
  return useQuery({
    queryKey: ["similarityExplain", queryDate, view],
    queryFn: () =>
      apiFetch<ExplainResponse>(
        withQuery("/api/v1/similarity/explain", {
          query_date: queryDate,
          view,
        }),
      ),
    enabled: hasValue(queryDate) && hasValue(view),
  });
}

export function useSimilarityEventsExplain(
  queryDate: OptionalParam,
  enabled = true,
): UseQueryResult<ExplainResponse, ApiError> {
  return useQuery({
    queryKey: ["similarityEventsExplain", queryDate],
    queryFn: () =>
      apiFetch<ExplainResponse>(withQuery("/api/v1/similarity/events/explain", { query_date: queryDate })),
    enabled: enabled && hasValue(queryDate),
  });
}

export function useMacro(
  tradeDate: OptionalParam,
  indicatorId: OptionalParam,
): UseQueryResult<MacroResponse, ApiError> {
  return useQuery({
    queryKey: ["macro", tradeDate, indicatorId],
    queryFn: () =>
      apiFetch<MacroResponse>(
        withQuery("/api/v1/macro", {
          trade_date: tradeDate,
          indicator_id: indicatorId,
        }),
      ),
    enabled: hasValue(tradeDate) && hasValue(indicatorId),
  });
}

export function useMacroTimeline(
  indicatorId: OptionalParam,
  start: OptionalParam,
  end: OptionalParam,
): UseQueryResult<MacroTimelineResponse, ApiError> {
  return useQuery({
    queryKey: ["macroTimeline", indicatorId, start, end],
    queryFn: () =>
      apiFetch<MacroTimelineResponse>(
        withQuery("/api/v1/macro/timeline", {
          indicator_id: indicatorId,
          start,
          end,
        }),
      ),
    enabled: hasValue(indicatorId) && hasValue(start) && hasValue(end),
  });
}

export function useMacroExplain(
  tradeDate: OptionalParam,
): UseQueryResult<ExplainResponse, ApiError> {
  return useQuery({
    queryKey: ["macroExplain", tradeDate],
    queryFn: () =>
      apiFetch<ExplainResponse>(withQuery("/api/v1/macro/explain", { trade_date: tradeDate })),
    enabled: hasValue(tradeDate),
  });
}

export function useEod(
  symbol: OptionalParam,
  tradeDate: OptionalParam,
): UseQueryResult<EodResponse, ApiError> {
  return useQuery({
    queryKey: ["eod", symbol, tradeDate],
    queryFn: () =>
      apiFetch<EodResponse>(
        withQuery("/api/v1/eod", {
          symbol,
          trade_date: tradeDate,
        }),
      ),
    enabled: hasValue(symbol) && hasValue(tradeDate),
  });
}

export function useEodTimeline(
  symbol: OptionalParam,
  start: OptionalParam,
  end: OptionalParam,
): UseQueryResult<EodTimelineResponse, ApiError> {
  return useQuery({
    queryKey: ["eodTimeline", symbol, start, end],
    queryFn: () =>
      apiFetch<EodTimelineResponse>(
        withQuery("/api/v1/eod/timeline", {
          symbol,
          start,
          end,
        }),
      ),
    enabled: hasValue(symbol) && hasValue(start) && hasValue(end),
  });
}

function withQuery(path: string, params: Record<string, string | number | null | undefined>): string {
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== "") {
      searchParams.set(key, String(value));
    }
  });
  const query = searchParams.toString();
  return query ? `${path}?${query}` : path;
}

function hasValue(value: OptionalParam | SimilarityView): value is DateString {
  return value !== null && value !== undefined && value !== "";
}
