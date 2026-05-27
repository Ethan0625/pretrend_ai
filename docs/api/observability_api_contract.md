# Observability API 계약

Markers: contract, architecture
Status: active

## 1. API 목적

Observability API는 Postgres serving table과 Phase 3 dashboard 사이의 읽기 전용 runtime interface다.

API가 답하는 것:

- 특정 날짜의 관측 regime state.
- 구조적으로 유사한 과거 날짜.
- 특정 날짜 또는 기간의 macro/EOD 값.
- 특정 날짜와 use case에 대해 cache된 explanation.
- Runtime health와 현재 watermark.

API가 답하지 않는 것:

- 무엇을 사고팔아야 하는가.
- 어떤 수익률이 예측되는가.
- 어떤 target allocation 또는 target price를 사용해야 하는가.
- Broker 또는 paper trading engine이 어떤 action을 취해야 하는가.

## 2. 인증

모든 `/api/v1/*` endpoint는 `X-API-Key` header가 필요하다.

| 항목 | 계약 |
| --- | --- |
| Header | `X-API-Key` |
| Server env var | `PRETREND_API_KEY` |
| Missing key | `401 {"detail": "API key required"}` |
| Invalid key | `401 {"detail": "API key invalid"}` |
| Public endpoints | `/health`, `/docs`, `/openapi.json` |

P28 구현은 key가 없거나 invalid인 경우 `401`을 반환한다. 향후 `403` behavior를 쓰려면 contract update가 필요하다.

## 3. Endpoint 목록

| Endpoint | 목적 | Consumer Page | Source Table | Read-only |
| --- | --- | --- | --- | --- |
| `GET /health` | Liveness와 Alembic revision | 운영 health monitor | app + Alembic | Yes |
| `GET /api/v1/meta` | Runtime table stats와 watermark | 운영 health monitor | all serving tables | Yes |
| `GET /api/v1/regime` | 단일 날짜 fixed-width regime feature | Dashboard `/regime` | `gold_market_state_similarity_feature` | Yes |
| `GET /api/v1/regime/explain` | Cached regime explanation | Dashboard `/regime` explanation panel | `explainability_cache` | Yes |
| `GET /api/v1/similarity` | Top-N historical neighbor | Dashboard `/similarity` | `similarity_regime`, `similarity_gold` | Yes |
| `GET /api/v1/similarity/events` | 역사 이벤트 anchor 기준 regime similarity | Dashboard `/similarity` 이벤트 탭 | `gold_market_state_similarity_feature` | Yes |
| `GET /api/v1/similarity/events/explain` | Cached event similarity explanation | Dashboard `/similarity` explanation panel | `explainability_cache` (`similarity_events`) | Yes |
| `GET /api/v1/similarity/explain` | Cached date-neighbor similarity explanation | Legacy/manual 확인 | `explainability_cache` (`similarity_regime`, `similarity_gold`) | Yes |
| `GET /api/v1/macro` | 단일 macro indicator observation | Dashboard `/macro` | `gold_macro_features` | Yes |
| `GET /api/v1/macro/timeline` | Macro indicator timeline | Dashboard `/macro` chart | `gold_macro_features` | Yes |
| `GET /api/v1/macro/explain` | Cached macro explanation | Dashboard `/macro` explanation panel | `explainability_cache` | Yes |
| `GET /api/v1/eod` | 단일 EOD symbol observation | Dashboard `/eod` | `gold_eod_features` | Yes |
| `GET /api/v1/eod/timeline` | EOD symbol timeline | Dashboard `/eod` chart | `gold_eod_features` | Yes |

## 4. Endpoint 상세

### 4.1 `GET /health`

| 항목 | 값 |
| --- | --- |
| Auth | No |
| Query param | None |
| Response schema | `{"status": "ok", "alembic": str}` |
| Date semantic | None |
| Error case | Runtime failure if DB/Alembic cannot be checked |

응답 예시:

```json
{"status": "ok", "alembic": "0005"}
```

불변식:

- Must not require `X-API-Key`.

### 4.2 `GET /api/v1/meta`

| 항목 | 값 |
| --- | --- |
| Auth | `X-API-Key` |
| Query param | None |
| Response schema | `MetaResponse` |
| Nullable | max dates can be null for empty tables |
| Date semantic | Table watermarks reflect Postgres serving tables |
| Error case | `401`, `500` |

응답 예시 형태:

```json
{
  "alembic": "0005",
  "tables": {
    "gold_macro_features": {"row_count": 26106, "max_trade_date": "2026-05-13"},
    "similarity_regime": {"row_count": 576566, "max_query_date": "2026-05-13"}
  },
  "explainability_use_cases": {"regime": 1, "macro": 1}
}
```

