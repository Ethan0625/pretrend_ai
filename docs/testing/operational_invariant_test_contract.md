# Operational Invariant Test Contract

Markers: testing, contract
Status: active

## 1. Testing Philosophy

Tests in the Observability Track are not only feature checks. They are operational invariant monitors for the local runtime.

They should answer:

- Did a contract change break the public API?
- Did a migration drift from SQLAlchemy models or source schema?
- Did a DAG stop importing or scheduling correctly?
- Did a serving table violate grain/key or PIT rules?
- Did a boundary import reintroduce Personal Track coupling?
- Did explanation or API text cross into prediction or recommendation semantics?

P29 separates verification into code audit, operations audit, documentation contracts, and final stage-gate reporting. This document defines how future pytest markers and command sets should encode those checks.

## 2. Test Group Inventory

| Test Group | Invariant | Failure Means | Run Timing | Marker |
| --- | --- | --- | --- | --- |
| `gold_sync` | Postgres mirror matches Gold Parquet contract and preserves UPSERT idempotency | API/similarity may read stale or malformed Gold data | Before dashboard work and after sync changes | `db`, `invariant` |
| `api_contract` | 11 logical endpoints preserve auth, response schema, error behavior | Dashboard client contract is unsafe | Every API change and pre-dashboard check | `contract` |
| `similarity` | Multi-view similarity remains historical comparison with min-gap, score, rank, and PK invariants | Similarity can become misleading or invalid | Similarity changes and stage gates | `invariant`, `db` where Postgres is used |
| `explainability` | Cached reports remain evidence-bound and prediction-free | LLM output can leak recommendation semantics or cause cost drift | Prompt/provider/cache changes and stage gates | `invariant`, `slow` where real provider is used |
| `boundary` | Observability and Personal Track dependency boundaries hold | Frozen Personal code becomes coupled to main runtime or vice versa | Every refactor and stage gate | `contract` |
| `migration` | Alembic chain, SQLAlchemy models, and physical DB schema stay aligned | Serving DB cannot be rebuilt safely | Schema/model/migration changes and stage gates | `db`, `invariant` |
| `dag` | DAGs import, schedule, and task graph shape remain valid | Scheduler runtime can silently break | DAG changes and operations audit | `dag`, `contract` |
| `personal_archive` | Frozen Personal regression assets remain runnable on demand | Archived assets were accidentally broken or deleted | Manual regression only | `personal`, `slow` as needed |
| `runtime_reproducibility` | Docker runtime, restore procedure, volume mounts, and sensitive-file excludes stay reproducible | New clone / OS migration / power-loss recovery procedures can drift silently | P30 and every runtime/Docker/docs change | `contract` |

## 3. Required Pytest Markers

The following markers should be added in P29-4.

| Marker | Meaning |
| --- | --- |
| `contract` | Public contract or boundary behavior. Breakage means a documented interface changed. |
| `invariant` | Operational invariant such as PIT, idempotency, no forbidden terms, no duplicate keys, or score range. |
| `db` | Requires a real or provisioned database connection. |
| `dag` | Validates Airflow DAG import, metadata, schedule, or task graph. |
| `slow` | Too slow for quick local loops or depends on larger data fixtures. |
| `personal` | Frozen Personal Track regression tests, normally excluded from active default runs. |

Marker rules:

- A test can have multiple markers.
- `personal` tests must remain available but should not be part of the active default runtime check unless explicitly requested.
- `db` tests must document required env vars or fixtures.
- Real LLM provider checks must be `slow` and must not run by default.

## 4. Required Command Sets

These command sets are target contracts for P29-4 marker work. Until markers are applied, use the existing explicit pytest paths from task docs.

Fast local check:

```bash
conda run -n pytest-pretrend pytest -m "not slow and not db and not personal" -q --tb=short
```

Contract and invariant check:

```bash
conda run -n pytest-pretrend pytest -m "contract or invariant" -q --tb=short
```

Phase 2 backend/runtime check:

```bash
conda run -n pytest-pretrend pytest -m "db or contract or invariant" -q --tb=short
```

DAG check:

```bash
conda run -n pytest-pretrend pytest -m "dag" -q --tb=short
```

Pre-dashboard check:

```bash
conda run -n pytest-pretrend pytest -m "not personal" -q --tb=short
```

P30 reproducible runtime gate:

```bash
docker compose config --quiet
docker compose build
docker compose up -d postgres api
docker compose ps
docker build -t pretrend-dev -f Dockerfile.dev .
docker run --rm pretrend-dev pytest -q --tb=short
docker run --rm pretrend-dev pytest tests/ops/ -q --tb=short
```

P30 volume and sensitive-file gate:

