# Pretrend 시스템 개요

Markers: architecture, operation
Status: active

## 1. 한 줄 요약

Pretrend는 금융·거시 데이터를 재현 가능한 방식으로 수집·정제하고, PIT-safe macro/market feature layer를 구축하는 market data platform이다. Regime, historical similarity, explanation, read-only API는 이 데이터 플랫폼 위의 관측 표면이다.

## 2. 목적 / 비전

현재 프로젝트 목표는 투자 자동화가 아니라 시장 판단 이전 단계의 데이터 정합성, 시점 안전성, 재처리 가능성, 운영 재현성을 확보하는 것이다.

Pretrend가 관측하는 것:

- 재현 가능한 Bronze/Silver/Gold data lineage.
- PIT-safe macro/EOD feature layer.
- 현재 regime state.
- 현재 시장 구조와 유사했던 과거 날짜.
- 특정 날짜 주변의 macro/EOD context.
- evidence 기반 한국어 설명.
- runtime freshness와 health.

Pretrend가 제공하지 않는 것:

- 매수, 매도, 보유, allocation guidance.
- forecast 또는 target return.
- broker 또는 paper trading instruction.
- LLM이 생성한 strategy input.

우선 참조 문서:

- [docs/architecture/system_map_2026q2.md](architecture/system_map_2026q2.md)
- [docs/architecture/boundary_contract.md](architecture/boundary_contract.md)
- [docs/architecture/runtime_flow.md](architecture/runtime_flow.md)

## 3. Phase 진행 상황

| 단계 | 상태 | 비고 |
| --- | --- | --- |
| Phase 0 | 완료 | Docker Postgres, config, models, Alembic foundation. |
| Phase 1 | 완료 | `src/pretrend/observability/regime/` 하위 regime observation module 정리 및 compatibility shim 유지. |
| Phase 2 | 완료 | Gold Postgres mirror, sync DAG, similarity, explainability, FastAPI read-only API. |
| P29 Stage Gate | 완료 | code audit, operation audit, architecture docs, legacy consolidation, final checklist. |
| P30 Runtime Preflight | 완료 | Docker runtime, DB volume/restore contract, Airflow 2 profile, one-shot backfill, 격리 test DB, 새 머신 runbook. |
| Phase 3 | 대기 | React dashboard 구현 가능. |
| Cloudflare Tunnel | 보류 | local dashboard E2E 검증 이후 별도 판단. |

현재 기준:

- API와 Postgres compose service는 healthy 상태를 기준으로 운영한다.
- P29 audit 시점 serving table은 `2026-05-13`까지 populate되어 있었다.
- Runtime 재현성 작업에는 API/Postgres/Airflow Docker Compose profile과 새 머신용 restore/backfill contract가 포함된다.

## 4. 현재 운영 범위 / 보관 범위

| 영역 | 역할 | 현재 운영 여부 | 주요 경로 |
| --- | --- | --- | --- |
| Shared Infrastructure | Bronze/Silver/Gold data pipeline, calendar/PIT foundation | 예 | `src/pretrend/pipeline/ingest/`, `src/pretrend/pipeline/features/`, `src/pretrend/pipeline/calendar/`, `data/` |
| Observability Runtime | Regime, similarity, explainability, API, dashboard | 예 | `src/pretrend/observability/`, `src/pretrend/api/`, `src/pretrend/models/`, `migrations/`, `apps/web/` |
| 보관된 전략 실험 | Strategy, backtest, paper, broker, Telegram automation asset | 현재 공개 운영 표면 아님 | `src/pretrend/pipeline/strategy_engine/`, `src/pretrend/backtest/`, `src/pretrend/paper/`, `src/pretrend/broker/`, archived tests |

의존성 규칙:

```text
Observability Runtime -> Shared Infrastructure
보관된 전략 실험 -> Shared Infrastructure
Observability Runtime -X-> archived strategy execution modules
```

## 5. 데이터 흐름

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

저장소 경계:

- Gold Parquet은 feature SOT다.
- Postgres는 API, similarity, dashboard를 위한 serving mirror/cache다.
- FastAPI는 Postgres만 읽으며 read-only다.
- Dashboard는 FastAPI만 읽으며 observation-only여야 한다.

## 6. 운영 시간대 (KST)

