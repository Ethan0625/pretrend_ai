# Observability API Contract

## 1. API Purpose

The Observability API is the read-only runtime interface between Postgres serving tables and the Phase 3 dashboard.

The API answers:

- What is the current observed regime state for a date?
- Which historical dates are structurally similar?
- What macro and EOD values are available for a date or range?
- What cached explanation exists for a date and use case?
- Is the runtime healthy and what are the current watermarks?

The API does not answer:

- What should be bought or sold?
- What return is forecast?
- What target allocation or target price should be used?
- What action a broker or paper trading engine should take?

## 2. Auth

All `/api/v1/*` endpoints require an `X-API-Key` header.

| Item | Contract |
| --- | --- |
| Header | `X-API-Key` |
| Server env var | `PRETREND_API_KEY` |
| Missing key | `401 {"detail": "API key required"}` |
| Invalid key | `401 {"detail": "API key invalid"}` |
| Public endpoints | `/health`, `/docs`, `/openapi.json` |

P28 implementation returns `401` for missing or invalid keys. Future `403` behavior would require a contract update.

## 3. Endpoint Inventory

| Endpoint | Purpose | Consumer Page | Source Table | Read-only |
| --- | --- | --- | --- | --- |
| `GET /health` | Liveness and Alembic revision | Operations health monitor | app + Alembic | Yes |
| `GET /api/v1/meta` | Runtime table stats and watermarks | Operations health monitor | all serving tables | Yes |
| `GET /api/v1/regime` | Fixed-width regime feature for one date | Dashboard `/regime` | `gold_market_state_similarity_feature` | Yes |
| `GET /api/v1/regime/explain` | Cached regime explanation | Dashboard `/regime` explanation panel | `explainability_cache` | Yes |
| `GET /api/v1/similarity` | Top-N historical neighbors | Dashboard `/similarity` | `similarity_regime`, `similarity_gold` | Yes |
| `GET /api/v1/similarity/explain` | Cached similarity explanation | Dashboard `/similarity` explanation panel | `explainability_cache` | Yes |
| `GET /api/v1/macro` | Single macro indicator observation | Dashboard `/macro` | `gold_macro_features` | Yes |
| `GET /api/v1/macro/timeline` | Macro indicator timeline | Dashboard `/macro` chart | `gold_macro_features` | Yes |
| `GET /api/v1/macro/explain` | Cached macro explanation | Dashboard `/macro` explanation panel | `explainability_cache` | Yes |
| `GET /api/v1/eod` | Single EOD symbol observation | Dashboard `/eod` | `gold_eod_features` | Yes |
| `GET /api/v1/eod/timeline` | EOD symbol timeline | Dashboard `/eod` chart | `gold_eod_features` | Yes |

## 4. Endpoint Detail

### 4.1 `GET /health`

| Field | Value |
| --- | --- |
| Auth | No |
| Query params | None |
| Response schema | `{"status": "ok", "alembic": str}` |
| Date semantics | None |
| Error cases | Runtime failure if DB/Alembic cannot be checked |

Example response:

```json
{"status": "ok", "alembic": "0004"}
```

Invariant:

- Must not require `X-API-Key`.

### 4.2 `GET /api/v1/meta`

| Field | Value |
| --- | --- |
| Auth | `X-API-Key` |
| Query params | None |
| Response schema | `MetaResponse` |
| Nullable | max dates can be null for empty tables |
| Date semantics | Table watermarks reflect Postgres serving tables |
| Error cases | `401`, `500` |

Example response shape:

```json
{
  "alembic": "0004",
  "tables": {
    "gold_macro_features": {"row_count": 26106, "max_trade_date": "2026-05-13"},
    "similarity_regime": {"row_count": 576566, "max_query_date": "2026-05-13"}
  },
  "explainability_use_cases": {"regime": 1, "macro": 1}
}
```

Invariant:

- Must expose serving freshness without exposing API secrets.

