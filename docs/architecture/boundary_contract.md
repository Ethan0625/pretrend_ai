# Boundary Contract

## 1. Track Classification

This document is the dependency boundary contract for the 2026Q2 two-track architecture.

### Shared Infrastructure

Shared Infrastructure may be read by both Observability and frozen Personal assets.

| Path | Responsibility |
| --- | --- |
| `src/pretrend/pipeline/ingest/` | Bronze source ingestion |
| `src/pretrend/pipeline/features/` | Silver/Gold feature builders |
| `src/pretrend/pipeline/calendar/` | Release calendar and PIT evidence |
| `src/pretrend/pipeline/config/` | Shared universe/config definitions where explicitly documented |
| `data/bronze/`, `data/silver/`, `data/gold/` | Parquet data layers |
| `dags/eod_pipeline_dag.py` | Shared EOD data DAG |
| `dags/macro_pipeline_dag.py` | Shared macro data DAG |

### Observability Track

Observability owns market structure observation, historical comparison, explanation, serving DB schema, API, and dashboard surfaces.

| Path | Responsibility |
| --- | --- |
| `src/pretrend/observability/regime/` | Regime observation modules |
| `src/pretrend/observability/similarity/` | Historical similarity builders and inputs |
| `src/pretrend/observability/explainability/` | Evidence-bound report generation and cache |
| `src/pretrend/api/` | Read-only FastAPI runtime |
| `src/pretrend/models/` | Postgres SQLAlchemy/Pydantic models |
| `src/pretrend/config.py` | Observability runtime settings |
| `src/pretrend/pipeline/sync/` | Gold Parquet to Postgres sync |
| `migrations/` | Postgres/TimescaleDB schema revisions |
| `dags/gold_postgres_sync_dag.py` | Gold mirror sync |
| `dags/similarity_build_dag.py` | Similarity build |
| `dags/explainability_build_dag.py` | Explainability cache build |
| `Dockerfile.api`, `requirements_api.txt`, `docker-compose.yml` `api` service | API runtime integration |
| `apps/web/` | Phase 3 dashboard |

### Personal Track Frozen

Personal Track preserves prior investing experiment assets. It is frozen and should not operate services by default.

| Path | Responsibility |
| --- | --- |
| `src/pretrend/pipeline/strategy_engine/{allocation, policy_selector, sell_advisor, universe}` | Investing decision logic |
| `src/pretrend/backtest/` | Backtest and walk-forward assets |
| `src/pretrend/paper/` | Paper trading |
| `src/pretrend/broker/` | Broker mock/live adapters |
| `dags/strategy_engine_dag.py` | Strategy snapshot DAG |
| `dags/paper_trading_dag.py` | Paper trading DAG |
| `dags/broker_mock_trading_dag.py` | Broker mock DAG |
| `tests/archive/personal/` | Archived Personal regression tests |
| `scripts/telegram_*` | Telegram orchestration assets |

Compatibility shims under `src/pretrend/pipeline/strategy_engine/*` that re-export moved Observability modules are temporary compatibility assets. They must not be treated as new Personal feature ownership.

## 2. Allowed Dependencies

Allowed dependency direction:

```text
Observability Track -> Shared Infrastructure
Personal Track Frozen -> Shared Infrastructure
```

Allowed examples:

- API routers import `pretrend.models` and Observability query helpers.
- Similarity builders read Postgres mirror data and shared Gold feature definitions.
- Gold Postgres sync reads Gold Parquet feature contracts.
- Legacy Personal tests may import archived Personal modules for regression only.

Observability may read:

- `pretrend.pipeline.features.*`
- `pretrend.pipeline.calendar.*`
- `pretrend.pipeline.config.*` only when the config is explicitly shared.
- `pretrend.models.*`
- `pretrend.config`

Personal may continue reading:

- Shared Gold Parquet features.
- Existing Personal snapshots and ledgers.
- Archived Personal test fixtures.

## 3. Forbidden Dependencies

Forbidden code dependencies:

- `src/pretrend/observability/` must not import `pretrend.backtest`, `pretrend.paper`, or `pretrend.broker`.
- `src/pretrend/observability/` must not import Personal decision modules from `pretrend.pipeline.strategy_engine.*`.
- `src/pretrend/api/` must not import allocation, paper, broker, backtest, or Personal strategy modules.
- Personal Track modules must not import `pretrend.observability`, `pretrend.models`, or API runtime modules.
- Dashboard code must not call Personal Track endpoints or read Personal snapshots.

Forbidden product semantics:

- FastAPI must not return allocation, order, buy, sell, hold, target price, or target return guidance.
- Similarity must not claim future prediction.
- Explainability must not generate investment decision text.
- Dashboard must not display historical similarity as a future outcome.
- LLM output must remain observer-only and must not become strategy input.

Forbidden schema drift:

- Postgres mirror tables must not change grain/key without a contract and migration task.
- `explainability_cache` must not receive historical full LLM backfill under a cache key that cannot distinguish explanation scope/window.

P29 hotfix resolution:

- Shared snapshot load/write helpers live in `src/pretrend/pipeline/utils/snapshot.py`.
- Runtime Observability modules import shared snapshot IO instead of `pretrend.pipeline.backtest._utils`.
- The one-off historical `what_to_hold` backfill helper was moved out of runtime Observability to `src/pretrend/pipeline/research/similarity_what_to_hold_backfill.py`.
- `tests/observability/test_boundary_imports.py` protects this boundary with an AST import check.

## 4. Frozen Boundary Rules

Personal Track rules:

- No new features.
- No service enablement by default.
- No new dashboard surface.
- No new API dependency.
- No deletion of archived Personal regression tests.
- Compatibility fixes are allowed only when needed for active Observability or CI safety.

Operational rules:

- `strategy_engine_dag`, `paper_trading_dag`, and `broker_mock_trading_dag` should be paused or disabled according to `track_separation.md`.
- If an operational audit finds Personal DAGs unpaused, record it as drift and fix in a separate operational hotfix.
- Existing Personal data under `state/`, `data/strategy/`, `data/paper/`, and `data/broker/` should be preserved.

Review checklist:

- Did the change add an Observability import of Personal code?
- Did the change add a Personal import of Observability code?
- Did the API expose decision fields?
- Did an LLM output become strategy input?
- Did a Postgres table key/grain change without a contract?
- Did a Personal DAG become scheduled or unpaused?

## 5. Change History

- 2026-05-15: Initial draft. P29-3.
- 2026-05-15: P29 hotfix resolved known runtime Observability boundary exceptions by extracting shared snapshot IO and moving historical backfill helper out of `src/pretrend/observability/`.
