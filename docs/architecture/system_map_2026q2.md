# 시스템 맵 2026Q2

Markers: architecture, contract
Status: active

## 1. 한 줄 정의

Pretrend는 금융·거시 데이터를 재현 가능한 방식으로 수집·정제하고, PIT-safe macro/market feature layer를 구축하는 market data platform이다. Regime, similarity, explanation view, read-only dashboard는 이 feature layer를 소비하는 관측 표면이다.

## 2. Market Data Platform의 목적

현재 시스템은 investment recommendation engine이 아니다. 목적은 시장 판단 이전 단계에서 데이터 정합성, 시점 안전성, 재처리 가능성, 운영 재현성을 확보하고, 그 위에서 현재와 과거의 시장 구조를 관측 가능하고 설명 가능하게 만드는 것이다.

핵심 runtime 책임:

- Bronze, Silver, Gold feature layer를 canonical 형태로 생성한다.
- Point-in-time 안전성과 재처리 가능성을 data contract와 pytest gate로 검증한다.
- Dashboard serving에 필요한 Gold/Observability data를 Postgres로 mirror한다.
- 현재 시장 구조를 과거 상태와 비교한다.
- 기존 evidence에서 벗어나지 않는 한국어 설명을 cache한다.
- Local dashboard가 사용할 read-only API response를 제공한다.

명시적 제외 범위:

- 미래 수익률 예측.
- buy, sell, hold, target price, allocation guidance 생성.
- LLM output을 strategy, paper trading, broker execution에 입력하는 것.

## 3. 운영 영역 경계

Pretrend는 세 영역으로 운영한다.

| 영역 | 역할 | 주요 위치 | 상태 |
| --- | --- | --- | --- |
| Shared Infrastructure | Data ingestion, calendar, Bronze/Silver/Gold feature generation, Parquet SOT | `src/pretrend/pipeline/ingest/`, `src/pretrend/pipeline/features/`, `src/pretrend/pipeline/calendar/`, `data/` | 운영 |
| Observability Runtime | Regime, similarity, explainability, API, dashboard, Postgres serving schema | `src/pretrend/observability/`, `src/pretrend/api/`, `src/pretrend/models/`, `migrations/`, `docker/Dockerfile.api`, `apps/web/` | 현재 메인 |
| 보관된 전략 실험 | Strategy, backtest, paper, broker, Telegram automation asset | `src/pretrend/pipeline/strategy_engine/`, `src/pretrend/backtest/`, `src/pretrend/paper/`, `src/pretrend/broker/`, personal DAGs | 현재 공개 운영 표면 아님 |

경계 규칙:

- Observability Runtime은 Shared Infrastructure를 소비할 수 있다.
- 보관된 strategy experiment는 Shared Infrastructure를 소비할 수 있다.
- Observability Runtime과 archived strategy execution module은 서로 직접 import/depend하지 않는다.

P29 audit 참고:

- P29-1에서 일부 regime/similarity helper path에 `pretrend.pipeline.backtest._utils`, `pretrend.pipeline.strategy_engine.*` import가 남아 있음을 확인했다. 이는 hotfix 후보이며 새로 허용된 dependency가 아니다.

## 4. 시스템 구성요소