| DAG | Schedule | 역할 |
| --- | --- | --- |
| `eod_pipeline_dag` | `0 8 * * *` | Gold EOD Parquet 생성. |
| `macro_pipeline_dag` | `0 9 * * *` | Gold macro Parquet 생성. |
| `strategy_engine_dag` | `0 10 * * *` | optional archived strategy-report DAG. 명시 테스트 때만 unpause. |
| `gold_postgres_sync_dag` | `0 11 * * *` | Gold Parquet을 Postgres로 mirror. |
| `similarity_build_dag` | `0 12 * * *` | regime/gold historical similarity table 생성. |
| `explainability_build_dag` | `0 13 * * *` | cached explanation report 생성. |

운영 참고:

- Airflow CLI command는 project `AIRFLOW_HOME`, project `PYTHONPATH`, project `DAGS_FOLDER`를 사용해야 한다. 그렇지 않으면 기본 `~/airflow` metadata DB를 볼 수 있다.
- 보관된 strategy/report DAG는 bounded compatibility test가 필요한 경우에만 unpause한다.

상세 runtime flow:

- [docs/architecture/runtime_flow.md](architecture/runtime_flow.md)

## 7. API 진입

Observability API는 Phase 3 dashboard의 backend surface다.

| Endpoint group | Auth | 목적 |
| --- | --- | --- |
| `/health` | 없음 | Liveness와 Alembic revision 확인. |
| `/api/v1/meta` | `X-API-Key` | Table row count와 watermark. |
| `/api/v1/regime*` | `X-API-Key` | Regime feature와 cached regime explanation. |
| `/api/v1/similarity*` | `X-API-Key` | Historical similarity Top-N과 cached explanation. |
| `/api/v1/macro*` | `X-API-Key` | Macro point/timeline과 cached explanation. |
| `/api/v1/eod*` | `X-API-Key` | EOD point/timeline. |

전체 계약:

- [docs/api/observability_api_contract.md](api/observability_api_contract.md)

## 8. 문서 진입 가이드

권장 읽기 순서:

1. 이 문서, [docs/system_overview.md](system_overview.md): 전체 entry point.
2. [docs/architecture/system_map_2026q2.md](architecture/system_map_2026q2.md): 전체 system map.
3. [docs/architecture/runtime_flow.md](architecture/runtime_flow.md): DAG order, freshness, recovery.
4. [docs/architecture/boundary_contract.md](architecture/boundary_contract.md): dependency boundary와 보관 영역 경계.
5. [docs/api/observability_api_contract.md](api/observability_api_contract.md): API client 작업 기준.
6. [docs/testing/operational_invariant_test_contract.md](testing/operational_invariant_test_contract.md): test marker와 invariant check.
7. [docs/operation/reproducible_runtime_contract.md](operation/reproducible_runtime_contract.md): Docker runtime, DB volume, backup/restore, 새 머신 검증.
8. Area SOT:
   - [docs/architecture/gold_postgres_schema.md](architecture/gold_postgres_schema.md)
   - [docs/architecture/gold_postgres_sync.md](architecture/gold_postgres_sync.md)
   - [docs/architecture/similarity_design.md](architecture/similarity_design.md)
   - [docs/architecture/explainability_design.md](architecture/explainability_design.md)
   - [docs/architecture/api_design.md](architecture/api_design.md)

보관된 전략 실험 개요:

- [docs/legacy/personal_track_overview.md](legacy/personal_track_overview.md)

## 9. Phase 3 진입 조건

다음 조건을 기준으로 Phase 3 React Dashboard 구현에 진입한다.

- [x] `system_map_2026q2.md` 작성 완료 (P29-3)
- [x] `runtime_flow.md` 작성 완료 (P29-3)
- [x] `boundary_contract.md` 작성 완료 (P29-3)
- [x] `observability_api_contract.md` 최소 endpoint inventory 완료 (P29-3, 11 logical endpoint)
- [x] `operational_invariant_test_contract.md` 작성 완료 (P29-3)
- [x] pytest marker 추가 (P29-4)
- [x] Phase 3 진입 전 pytest command 정의 (P29-3)
- [x] Observability runtime boundary dependency 점검 (P29-1, broader boundary hotfix backlog 포함)
- [x] Gold Parquet SOT / Postgres Mirror 구분 문서화 (P24-1 + P29 system map)

Phase 3 구현 전 runtime readiness는 [`docs/operation/reproducible_runtime_contract.md`](operation/reproducible_runtime_contract.md)를 기준으로 판단한다.

## 10. 변경 이력

- 2026-05-15: Observability Runtime entry point로 재작성. 이전 strategy experiment overview는 `docs/legacy/personal_track_overview.md`로 이동. P29-4.
- 2026-05-15: Phase 3 entry checklist 추가 및 P29 Stage Gate 완료 표시. P29-5.
- 2026-05-16: P30 runtime preflight 상태와 공개 문서 표현 정리.