### 4.3 `GET /api/v1/regime`

| Field | Value |
| --- | --- |
| Auth | `X-API-Key` |
| Query params | `trade_date: date` |
| Response schema | `RegimeResponse` |
| Nullable | feature values can be null |
| Date semantics | `trade_date` is the observed market state date |
| Error cases | `401`, `404`, `422`, `500` |

Example response shape:

```json
{
  "trade_date": "2026-05-13",
  "feature": {"mid_regime_code": 1, "risk_gate_flag": 1},
  "built_at": "2026-05-15T00:00:00Z"
}
```

Invariant:

- Feature fields are observations only. They are not trading decisions.

### 4.4 `GET /api/v1/regime/explain`

| Field | Value |
| --- | --- |
| Auth | `X-API-Key` |
| Query params | `trade_date: date` |
| Response schema | `ExplainResponse` |
| Nullable | report fields follow cached JSON schema |
| Date semantics | maps `trade_date` to `query_date` in `explainability_cache` |
| Error cases | `401`, `404`, `422`, `500` |

Example response shape:

```json
{
  "use_case": "regime",
  "query_date": "2026-05-13",
  "model_id": "mock",
  "prompt_version": "v1",
  "report": {"query_date": "2026-05-13", "ahs_summary": "관측 요약"},
  "built_at": "2026-05-15T00:00:00Z"
}
```

Invariant:

- The router must sanity-check forbidden prediction/recommendation terms before returning the report.

### 4.5 `GET /api/v1/similarity`

| Field | Value |
| --- | --- |
| Auth | `X-API-Key` |
| Query params | `query_date: date`, `view: regime\|gold`, `top_n: int = 10` |
| Response schema | `SimilarityResponse` |
| Nullable | none for row identity fields; scores/ranks are constrained by DB |
| Date semantics | `query_date` is the observed date whose historical neighbors are requested |
| Error cases | `401`, `404`, `422`, `500` |

Example response shape:

```json
{
  "query_date": "2026-05-13",
  "view": "regime",
  "neighbors": [
    {"neighbor_date": "2024-06-11", "score": 0.91, "rank": 1, "gap_days": 701}
  ]
}
```

Invariant:

- Similarity means historical comparison, not future prediction.

### 4.6 `GET /api/v1/similarity/explain`

| Field | Value |
| --- | --- |
| Auth | `X-API-Key` |
| Query params | `query_date: date`, `view: regime\|gold` |
| Response schema | `ExplainResponse` |
| Nullable | report fields follow cached JSON schema |
| Date semantics | `use_case` is `similarity_regime` or `similarity_gold` |
| Error cases | `401`, `404`, `422`, `500` |

Example response shape:

```json
{
  "use_case": "similarity_regime",
  "query_date": "2026-05-13",
  "model_id": "mock",
  "prompt_version": "v1",
  "report": {"summary": "과거 유사 구간의 공통 관측 특징을 요약했습니다."}
}
```

Invariant:

- Explanation text must stay evidence-bound to the similarity rows.

### 4.7 `GET /api/v1/macro`

| Field | Value |
| --- | --- |
| Auth | `X-API-Key` |
| Query params | `trade_date: date`, `indicator_id: str` |
| Response schema | `MacroResponse` |
| Nullable | macro feature fields can be null according to Gold contract |
| Date semantics | PIT-selected macro observation for `trade_date` |
| Error cases | `401`, `404`, `422`, `500` |

Example response shape:

```json
{
  "indicator_id": "CPI_US_ALL_ITEMS_SA",
  "trade_date": "2026-05-13",
  "selected_value": 320.0,
  "selected_release_date": "2026-05-12"
}
```

Invariant:

- `selected_release_date` must be earlier than `trade_date` when present.

### 4.8 `GET /api/v1/macro/timeline`