불변식:

- Must expose serving freshness without exposing API secrets.

### 4.3 `GET /api/v1/regime`

| 항목 | 값 |
| --- | --- |
| Auth | `X-API-Key` |
| Query param | `trade_date: date` |
| Response schema | `RegimeResponse` |
| Nullable | feature values can be null |
| Date semantic | `trade_date` is the observed market state date |
| Error case | `401`, `404`, `422`, `500` |

응답 예시 형태:

```json
{
  "trade_date": "2026-05-13",
  "feature": {"mid_regime_code": 1, "risk_gate_flag": 1},
  "built_at": "2026-05-15T00:00:00Z"
}
```

불변식:

- Feature fields are observations only. They are not trading decisions.

### 4.4 `GET /api/v1/regime/explain`

| 항목 | 값 |
| --- | --- |
| Auth | `X-API-Key` |
| Query param | `trade_date: date` |
| Response schema | `ExplainResponse` |
| Nullable | report fields follow cached JSON schema |
| Date semantic | maps `trade_date` to `query_date` in `explainability_cache` |
| Error case | `401`, `404`, `422`, `500` |

응답 예시 형태:

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

불변식:

- The router must sanity-check forbidden prediction/recommendation terms before returning the report.

### 4.5 `GET /api/v1/similarity`

| 항목 | 값 |
| --- | --- |
| Auth | `X-API-Key` |
| Query param | `query_date: date`, `view: regime\|gold`, `top_n: int = 10` |
| Response schema | `SimilarityResponse` |
| Nullable | none for row identity fields; scores/ranks are constrained by DB |
| Date semantic | `query_date` is the observed date whose historical neighbors are requested |
| Error case | `401`, `404`, `422`, `500` |

응답 예시 형태:

```json
{
  "query_date": "2026-05-13",
  "view": "regime",
  "neighbors": [
    {"neighbor_date": "2024-06-11", "score": 0.91, "rank": 1, "gap_days": 701}
  ]
}
```

불변식:

- Similarity means historical comparison, not future prediction.

### 4.6 `GET /api/v1/similarity/events`

| 항목 | 값 |
| --- | --- |
| Auth | `X-API-Key` |
| Query param | `query_date: date` |
| Response schema | `EventSimilarityResponse` |
| Nullable | `actual_date`, `similarity_score` can be null when anchor row is unavailable |
| Date semantic | `query_date` is compared with fixed historical event anchors |
| Error case | `401`, `404`, `422`, `500` |

응답 예시 형태:

```json
{
  "query_date": "2026-05-20",
  "data": [
    {
      "event_name": "VIX 폭발",
      "anchor_date": "2018-02-05",
      "actual_date": "2018-02-05",
      "similarity_score": 0.25
    }
  ]
}
```

불변식:

- 기존 regime similarity와 같은 feature normalization을 사용한다.
- 사용자 노출 score는 `0.0~1.0`이며, raw cosine이 음수이면 `0.0`으로 clamp한다.

### 4.7 `GET /api/v1/similarity/events/explain`

| 항목 | 값 |
| --- | --- |
| Auth | `X-API-Key` |
| Query param | `query_date: date` |
| Response schema | `ExplainResponse` |
| Nullable | report fields follow cached JSON schema |
| Date semantic | `use_case=similarity_events` |
| Error case | `401`, `404`, `422`, `500` |

응답 예시 형태:

```json
{
  "use_case": "similarity_events",
  "query_date": "2026-05-20",
  "model_id": "vscode_codex",
  "prompt_version": "v1",
  "report": {"summary": "역사 이벤트 유사시기 관측 요약"}
}
```

불변식:

- Dashboard의 유사도 설명은 P32부터 이 endpoint를 사용한다.
- `similarity_score <= 0` 또는 source row가 없는 이벤트는 설명 report에서 제외한다.

### 4.8 `GET /api/v1/similarity/explain`

> Legacy/manual endpoint. Dashboard 설명 패널은 P32부터 `/api/v1/similarity/events/explain`을 사용한다.

| 항목 | 값 |
| --- | --- |
| Auth | `X-API-Key` |
| Query param | `query_date: date`, `view: regime\|gold` |
| Response schema | `ExplainResponse` |
| Nullable | report fields follow cached JSON schema |
| Date semantic | `use_case` is `similarity_regime` or `similarity_gold` |
| Error case | `401`, `404`, `422`, `500` |

