# Observability API 설계

Markers: architecture, contract
Status: active

> P28 SOT. 본 문서는 Observability Track의 최소 read-only FastAPI 진입점을 정의한다.

## 1. 목적과 불변식

API는 Postgres에 적재된 Observability 데이터를 Phase 3 dashboard와 로컬 운영자가 조회할 수 있게 하는 외부 진입점이다. P28은 read-only 범위이며 `GET` endpoint만 허용한다.

핵심 불변식:

- API 출력은 관측 전용이다. 예측, 추천, 주문 조언, 목표 가격, 목표 수익률 의미를 제공하지 않는다.
- explainability 응답은 cached `report_json`을 반환하기 직전에 최종 sanity check를 실행한다.
- 금지 prefix/term set: `predicted_`, `forecast_`, `recommend_`, `should_buy_`, `target_price`, `target_return`, `buy_signal`, `sell_signal`, `trading_signal`.
- API version prefix는 `/api/v1/`이다.
- `/health`는 unversioned이며 request auth만 bypass한다.
- `PRETREND_API_KEY`는 app creation/startup 시점에 필수다.

## 2. 인증 정책

모든 `/api/v1/*` endpoint는 `X-API-Key` header를 요구한다. 서버의 기준 key는 `PRETREND_API_KEY`에서 읽는다.

정책:

- app creation/startup 시 `PRETREND_API_KEY`가 없으면 startup error로 실패한다.
- 요청 header가 없으면 `401 {"detail": "API key required"}`를 반환한다.
- 요청 header가 기준 key와 다르면 `401 {"detail": "API key invalid"}`를 반환한다.
- `/health`, `/docs`, `/openapi.json`은 request header를 요구하지 않는다.

테스트는 `PRETREND_API_KEY`를 주입한 뒤 app을 생성해야 한다. app factory 경로 외의 임의 module import 시점에서 `APISettings()`를 직접 평가하지 않는다.

## 3. CORS와 Trusted Hosts

환경 변수:

| env var | default | 의미 |
| --- | --- | --- |
| `PRETREND_API_KEY` | 필수 | `X-API-Key` 검증에 사용하는 API key |
| `PRETREND_API_CORS_ORIGINS` | empty | Phase 3 dashboard용 허용 origin, comma-separated |
| `PRETREND_API_TRUSTED_HOSTS` | `*` | 허용 host 목록, comma-separated |

CORS default는 외부 origin 없음이다. `TrustedHostMiddleware`는 `PRETREND_API_TRUSTED_HOSTS`를 사용한다. 로컬 개발 default는 `*`이며, 운영 hardening task에서 도메인 기준으로 좁힐 수 있다.

## 4. Versioning

- `/health`는 unversioned liveness endpoint다.
- 모든 데이터 endpoint는 `/api/v1/` 아래에 둔다.
- 향후 `/api/v2/`를 도입하려면 별도 contract update와 v1 deprecation plan이 필요하다.

## 5. 응답과 에러 표준

모든 응답은 JSON이며 Pydantic response model로 검증한다.

표준 에러:

```json
{"detail": "API key required"}
```

```json
{"detail": "API key invalid"}
```

```json
{"detail": "Not found", "resource": "regime", "query": {"trade_date": "2026-05-12"}}
```

처리하지 못한 generic error는 아래 형식으로 반환한다.

```json
{"detail": "Internal server error", "request_id": "uuid"}
```

잘못된 query parameter는 FastAPI default `422` validation response를 유지한다.

## 6. OpenAPI 메타데이터

- title: `Pretrend Observability API`
- description: `Read-only API for market structure observability (regime / similarity / macro / EOD / explainability)`
- version: `0.1.0`
- tags: `health`, `meta`, `regime`, `similarity`, `macro`, `eod`, `explain`

Swagger UI는 `/docs`에서 제공한다.

## 7. Endpoint 요약

P28은 11 endpoints를 정의한다. P28-4 smoke 검증은 12 calls를 사용한다. 이유는 `/api/v1/similarity/explain`을 `view=regime`, `view=gold`로 각각 한 번씩 호출하기 때문이다.