| 구성요소 | 역할 | 입력 | 출력 | 영역 | SOT 여부 | 비고 |
| --- | --- | --- | --- | --- | --- | --- |
| Source adapters | 공개 market/macro input 수집 | 외부 data source | Raw source record | Shared Infrastructure | 아니오 | 외부 API와 rate-limit 정책은 source별 문서에서 관리. |
| Bronze/Silver Pipeline | Raw input 정규화 | Source record | 정제된 Parquet layer | Shared Infrastructure | 아니오 | Observability와 archived strategy context가 공유. |
| Gold Parquet | Canonical PIT-safe feature layer | Silver data | Gold macro/EOD Parquet | Shared Infrastructure | 예 | Feature SOT. Postgres는 이를 mirror하며 역방향이 아니다. |
| Postgres Mirror | Query serving layer | Gold Parquet과 Observability output | Timescale/Postgres table | Observability Runtime | 아니오 | API, similarity, dashboard 조회 최적화. |
| Regime Feature Builder | Fixed-width market state feature 생성 | Regime axis, horizon, position, transition, rotation observations | `gold_market_state_similarity_feature` | Observability Runtime | 아니오 | Canonical regime similarity input. |
| Similarity Builder | Historical neighbor 계산 | `gold_market_state_similarity_feature`, `gold_macro_features`, `gold_eod_features` | `similarity_regime`, `similarity_gold` | Observability Runtime | 아니오 | 과거 비교 전용. |
| Explainability Cache | Bounded explanation JSON 저장 | Postgres evidence table | `explainability_cache` | Observability Runtime | 아니오 | Cache key는 `use_case + query_date + model_id + prompt_version`. |
| FastAPI | Read-only runtime API | Postgres serving table | `/api/v1/` JSON response | Observability Runtime | 아니오 | `/health`는 unauthenticated, data endpoint는 `X-API-Key` 필요. |
| Dashboard | 사람이 보는 market observability UI | FastAPI | Local visual view | Observability Runtime | 아니오 | Phase 3. Trading decision을 표시하면 안 된다. |
| 보관된 Strategy | 보관된 investing experiment asset | Gold와 strategy snapshot | Backtest, paper, broker, Telegram output | 보관 영역 | 아니오 | 신규 feature 추가 대상이 아니다. |

## 5. 데이터 흐름

Runtime data flow:

```text
Source
  -> Bronze
  -> Silver
  -> Gold Parquet SOT
  -> Postgres Mirror
  -> Similarity Builder
  -> Explainability Cache
  -> FastAPI
  -> Dashboard
```

Storage ownership:

- Gold Parquet은 canonical feature SOT다.
- Postgres는 serving copy와 Observability output을 저장한다.
- API는 Postgres만 읽는다.
- Dashboard는 API만 읽는다.

## 6. Runtime Job

KST 기준 일일 순서:

| 순서 | DAG | Schedule | 주요 출력 |
| ---: | --- | --- | --- |
| 1 | `eod_pipeline_dag` | `0 8 * * *` | Gold EOD Parquet |
| 2 | `macro_pipeline_dag` | `0 9 * * *` | Gold macro Parquet |
| 3 | `gold_postgres_sync_dag` | `0 11 * * *` | `gold_macro_features`, `gold_eod_features` |
| 4 | `similarity_build_dag` | `0 12 * * *` | `gold_market_state_similarity_feature`, `similarity_regime`, `similarity_gold` |
| 5 | `explainability_build_dag` | `0 13 * * *` | `explainability_cache` |

Freshness, failure propagation, recovery command는 [runtime_flow.md](./runtime_flow.md)를 참조한다.

## 7. 저장소 경계

| Store | 역할 | Write owner | Read consumer | 계약 |
| --- | --- | --- | --- | --- |
| Gold Parquet | Feature SOT | Shared Infrastructure DAG/job | Postgres sync, legacy consumer | `gold_design_contract.md`, `eod_observability_contract.md` |
| Postgres Gold mirror | SQL serving mirror | `gold_postgres_sync_dag`와 sync runner | API, similarity | `gold_postgres_schema.md`, `gold_postgres_sync.md` |
| Postgres similarity tables | Historical neighbor serving data | `similarity_build_dag` | API, explainability, dashboard | `similarity_design.md` |
| Postgres explainability cache | Bounded report cache | `explainability_build_dag`, explainer modules | API, dashboard | `explainability_design.md` |

향후 계약에서 ownership을 명시적으로 변경하지 않는 한, Postgres가 competing feature SOT가 되어서는 안 된다.

## 8. API 경계

FastAPI service는 read-only runtime interface다.

규칙:

- Phase 2 범위의 endpoint는 `GET`만 허용한다.
- 모든 `/api/v1/*` endpoint는 `X-API-Key`가 필요하다.
- `/health`, `/docs`, `/openapi.json`은 auth exception이다.
- API response는 archived strategy decision field를 포함하면 안 된다.
- Explainability response는 반환 전 sanitize한다.

