# System Map 2026Q2

## 1. One-line Definition

Pretrend AI is a market structure observability runtime that turns PIT-safe macro and market features into regime, similarity, and explanation views for a read-only dashboard.

## 2. Why Observability Runtime

The current system is not an investment recommendation engine. Its purpose is to make the current and historical market structure observable, reproducible, and explainable.

Core runtime responsibilities:

- Build canonical Bronze, Silver, and Gold feature layers.
- Mirror dashboard-serving Gold and Observability data into Postgres.
- Compare current market structure against historical states.
- Cache bounded Korean-language explanations from existing evidence.
- Expose read-only API responses for local dashboard use.

Non-goals:

- Predicting future returns.
- Creating buy, sell, hold, target price, or allocation guidance.
- Feeding LLM output into strategy, paper trading, or broker execution.

## 3. Track Boundary

Pretrend is operated as three explicit areas.

| Track | Role | Primary locations | Status |
| --- | --- | --- | --- |
| Shared Infrastructure | Data ingestion, calendar, Bronze/Silver/Gold feature generation, Parquet SOT | `src/pretrend/pipeline/ingest/`, `src/pretrend/pipeline/features/`, `src/pretrend/pipeline/calendar/`, `data/` | Operational |
| Observability Track | Regime, similarity, explainability, API, dashboard, Postgres serving schema | `src/pretrend/observability/`, `src/pretrend/api/`, `src/pretrend/models/`, `migrations/`, `Dockerfile.api`, `apps/web/` | Main track |
| Personal Track Frozen | Strategy, backtest, paper, broker, Telegram automation assets | `src/pretrend/pipeline/strategy_engine/`, `src/pretrend/backtest/`, `src/pretrend/paper/`, `src/pretrend/broker/`, personal DAGs | Frozen and service-stopped by contract |

Boundary rule:

- Observability can consume Shared Infrastructure.
- Personal can consume Shared Infrastructure.
- Observability and Personal must not import or depend on each other directly.

Known P29 audit note:

- P29-1 found broader Observability imports of `pretrend.pipeline.backtest._utils` and `pretrend.pipeline.strategy_engine.*` in some regime/similarity helper paths. This is a hotfix candidate, not a new allowed dependency.

## 4. System Components

| Component | Role | Input | Output | Track | SOT | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Source adapters | Pull public market and macro inputs | External data sources | Raw source records | Shared Infrastructure | No | External API and rate-limit policy belongs to source-specific docs. |
| Bronze/Silver Pipeline | Normalize raw inputs | Source records | Cleaned Parquet layers | Shared Infrastructure | No | Shared by Observability and frozen Personal assets. |
| Gold Parquet | Canonical PIT-safe feature layer | Silver data | Gold macro and EOD Parquet | Shared Infrastructure | Yes | Feature SOT. Postgres mirrors this, not the reverse. |
| Postgres Mirror | Query serving layer | Gold Parquet and Observability outputs | Timescale/Postgres tables | Observability | No | Read-optimized for API, similarity, and dashboard. |
| Regime Feature Builder | Build fixed-width market state features | Regime axis, horizon, position, transition, rotation observations | `gold_market_state_similarity_feature` | Observability | No | Canonical regime similarity input. |
| Similarity Builder | Compute historical neighbors | `gold_market_state_similarity_feature`, `gold_macro_features`, `gold_eod_features` | `similarity_regime`, `similarity_gold` | Observability | No | Historical comparison only. |
| Explainability Cache | Store bounded explanation JSON | Postgres evidence tables | `explainability_cache` | Observability | No | Cache key is `use_case + query_date + model_id + prompt_version`. |
| FastAPI | Read-only runtime API | Postgres serving tables | JSON responses under `/api/v1/` | Observability | No | `/health` is unauthenticated; data endpoints require `X-API-Key`. |
| Dashboard | Human market observability UI | FastAPI | Local visual views | Observability | No | Phase 3. Must not present trading decisions. |
| Personal Track | Preserved investing experiment assets | Gold and strategy snapshots | Backtest, paper, broker, Telegram outputs | Personal Frozen | No | No new features. Operational services should remain stopped. |

## 5. Data Flow

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

- Gold Parquet remains the canonical feature SOT.
- Postgres stores serving copies and Observability outputs.
- API reads Postgres only.
- Dashboard reads API only.

## 6. Runtime Jobs

Daily order, KST:

| Order | DAG | Schedule | Main output |
| ---: | --- | --- | --- |
| 1 | `eod_pipeline_dag` | `0 8 * * *` | Gold EOD Parquet |
| 2 | `macro_pipeline_dag` | `0 9 * * *` | Gold macro Parquet |
| 3 | `gold_postgres_sync_dag` | `0 11 * * *` | `gold_macro_features`, `gold_eod_features` |
| 4 | `similarity_build_dag` | `0 12 * * *` | `gold_market_state_similarity_feature`, `similarity_regime`, `similarity_gold` |
| 5 | `explainability_build_dag` | `0 13 * * *` | `explainability_cache` |