| Field | Value |
| --- | --- |
| Auth | `X-API-Key` |
| Query params | `indicator_id: str`, `start: date`, `end: date` |
| Response schema | `MacroTimelineResponse` |
| Nullable | row fields follow macro schema nullability |
| Date semantics | inclusive `start` and `end` over `trade_date` |
| Error cases | `401`, `404`, `422`, `500` |

Example response shape:

```json
{
  "indicator_id": "CPI_US_ALL_ITEMS_SA",
  "start": "2026-04-13",
  "end": "2026-05-13",
  "rows": [{"trade_date": "2026-05-13", "selected_value": 320.0}]
}
```

Invariant:

- Timeline must not synthesize unavailable future observations.

### 4.9 `GET /api/v1/macro/explain`

| Field | Value |
| --- | --- |
| Auth | `X-API-Key` |
| Query params | `trade_date: date` |
| Response schema | `ExplainResponse` |
| Nullable | report fields follow cached JSON schema |
| Date semantics | `use_case=macro`, `query_date=trade_date` |
| Error cases | `401`, `404`, `422`, `500` |

Example response shape:

```json
{
  "use_case": "macro",
  "query_date": "2026-05-13",
  "report": {"indicators": []}
}
```

Invariant:

- Macro explanation may describe current and historical macro observations only.

### 4.10 `GET /api/v1/eod`

| Field | Value |
| --- | --- |
| Auth | `X-API-Key` |
| Query params | `symbol: str`, `trade_date: date` |
| Response schema | `EodResponse` |
| Nullable | price and indicator fields follow EOD schema nullability |
| Date semantics | single symbol row at `trade_date` |
| Error cases | `401`, `404`, `422`, `500` |

Example response shape:

```json
{
  "symbol": "SPY",
  "trade_date": "2026-05-13",
  "adj_close": 600.0,
  "asset_name": "SP500"
}
```

Invariant:

- EOD response is an observation and must not imply action.

### 4.11 `GET /api/v1/eod/timeline`

| Field | Value |
| --- | --- |
| Auth | `X-API-Key` |
| Query params | `symbol: str`, `start: date`, `end: date` |
| Response schema | `EodTimelineResponse` |
| Nullable | row fields follow EOD schema nullability |
| Date semantics | inclusive `start` and `end` over `trade_date` |
| Error cases | `401`, `404`, `422`, `500` |

Example response shape:

```json
{
  "symbol": "SPY",
  "start": "2026-04-13",
  "end": "2026-05-13",
  "rows": [{"trade_date": "2026-05-13", "adj_close": 600.0}]
}
```

Invariant:

- Timeline endpoints return historical rows only.

## 5. Global Invariants

- All data endpoints are read-only.
- All `/api/v1/*` endpoints require `X-API-Key`.
- `trade_date` and `query_date` are observation dates, not prediction dates.
- Responses must not contain Personal Track decision fields.
- Responses must not contain prediction, recommendation, target price, target return, buy/sell, or trading guidance semantics.
- Not found data returns `404`; invalid query parameters return FastAPI `422`.
- API version prefix is `/api/v1/`.
- Any new endpoint requires a contract update before implementation.

## 6. Consumer Page Mapping

| Consumer Page | Endpoints |
| --- | --- |
| Operations health monitor | `/health`, `/api/v1/meta` |
| Dashboard `/regime` | `/api/v1/regime`, `/api/v1/regime/explain` |
| Dashboard `/similarity` | `/api/v1/similarity`, `/api/v1/similarity/explain` |
| Dashboard `/macro` | `/api/v1/macro`, `/api/v1/macro/timeline`, `/api/v1/macro/explain` |
| Dashboard `/eod` | `/api/v1/eod`, `/api/v1/eod/timeline` |

Consumer routes are Phase 3 placeholders. API contracts are stable enough for a dashboard client, but page composition can change in Phase 3 without changing endpoint semantics.

## 7. Change History

- 2026-05-15: Initial draft. P29-3.