Endpoint inventory와 dashboard mapping은 [../api/observability_api_contract.md](../api/observability_api_contract.md)를 참조한다.

## 9. LLM 경계

LLM layer는 Postgres에 이미 존재하는 evidence를 설명한다.

허용:

- 현재 관측된 market structure.
- Historical neighbor comparison.
- Macro condition narration.
- Evidence-bound Korean JSON report.

금지:

- Forecast 반환.
- Trade recommendation.
- Target price 또는 target return 생성.
- Buy, sell, trading signal semantic 생성.
- Explanation을 strategy, paper, broker, backtest execution에 다시 입력하는 것.

Historical full LLM backfill은 Phase 3에서 explanation scope/window/cache key 계약을 정하기 전까지 보류한다.

## 10. 보관 영역

보관된 strategy execution 영역:

- `src/pretrend/pipeline/strategy_engine/{allocation, policy_selector, sell_advisor, universe}`
- `src/pretrend/backtest/`
- `src/pretrend/paper/`
- `src/pretrend/broker/`
- `dags/strategy_engine_dag.py`
- `dags/paper_trading_dag.py`
- `dags/broker_mock_trading_dag.py`
- Telegram bot orchestration scripts.

규칙:

- 신규 strategy execution feature를 추가하지 않는다.
- Archived personal test는 보존한다.
- 불가피한 compatibility 또는 safety issue만 수정한다.
- Operational state는 service-stopped 상태를 유지한다.

P29 audit 참고:

- P29-2에서 일부 archived DAG가 `is_paused=False`로 등록되어 있음을 확인했다. 이는 운영 hotfix 대상이었다.

## 11. 확장 규칙

| 신규 작업 | 위치 |
| --- | --- |
| New market state observation | `src/pretrend/observability/regime/` |
| New similarity view 또는 operation | `src/pretrend/observability/similarity/` + contract update |
| New explanation prompt/use case | `src/pretrend/observability/explainability/` + prompt version policy |
| New read-only API route | `src/pretrend/api/routers/` + API contract update |
| New dashboard page | Phase 3 시작 후 `apps/web/` |
| New Postgres serving table | contract/migration plan 이후 `src/pretrend/models/`, `migrations/versions/` |
| New operational DAG | ownership과 recovery note를 포함해 `dags/` |
| New investing decision logic | Observability Runtime에서는 금지. 보관된 strategy execution 영역은 신규 기능 대상이 아니다. |

Grain, key, invariant, schema, public API를 건드리는 변경은 먼저 contract를 갱신해야 한다.

## 12. 현재 Phase 상태

| 영역 | 상태 |
| --- | --- |
| Phase 0 foundation | 완료 |
| Phase 1 Observability extraction | 완료, compatibility shim 유지 |
| Phase 2 code/data layer | 완료 |
| P29 Stage Gate | 완료 |
| P30 Runtime Preflight | 완료 |
| Phase 3 dashboard | 대기 |
| Cloudflare Tunnel | Local dashboard E2E 검증 전까지 보류 |

P24-P28 SOT index:

| Workstream | SOT |
| --- | --- |
| P24 Gold Postgres schema | [gold_postgres_schema.md](./gold_postgres_schema.md) |
| P25 Gold Postgres sync | [gold_postgres_sync.md](./gold_postgres_sync.md) |
| P26 Historical similarity | [similarity_design.md](./similarity_design.md) |
| P27 Explainability layer | [explainability_design.md](./explainability_design.md) |
| P28 Observability API | [api_design.md](./api_design.md) |

Phase 3에 영향을 주는 audit 산출물:

- Observability와 archived strategy execution 사이의 broad boundary cleanup은 계속 보호해야 한다.
- Strategy Engine compatibility shim export는 compatibility 범위로만 해석한다.
- Airflow audit command는 project `AIRFLOW_HOME`, project `PYTHONPATH`, project `DAGS_FOLDER`를 사용해야 한다.

## 13. 변경 이력

- 2026-05-15: 초안 작성. P29-3.
- 2026-05-16: 한국어 기준 문서로 정리하고 P30 상태 반영.