| # | method | path | auth | source |
| --- | --- | --- | --- | --- |
| 1 | GET | `/health` | no | app + alembic |
| 2 | GET | `/api/v1/meta` | yes | alembic + table stats |
| 3 | GET | `/api/v1/regime?trade_date=YYYY-MM-DD` | yes | `gold_market_state_similarity_feature` |
| 4 | GET | `/api/v1/regime/explain?trade_date=YYYY-MM-DD` | yes | `explainability_cache` |
| 5 | GET | `/api/v1/similarity?query_date=YYYY-MM-DD&view=regime\|gold&top_n=10` | yes | `similarity_regime` / `similarity_gold` |
| 6 | GET | `/api/v1/similarity/explain?query_date=YYYY-MM-DD&view=regime\|gold` | yes | `explainability_cache` |
| 7 | GET | `/api/v1/macro?trade_date=YYYY-MM-DD&indicator_id=...` | yes | `gold_macro_features` |
| 8 | GET | `/api/v1/macro/timeline?indicator_id=...&start=YYYY-MM-DD&end=YYYY-MM-DD` | yes | `gold_macro_features` |
| 9 | GET | `/api/v1/macro/explain?trade_date=YYYY-MM-DD` | yes | `explainability_cache` |
| 10 | GET | `/api/v1/eod?symbol=...&trade_date=YYYY-MM-DD` | yes | `gold_eod_features` |
| 11 | GET | `/api/v1/eod/timeline?symbol=...&start=YYYY-MM-DD&end=YYYY-MM-DD` | yes | `gold_eod_features` |

## 8. Endpoint Schema

### GET /health

응답 모델:

```python
class HealthResponse(BaseModel):
    status: Literal["ok"]
    alembic: str
```

예시:

```json
{"status": "ok", "alembic": "0004"}
```

### GET /api/v1/meta

응답 모델:

```python
class MetaTableInfo(BaseModel):
    row_count: int
    max_trade_date: date | None = None
    max_query_date: date | None = None

class MetaResponse(BaseModel):
    alembic: str
    tables: dict[str, MetaTableInfo]
    explainability_use_cases: dict[str, int]
```

예시:

```json
{
  "alembic": "0004",
  "tables": {
    "gold_macro_features": {"row_count": 26101, "max_trade_date": "2026-05-12"},
    "similarity_regime": {"row_count": 800, "max_query_date": "2026-05-12"}
  },
  "explainability_use_cases": {"regime": 1, "macro": 1}
}
```

### GET /api/v1/regime

Query params:

- `trade_date: date`

응답 모델:

```python
class RegimeResponse(BaseModel):
    trade_date: date
    feature: dict[str, int | float | str | None]
    built_at: datetime
```

예시:

```json
{
  "trade_date": "2026-05-12",
  "feature": {"mid_regime_code": 1, "short_signal_code": 0},
  "built_at": "2026-05-14T00:00:00Z"
}
```

해당 row가 없으면 `404`를 반환한다.

### GET /api/v1/regime/explain

Query params:

- `trade_date: date`

응답 모델:

```python
class ExplainResponse(BaseModel):
    use_case: Literal["similarity_regime", "similarity_gold", "regime", "macro"]
    query_date: date
    model_id: str
    prompt_version: str
    report: dict[str, Any]
    built_at: datetime
```

예시:

```json
{
  "use_case": "regime",
  "query_date": "2026-05-12",
  "model_id": "vscode_codex",
  "prompt_version": "v1",
  "report": {"query_date": "2026-05-12", "ahs_summary": "관측 요약"},
  "built_at": "2026-05-14T00:00:00Z"
}
```

라우터는 반환 직전에 `report`에 대해 금지 표현 sanity check를 실행한다. cache miss는 `404`, invariant violation은 `500`을 반환한다.

### GET /api/v1/similarity

Query params:

- `query_date: date`
- `view: Literal["regime", "gold"]`
- `top_n: int = 10`, `1 <= top_n <= 100`

응답 모델:

```python
class SimilarityNeighbor(BaseModel):
    neighbor_date: date
    rank: int
    score: float
    gap_days: int

class SimilarityResponse(BaseModel):
    query_date: date
    view: Literal["regime", "gold"]
    neighbors: list[SimilarityNeighbor]
```

예시:

```json
{
  "query_date": "2026-05-12",
  "view": "regime",
  "neighbors": [{"neighbor_date": "2024-06-03", "rank": 1, "score": 0.91, "gap_days": 708}]
}
```

neighbor가 없으면 `404`를 반환한다. 잘못된 `view` 또는 `top_n`은 `422`를 반환한다.

### GET /api/v1/similarity/explain

Query params:

- `query_date: date`
- `view: Literal["regime", "gold"]`

`view=regime`은 `use_case=similarity_regime`으로, `view=gold`는 `use_case=similarity_gold`로 매핑한다.

응답 모델: `ExplainResponse`.

예시:

```json
{
  "use_case": "similarity_regime",
  "query_date": "2026-05-12",
  "model_id": "vscode_codex",
  "prompt_version": "v1",
  "report": {"summary": "유사 구간 관측 요약"},
  "built_at": "2026-05-14T00:00:00Z"
}
```

### GET /api/v1/macro

Query params:

- `trade_date: date`
- `indicator_id: str`

응답 모델:

