# Pretrend AI System Overview

Markers: architecture, operation
Status: active

## 1. 한 줄 요약

Pretrend AI is a Market Structure Observability Runtime: a local system that turns PIT-safe macro and market features into regime, historical similarity, explanation, and read-only API views.

## 2. 목적 / 비전

The active project goal is market structure observation, not investment automation.

Pretrend observes:

- Current regime state.
- Historical dates with similar market structure.
- Macro and EOD context around a date.
- Evidence-bound Korean explanations.
- Runtime freshness and health.

Pretrend does not provide:

- Buy, sell, hold, or allocation guidance.
- Forecasts or target returns.
- Broker or paper trading instructions.
- LLM-generated strategy inputs.

Primary references:

- [docs/architecture/track_separation.md](architecture/track_separation.md)
- [docs/architecture/system_map_2026q2.md](architecture/system_map_2026q2.md)
- [docs/architecture/boundary_contract.md](architecture/boundary_contract.md)

## 3. Phase 진행 상황

| Phase | Status | Notes |
| --- | --- | --- |
| Phase 0 | Done | Docker Postgres, config, models, Alembic foundation. |
| Phase 1 | Done | Regime observation modules extracted under `src/pretrend/observability/regime/` with compatibility shims. |
| Phase 2 | Done | Gold Postgres mirror, sync DAG, similarity, explainability, FastAPI read-only API. |
| P29 Stage Gate | Done | Code audit, operations audit, architecture docs, legacy consolidation, final checklist. |
| P30 Runtime Preflight | Pending | Reproducible Docker runtime, DB volume/restore contract, dev/test image, agent docs publication safety. |
| Phase 3 | Pending | React dashboard can start with P29 hotfix backlog tracked separately. |
| Cloudflare Tunnel | Deferred | Only after local dashboard E2E is validated. |

Current baseline:

- API and Postgres compose services are healthy.
- Serving tables are populated through `2026-05-13` at P29 audit time.
- P29 follow-up hotfix resolved broader runtime Observability boundary imports, shim package exports, and Personal DAG paused-state drift.

## 4. Two-Track 구조 요약

| Area | Role | Active? | Main paths |
| --- | --- | --- | --- |
| Shared Infrastructure | Bronze/Silver/Gold data pipeline and calendar/PIT foundation | Yes | `src/pretrend/pipeline/ingest/`, `src/pretrend/pipeline/features/`, `src/pretrend/pipeline/calendar/`, `data/` |
| Observability Track | Regime, similarity, explainability, API, dashboard | Yes | `src/pretrend/observability/`, `src/pretrend/api/`, `src/pretrend/models/`, `migrations/`, `apps/web/` |
| Personal Track | Strategy, backtest, paper, broker, Telegram automation assets | Frozen, service-stopped by contract | `src/pretrend/pipeline/strategy_engine/`, `src/pretrend/backtest/`, `src/pretrend/paper/`, `src/pretrend/broker/`, personal DAGs |

Dependency rule:

```text
Observability Track -> Shared Infrastructure
Personal Track Frozen -> Shared Infrastructure
Observability Track -X-> Personal Track
Personal Track -X-> Observability Track
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

Storage boundary:

- Gold Parquet is the feature SOT.
- Postgres is the serving mirror/cache for API, similarity, and dashboard.
- FastAPI reads Postgres and is read-only.
- Dashboard reads FastAPI and must remain observation-only.

## 6. 운영 시간대 (KST)

| DAG | Schedule | Role |
| --- | --- | --- |
| `eod_pipeline_dag` | `0 8 * * *` | Build Gold EOD Parquet. |
| `macro_pipeline_dag` | `0 9 * * *` | Build Gold macro Parquet. |
| `strategy_engine_dag` | `0 10 * * *` | Personal Track legacy DAG, frozen and should be paused. |
| `gold_postgres_sync_dag` | `0 11 * * *` | Mirror Gold Parquet to Postgres. |
| `similarity_build_dag` | `0 12 * * *` | Build regime/gold historical similarity tables. |
| `explainability_build_dag` | `0 13 * * *` | Build cached explanation reports. |

Operational note:

- Airflow CLI commands must use the project `AIRFLOW_HOME`, project `PYTHONPATH`, and project `DAGS_FOLDER`; otherwise the CLI can inspect the default `~/airflow` metadata DB.
- P29 follow-up hotfix paused the three Personal DAGs in project Airflow metadata. Keep them paused unless a future Personal Track reactivation task is explicitly approved.

Detailed runtime flow:

- [docs/architecture/runtime_flow.md](architecture/runtime_flow.md)

## 7. API 진입

The Observability API is the backend surface for Phase 3 dashboard work.

| Endpoint group | Auth | Purpose |
| --- | --- | --- |
| `/health` | No | Liveness and Alembic revision. |
| `/api/v1/meta` | `X-API-Key` | Table row counts and watermarks. |
| `/api/v1/regime*` | `X-API-Key` | Regime feature and cached regime explanation. |
| `/api/v1/similarity*` | `X-API-Key` | Historical similarity Top-N and cached explanation. |
| `/api/v1/macro*` | `X-API-Key` | Macro point/timeline and cached explanation. |
| `/api/v1/eod*` | `X-API-Key` | EOD point/timeline. |

Full contract:

- [docs/api/observability_api_contract.md](api/observability_api_contract.md)

## 8. 문서 진입 가이드

Read in this order:

1. This file, [docs/system_overview.md](system_overview.md), for the entry point.
2. [docs/architecture/system_map_2026q2.md](architecture/system_map_2026q2.md), for the full system map.
3. [docs/architecture/runtime_flow.md](architecture/runtime_flow.md), for DAG order, freshness, and recovery.
4. [docs/architecture/boundary_contract.md](architecture/boundary_contract.md), for dependency and frozen-track boundaries.
5. [docs/api/observability_api_contract.md](api/observability_api_contract.md), for API client work.
6. [docs/testing/operational_invariant_test_contract.md](testing/operational_invariant_test_contract.md), for test markers and invariant checks.
7. [docs/operation/reproducible_runtime_contract.md](operation/reproducible_runtime_contract.md), for Docker runtime, DB volume, backup/restore, and new-machine verification.
8. [docs/architecture/track_separation.md](architecture/track_separation.md), for the Two-Track decision.
9. Area SOTs:
   - [docs/architecture/gold_postgres_schema.md](architecture/gold_postgres_schema.md)
   - [docs/architecture/gold_postgres_sync.md](architecture/gold_postgres_sync.md)
   - [docs/architecture/similarity_design.md](architecture/similarity_design.md)
   - [docs/architecture/explainability_design.md](architecture/explainability_design.md)
   - [docs/architecture/api_design.md](architecture/api_design.md)

Legacy overview:

- [docs/legacy/personal_track_overview.md](legacy/personal_track_overview.md) preserves the pre-2026Q2 Personal Track overview.

## 9. Phase 3 진입 조건

다음 조건을 기준으로 Phase 3 React Dashboard 구현에 진입한다.

- [x] `system_map_2026q2.md` 작성 완료 (P29-3)
- [x] `runtime_flow.md` 작성 완료 (P29-3)
- [x] `boundary_contract.md` 작성 완료 (P29-3)
- [x] `observability_api_contract.md` 최소 endpoint inventory 완료 (P29-3, 11 logical endpoint)
- [x] `operational_invariant_test_contract.md` 작성 완료 (P29-3)
- [x] pytest marker 추가 (P29-4)
- [x] Phase 3 진입 전 pytest command 정의 (P29-3)
- [x] Observability -> Personal Track 금지 dependency 점검 (P29-1, broader boundary hotfix backlog 포함)
- [x] Gold Parquet SOT / Postgres Mirror 구분 문서화 (P24-1 + P29 system map)

Phase 3 구현 전 hotfix backlog는 `.agent/TASK_QUEUE.md`의 P29 backlog를 기준으로 판단한다.

## 10. 변경 이력

- 2026-05-15: Rewritten as Observability Runtime entry point. Previous Personal Track overview moved to `docs/legacy/personal_track_overview.md`. P29-4.
- 2026-05-15: Added Phase 3 entry checklist and marked P29 Stage Gate done. P29-5.