응답 예시 형태:

```json
{
  "use_case": "similarity_regime",
  "query_date": "2026-05-13",
  "model_id": "mock",
  "prompt_version": "v1",
  "report": {"summary": "과거 유사 구간의 공통 관측 특징을 요약했습니다."}
}
```

불변식:

- Explanation text must stay evidence-bound to the similarity rows.

### 4.9 `GET /api/v1/macro`

| 항목 | 값 |
| --- | --- |
| Auth | `X-API-Key` |
| Query param | `trade_date: date`, `indicator_id: str` |
| Response schema | `MacroResponse` |
| Nullable | macro feature fields can be null according to Gold contract |
| Date semantic | PIT-selected macro observation for `trade_date` |
| Error case | `401`, `404`, `422`, `500` |

응답 예시 형태:

```json
{
  "indicator_id": "CPI_US_ALL_ITEMS_SA",
  "trade_date": "2026-05-13",
  "selected_value": 320.0,
  "selected_release_date": "2026-05-12"
}
```

불변식:

- `selected_release_date` must be earlier than `trade_date` when present.

### 4.10 `GET /api/v1/macro/timeline`

| 항목 | 값 |
| --- | --- |
| Auth | `X-API-Key` |
| Query param | `indicator_id: str`, `start: date`, `end: date` |
| Response schema | `MacroTimelineResponse` |
| Nullable | row fields follow macro schema nullability |
| Date semantic | inclusive `start` and `end` over `trade_date` |
| Error case | `401`, `404`, `422`, `500` |

응답 예시 형태:

```json
{
  "indicator_id": "CPI_US_ALL_ITEMS_SA",
  "start": "2026-04-13",
  "end": "2026-05-13",
  "rows": [{"trade_date": "2026-05-13", "selected_value": 320.0}]
}
```

불변식:

- Timeline must not synthesize unavailable future observations.

### 4.11 `GET /api/v1/macro/explain`

| 항목 | 값 |
| --- | --- |
| Auth | `X-API-Key` |
| Query param | `trade_date: date` |
| Response schema | `ExplainResponse` |
| Nullable | report fields follow cached JSON schema |
| Date semantic | `use_case=macro`, `query_date=trade_date` |
| Error case | `401`, `404`, `422`, `500` |

응답 예시 형태:

```json
{
  "use_case": "macro",
  "query_date": "2026-05-13",
  "report": {"indicators": []}
}
```

불변식:

- Macro explanation may describe current and historical macro observations only.

### 4.12 `GET /api/v1/eod`

| 항목 | 값 |
| --- | --- |
| Auth | `X-API-Key` |
| Query param | `symbol: str`, `trade_date: date` |
| Response schema | `EodResponse` |
| Nullable | price and indicator fields follow EOD schema nullability |
| Date semantic | single symbol row at `trade_date` |
| Error case | `401`, `404`, `422`, `500` |

응답 예시 형태:

```json
{
  "symbol": "SPY",
  "trade_date": "2026-05-13",
  "adj_close": 600.0,
  "asset_name": "SP500"
}
```

불변식:

- EOD response is an observation and must not imply action.

### 4.13 `GET /api/v1/eod/timeline`

| 항목 | 값 |
| --- | --- |
| Auth | `X-API-Key` |
| Query param | `symbol: str`, `start: date`, `end: date` |
| Response schema | `EodTimelineResponse` |
| Nullable | row fields follow EOD schema nullability |
| Date semantic | inclusive `start` and `end` over `trade_date` |
| Error case | `401`, `404`, `422`, `500` |

응답 예시 형태:

```json
{
  "symbol": "SPY",
  "start": "2026-04-13",
  "end": "2026-05-13",
  "rows": [{"trade_date": "2026-05-13", "adj_close": 600.0}]
}
```

불변식:

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
| Dashboard `/similarity` | `/api/v1/similarity`, `/api/v1/similarity/events`, `/api/v1/similarity/events/explain` |
| Dashboard `/macro` | `/api/v1/macro`, `/api/v1/macro/timeline`, `/api/v1/macro/explain` |
| Dashboard `/eod` | `/api/v1/eod`, `/api/v1/eod/timeline` |

Consumer routes are Phase 3 placeholders. API contracts are stable enough for a dashboard client, but page composition can change in Phase 3 without changing endpoint semantics.

## 7. 변경 이력

- 2026-05-21: P32 기준 역사 이벤트 유사도와 `similarity_events` 설명 endpoint 추가. Alembic 예시는 `0005`.
- 2026-05-15: 초안 작성. P29-3.