```bash
docker compose exec -T postgres sh -c 'test -d /var/lib/postgresql/data'
docker compose exec -T postgres sh -c 'test -d /backups'
git status --ignored --short .env .env.airflow .local data logs result .agent
docker run --rm --entrypoint sh pretrend-api-test -c 'test ! -e /app/.env && test ! -d /app/data && test ! -d /app/logs && test ! -d /app/result && test ! -d /app/tests && test ! -d /app/docs'
docker run --rm --entrypoint sh pretrend-dev -c 'test ! -e /app/.env && test ! -d /app/data && test ! -d /app/logs && test ! -d /app/result && test -d /app/tests && test -d /app/docs'
```

P30 restore gate:

```bash
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /backups/pretrend_test.dump'
docker compose exec -T postgres sh -c 'test -s /backups/pretrend_test.dump'
docker compose exec -T postgres sh -c 'createdb -U "$POSTGRES_USER" pretrend_restore_check'
docker compose exec -T postgres sh -c 'pg_restore --exit-on-error -U "$POSTGRES_USER" -d pretrend_restore_check --no-owner --no-privileges /backups/pretrend_test.dump'
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d pretrend_restore_check -Atc "SELECT COUNT(*) FROM alembic_version;"'
docker compose exec -T postgres sh -c 'dropdb -U "$POSTGRES_USER" pretrend_restore_check'
```

Pre-Cloudflare check:

```bash
conda run -n pytest-pretrend pytest -m "not personal" -q --tb=short
```

Manual Personal regression:

```bash
conda run -n pytest-pretrend pytest tests/archive/personal/ -q --tb=short
```

Operational SQL checks remain outside pytest until explicit DB fixtures are added:

```sql
SELECT COUNT(*), MAX(trade_date) FROM gold_macro_features;
SELECT COUNT(*), MAX(trade_date) FROM gold_eod_features;
SELECT COUNT(*), MAX(trade_date) FROM gold_market_state_similarity_feature;
SELECT COUNT(*), MAX(query_date) FROM similarity_regime;
SELECT COUNT(*), MAX(query_date) FROM similarity_gold;
SELECT use_case, COUNT(*), MAX(query_date) FROM explainability_cache GROUP BY 1;
```

Airflow CLI checks require the project environment:

```bash
env \
  AIRFLOW_HOME=/home/redtable/Desktop/ethan/pretrend/pretrend_ai/airflow_pretrend \
  PYTHONPATH=/home/redtable/Desktop/ethan/pretrend/pretrend_ai/src \
  AIRFLOW__CORE__DAGS_FOLDER=/home/redtable/Desktop/ethan/pretrend/pretrend_ai/dags \
  AIRFLOW__CORE__LOAD_EXAMPLES=False \
  AIRFLOW__CORE__DEFAULT_TIMEZONE=Asia/Seoul \
  conda run -n airflow-pretrend airflow dags list-import-errors
```

Forbidden prediction/recommendation checks are allowlist-aware. Raw recursive grep is not expected to return zero because it will match invariant definitions, negative tests, archived Personal assets, and docs that describe forbidden terms. Use these checks instead:

```bash
conda run -n pytest-pretrend pytest tests/observability/explainability/test_invariant_filter.py -q
conda run -n pytest-pretrend pytest tests/observability/test_boundary_imports.py tests/observability/regime/test_strategy_shim_exports.py -q
```

Operational API/cache forbidden-term checks should inspect live response bodies and `explainability_cache.report_json`, not documentation text or negative fixtures.

## 5. Missing Test TODO

The following gaps were identified during P29 and should become explicit tests or documented operational checks.

| Gap | Why it matters | Candidate marker |
| --- | --- | --- |
| Boundary import grep test | Added in P29 hotfix: `tests/observability/test_boundary_imports.py` protects Observability from frozen Personal imports | `contract` |
| Shim export compatibility test | Added in P29 hotfix: `tests/observability/regime/test_strategy_shim_exports.py` protects package-level shim exports | `contract` |
| Model-migration-feature schema alignment test | P29-1 had to verify six serving tables manually | `db`, `invariant` |
| Alembic shadow upgrade/downgrade test | Rebuildability should be protected outside manual stage gates | `db`, `invariant`, `slow` |
| API forbidden term live-response test | API and explanations must remain observation-only | `invariant` |
| End-to-end DAG chain smoke | P29-2 verified manual reruns, but no single automated test covers sync -> similarity -> explainability | `dag`, `db`, `slow` |
| Airflow project-env guard | Documented in `docs/operation_guide.md`; future automation can wrap the project env command | `dag`, `contract` |
| Personal DAG paused-state check | P29 hotfix paused the three Personal DAGs; future automation can assert paused state from project metadata | `contract`, `dag` |
| Explainability scope/window contract test | Historical LLM backfill should not pollute cache before scope/window is explicit | `contract`, `invariant` |

## 6. Change History

- 2026-05-15: Initial draft. P29-3.
- 2026-05-15: Added allowlist-aware forbidden-term guidance, boundary import test reference, shim export test reference, and Airflow project-env guard follow-up notes.
- 2026-05-15: Added P30 reproducible runtime, volume/sensitive-file, and separate-DB restore gates.