See [runtime_flow.md](./runtime_flow.md) for freshness, failure propagation, and recovery commands.

## 7. Storage Boundary

| Store | Role | Write owner | Read consumers | Contract |
| --- | --- | --- | --- | --- |
| Gold Parquet | Feature SOT | Shared Infrastructure DAGs/jobs | Postgres sync, legacy consumers | `gold_design_contract.md`, `eod_observability_contract.md` |
| Postgres Gold mirror | SQL serving mirror | `gold_postgres_sync_dag` and sync runner | API, similarity | `gold_postgres_schema.md`, `gold_postgres_sync.md` |
| Postgres similarity tables | Historical neighbor serving data | `similarity_build_dag` | API, explainability, dashboard | `similarity_design.md` |
| Postgres explainability cache | Bounded report cache | `explainability_build_dag`, explainer modules | API, dashboard | `explainability_design.md` |

Postgres is not allowed to become a competing feature SOT unless a future contract explicitly changes ownership.

## 8. API Boundary

The FastAPI service is a read-only runtime interface.

Rules:

- Only `GET` endpoints are in scope for Phase 2.
- All `/api/v1/*` endpoints require `X-API-Key`.
- `/health`, `/docs`, and `/openapi.json` are auth exceptions.
- API responses must not include Personal Track decision fields.
- Explainability responses are sanitized before return.

Endpoint inventory and dashboard mapping live in [../api/observability_api_contract.md](../api/observability_api_contract.md).

## 9. LLM Boundary

The LLM layer explains evidence that already exists in Postgres.

Allowed:

- Current observed market structure.
- Historical neighbor comparison.
- Macro condition narration.
- Evidence-bound Korean JSON reports.

Forbidden:

- Return forecasts.
- Recommend trades.
- Generate target prices or target returns.
- Create buy, sell, or trading signal semantics.
- Feed explanations back into strategy, paper, broker, or backtest execution.

Historical full LLM backfill is deferred until Phase 3 defines whether explanations are snapshot, rolling-window, or full-history-to-date scoped.

## 10. Frozen Areas

Frozen Personal Track areas:

- `src/pretrend/pipeline/strategy_engine/{allocation, policy_selector, sell_advisor, universe}`
- `src/pretrend/backtest/`
- `src/pretrend/paper/`
- `src/pretrend/broker/`
- `dags/strategy_engine_dag.py`
- `dags/paper_trading_dag.py`
- `dags/broker_mock_trading_dag.py`
- Telegram bot orchestration scripts.

Rules:

- No new Personal Track feature work.
- Preserve archived personal tests.
- Fix only unavoidable compatibility or safety issues.
- Operational state should match `track_separation.md`: frozen and service-stopped.

Known P29 audit note:

- P29-2 found Personal DAGs registered as `is_paused=False`; paper and broker DAGs also resolve to the same `09:40` weekday slot when `.env.airflow` is sourced. This is an operational hotfix candidate.

## 11. Extension Rules

| New work | Location |
| --- | --- |
| New market state observation | `src/pretrend/observability/regime/` |
| New similarity view or similarity operation | `src/pretrend/observability/similarity/` plus explicit contract update |
| New explanation prompt/use case | `src/pretrend/observability/explainability/` plus prompt version policy |
| New read-only API route | `src/pretrend/api/routers/` plus API contract update |
| New dashboard page | `apps/web/` after Phase 3 starts |
| New Postgres serving table | `src/pretrend/models/` and `migrations/versions/` only after contract and migration plan |
| New operational DAG | `dags/`, with track ownership and recovery notes |
| New investing decision logic | Not allowed in Observability; Personal Track is frozen |

If a change touches grain, key, invariant, schema, or public API, stop and update the contract first.

## 12. Current Phase Status

| Area | Status |
| --- | --- |
| Phase 0 foundation | Done |
| Phase 1 Observability extraction | Done with compatibility shims |
| Phase 2 code/data layer | Done |
| P29 Stage Gate | In progress |
| Phase 3 dashboard | Pending P29 completion |
| Cloudflare Tunnel | Deferred until local dashboard E2E is verified |

P24-P28 SOT index:

| Workstream | SOT |
| --- | --- |
| P24 Gold Postgres schema | [gold_postgres_schema.md](./gold_postgres_schema.md) |
| P25 Gold Postgres sync | [gold_postgres_sync.md](./gold_postgres_sync.md) |
| P26 Historical similarity | [similarity_design.md](./similarity_design.md) |
| P27 Explainability layer | [explainability_design.md](./explainability_design.md) |
| P28 Observability API | [api_design.md](./api_design.md) |

P29 audit outputs that should influence Phase 3:

- Broader Observability to Personal/legacy pipeline boundary cleanup is still needed.
- Strategy Engine compatibility shim exports need clarification.
- Personal Track Airflow operational state needs repair.
- Airflow audit commands must use the project `AIRFLOW_HOME`, project `PYTHONPATH`, and project `DAGS_FOLDER`.

## 13. Change History

- 2026-05-15: Initial draft. P29-3.