```python
class MacroFeature(BaseModel):
    indicator_id: str
    trade_date: date
    selected_observation_date: date | None
    selected_value: float | None
    selected_release_date: date | None
    delta_1m: float | None
    delta_3m: float | None
    delta_6m: float | None
    direction: str | None
    regime: str | None
    zscore_12m: float | None
    release_source: str | None
    is_assumption_based: bool

class MacroResponse(BaseModel):
    data: MacroFeature
```

예시:

```json
{
  "data": {
    "indicator_id": "CPI_US_ALL_ITEMS_SA",
    "trade_date": "2026-05-12",
    "selected_value": 313.2,
    "delta_3m": 0.4,
    "regime": "tightening",
    "is_assumption_based": false
  }
}
```

해당 row가 없으면 `404`를 반환한다.

### GET /api/v1/macro/timeline

Query params:

- `indicator_id: str`
- `start: date`
- `end: date`

`end - start`는 최대 730일이다.

응답 모델:

```python
class MacroTimelineResponse(BaseModel):
    indicator_id: str
    start: date
    end: date
    data: list[MacroFeature]
```

예시:

```json
{"indicator_id": "CPI_US_ALL_ITEMS_SA", "start": "2025-01-01", "end": "2026-05-12", "data": []}
```

730일을 넘는 범위는 `422`를 반환한다.

### GET /api/v1/macro/explain

Query params:

- `trade_date: date`

`use_case=macro`로 매핑한다. 응답 모델은 `ExplainResponse`다.

### GET /api/v1/eod

Query params:

- `symbol: str`
- `trade_date: date`

응답 모델:

```python
class EodFeature(BaseModel):
    symbol: str
    trade_date: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    adj_close: float | None
    volume: int | None
    currency: str | None
    ret_1d: float | None
    ret_5d: float | None
    ret_20d: float | None
    vol_20d: float | None
    vol_60d: float | None
    is_trading_day: bool
    asset_group: str
    asset_name: str

class EodResponse(BaseModel):
    data: EodFeature
```

예시:

```json
{
  "data": {
    "symbol": "SPY",
    "trade_date": "2026-05-12",
    "adj_close": 500.1,
    "ret_1d": 0.002,
    "asset_group": "SP500",
    "asset_name": "SPY",
    "is_trading_day": true
  }
}
```

해당 row가 없으면 `404`를 반환한다.

### GET /api/v1/eod/timeline

Query params:

- `symbol: str`
- `start: date`
- `end: date`

`end - start`는 최대 730일이다.

응답 모델:

```python
class EodTimelineResponse(BaseModel):
    symbol: str
    start: date
    end: date
    data: list[EodFeature]
```

예시:

```json
{"symbol": "SPY", "start": "2025-01-01", "end": "2026-05-12", "data": []}
```

## 9. 구현 위치

P28은 `apps/api/`가 아니라 `src/pretrend/api/`를 사용한다.

근거:

1. 11 endpoints가 모두 `pretrend.models.*` ORM class를 직접 사용한다.
2. `track_separation.md`는 현재 배포 구조를 microservice split이 아닌 monolith로 유지한다.
3. repository에는 이미 `dags/`, `scripts/` 같은 top-level runtime folder가 존재한다.
4. Phase 3 `apps/web/`는 별도 React surface이며 Python API 위치와 직접 결합하지 않는다.
5. 단일 개발자 / 로컬 docker-compose 배포에서는 작은 package boundary가 낫다.
6. 향후 협업 구조에서 분리가 필요하면 `git mv`로 되돌릴 수 있다.

라우터 모듈:

- 총 7 routers: `health`, `meta`, `regime`, `similarity`, `macro`, `eod`, `explain`.
- P28-3에서 추가하는 router modules는 6개다: `meta`, `regime`, `similarity`, `macro`, `eod`, `explain`.

## 10. 후속 범위

P28의 명시적 out-of-scope:

- React dashboard 통합.
- `POST` / `PUT` / `DELETE` / `PATCH` endpoint.
- WebSocket / Server-Sent Events.
- LLM 호출. API는 `explainability_cache`만 읽는다.
- OAuth / SSO / JWT.
- Rate limiting.
- Cloudflare, cloudflared, tunnel 설정, 예시, 운영 등록. 이는 로컬 dashboard 검증 이후 Phase 3 이후의 별도 운영 task다.
- Bronze / Silver / text API.
- 사용자 입력 chat agent.

## 11. 변경 이력

- 2026-05-14: P28-1 초안 작성. API version=0.1.0. 금지 prefix/term set: `predicted_`, `forecast_`, `recommend_`, `should_buy_`, `target_price`, `target_return`, `buy_signal`, `sell_signal`, `trading_signal`.
