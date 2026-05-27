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

P28은 11 endpoints로 시작했다. P32에서 regime timeline, 역사 이벤트 유사도, 이벤트 유사도 설명 endpoint가 추가되었다. P35에서 유사 구간 이후 궤적을 묶어 반환하는 replay endpoint가 추가되었다. Dashboard의 유사도 설명은 P32부터 날짜 Top-N 설명이 아니라 `similarity_events` cache를 읽는다.

| # | method | path | auth | source |
| --- | --- | --- | --- | --- |
| 1 | GET | `/health` | no | app + alembic |
| 2 | GET | `/api/v1/meta` | yes | alembic + table stats |
| 3 | GET | `/api/v1/regime?trade_date=YYYY-MM-DD` | yes | `gold_market_state_similarity_feature` |
| 4 | GET | `/api/v1/regime/explain?trade_date=YYYY-MM-DD` | yes | `explainability_cache` |
| 5 | GET | `/api/v1/similarity?query_date=YYYY-MM-DD&view=regime\|gold&top_n=10` | yes | `similarity_regime` / `similarity_gold` |
| 6 | GET | `/api/v1/similarity/events?query_date=YYYY-MM-DD` | yes | `gold_market_state_similarity_feature` |
| 7 | GET | `/api/v1/similarity/replay?query_date=YYYY-MM-DD&view=events&top_n=5&symbol=SPY` | yes | `gold_market_state_similarity_feature` / `similarity_regime` / `similarity_gold` + `gold_eod_features` |
| 8 | GET | `/api/v1/similarity/events/explain?query_date=YYYY-MM-DD` | yes | `explainability_cache` (`similarity_events`) |
| legacy | GET | `/api/v1/similarity/explain?query_date=YYYY-MM-DD&view=regime\|gold` | yes | `explainability_cache` (`similarity_regime`, `similarity_gold`) |
| 9 | GET | `/api/v1/macro?trade_date=YYYY-MM-DD&indicator_id=...` | yes | `gold_macro_features` |
| 10 | GET | `/api/v1/macro/timeline?indicator_id=...&start=YYYY-MM-DD&end=YYYY-MM-DD` | yes | `gold_macro_features` |
| 11 | GET | `/api/v1/macro/explain?trade_date=YYYY-MM-DD` | yes | `explainability_cache` |
| 12 | GET | `/api/v1/eod?symbol=...&trade_date=YYYY-MM-DD` | yes | `gold_eod_features` |
| 13 | GET | `/api/v1/eod/timeline?symbol=...&start=YYYY-MM-DD&end=YYYY-MM-DD` | yes | `gold_eod_features` |

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
{"status": "ok", "alembic": "0005"}
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
  "alembic": "0005",
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
    use_case: Literal["similarity_regime", "similarity_gold", "similarity_events", "regime", "macro"]
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

### GET /api/v1/similarity/replay

Query params:

- `query_date: date`
- `view: Literal["events", "regime", "gold"]`
- `top_n: int = 5`, 허용 범위 `1~10`
- `compare_days: int = 60`, 허용 범위 `0~180`
- `forward_days: int = 30`, 허용 범위 `1~180`
- `top_assets: int = 5`, 허용 범위 `1~10`
- `symbol: str = "SPY"`: 화면에서 선택한 단일 자산 식별자
- `ranking_symbols: str | None`: Asset Name별 trajectory 유사도 ranking 계산용 symbol 목록, 최대 60개

추가 제약:

- `compare_days + forward_days <= 365`

응답 모델:

```python
class ReplayPathPoint(BaseModel):
    trade_date: date
    day_offset: int
    adj_close: float | None
    normalized_return: float | None

class ReplayAssetPath(BaseModel):
    symbol: str
    asset_name: str
    asset_group: str | None
    base_date: date | None
    base_adj_close: float | None
    points: list[ReplayPathPoint]

class ReplayAssetRanking(BaseModel):
    symbol: str
    asset_name: str
    asset_group: str | None
    trajectory_similarity_score: float | None

class ReplayAssetOverlay(BaseModel):
    symbol: str
    asset_name: str
    asset_group: str | None
    trajectory_similarity_score: float | None
    current_path: ReplayAssetPath
    historical_path: ReplayAssetPath

class ReplayTrajectory(BaseModel):
    label: str
    event_name: str | None
    anchor_date: date
    actual_date: date
    rank: int
    state_similarity_score: float
    trajectory_similarity_score: float | None
    compare_start: date
    compare_end: date
    window_start: date
    window_end: date
    current_path: ReplayAssetPath
    historical_path: ReplayAssetPath
    overlay_assets: list[ReplayAssetOverlay]
    asset_rankings: list[ReplayAssetRanking]

class SimilarityReplayResponse(BaseModel):
    query_date: date
    view: Literal["events", "regime", "gold"]
    symbol: str
    asset_name: str
    compare_days: int
    forward_days: int
    trajectories: list[ReplayTrajectory]
```

`view=events`는 역사 이벤트 anchor를, `view=regime|gold`는 기존 Top-N 유사 날짜의 `neighbor_date`를 historical anchor로 사용한다. 응답은 선택한 단일 `symbol`의 현재 비교 구간(`query_date - compare_days ~ query_date`)과 과거 표시 구간(`actual_date - compare_days ~ actual_date + forward_days`)을 같은 `day_offset` 축으로 정렬해 반환한다. 각 경로는 anchor일의 `adj_close`를 기준으로 `normalized_return = adj_close / base_adj_close - 1`로 정규화한다.

`state_similarity_score`는 feature 상태 유사도이며, `trajectory_similarity_score`는 `D-compare_days ~ D` 구간의 현재 자산 궤적과 과거 자산 궤적을 비교한 normalized return cosine 유사도다. `D+1 ~ D+forward_days`는 유사도 계산에 쓰지 않고 과거 이후 관측 구간으로만 반환한다. `overlay_assets`는 Top Asset Name의 과거 궤적 overlay, `asset_rankings`는 같은 anchor에서 Asset Name별 trajectory 유사도를 비교하기 위한 보조 ranking이다. 이 endpoint는 과거 유사 구간에서 관측된 흐름을 보여주기 위한 read model이며, 예측/전망 값을 만들지 않는다. anchor가 없으면 `404`와 함께 `reason="not_yet_built"`, `latest_available` 힌트를 반환한다.

### GET /api/v1/similarity/events

Query params:

- `query_date: date`

응답 모델:

```python
class EventSimilarityItem(BaseModel):
    event_name: str
    anchor_date: date
    actual_date: date | None
    similarity_score: float | None

class EventSimilarityResponse(BaseModel):
    query_date: date
    data: list[EventSimilarityItem]
```

역사 이벤트 anchor와 현재 `gold_market_state_similarity_feature` row를 기존 regime similarity와 같은 normalization으로 비교한다. 사용자 노출 score는 `0.0~1.0`이며 음수 raw cosine은 `0.0`으로 clamp한다.

### GET /api/v1/similarity/events/explain

Query params:

- `query_date: date`

`use_case=similarity_events`로 매핑한다. Dashboard의 유사도 설명 패널은 이 endpoint를 사용한다.

응답 모델: `ExplainResponse`.

### GET /api/v1/similarity/explain

Legacy/manual endpoint. Dashboard 설명 패널은 P32부터 `/api/v1/similarity/events/explain`을 사용한다.

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

- 2026-05-21: P32 이벤트 유사도 endpoint와 `similarity_events` 설명 cache를 반영. Alembic 예시는 `0005`.
- 2026-05-14: P28-1 초안 작성. API version=0.1.0. 금지 prefix/term set: `predicted_`, `forecast_`, `recommend_`, `should_buy_`, `target_price`, `target_return`, `buy_signal`, `sell_signal`, `trading_signal`.
