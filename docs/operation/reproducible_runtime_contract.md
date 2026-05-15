# Reproducible Runtime Contract

Markers: contract, operation, security, testing
Status: active
Last Updated: 2026-05-15

## 1. Purpose

Pretrend must be runnable from a fresh clone without depending on one Linux desktop.

This contract defines the minimum runtime, data, backup, and verification rules required before Phase 3 dashboard work continues. The target is not cloud deployment. The target is a reproducible local development and verification runtime across Linux, Windows PowerShell, and Windows with WSL2.

## 2. Non-Goals

This contract does not introduce:

- Cloud deployment.
- Full Airflow Docker operations.
- MinIO/S3.
- LLM server Dockerization.
- Broker/live trading operations.
- Production scheduling.
- Git-tracked data lake files.

## 3. Runtime Roles

| Runtime | Role | Notes |
| --- | --- | --- |
| `postgres` | TimescaleDB serving DB | Stores Postgres mirror/cache tables for API, similarity, and explainability. |
| `api` | Read-only FastAPI service | Serves Observability API from Postgres. |
| `dev/test` | Reproducible validation image | Runs pytest, smoke checks, repository audits, and README validation. |
| `ops/worker` | Future operational helper | May run dump/restore/bootstrap commands without changing API image scope. |

Existing production-facing API runtime and dev/test runtime must stay separate:

- `Dockerfile.api`: API service runtime.
- `Dockerfile.dev`: pytest, smoke run, repository audit, and reproducibility verification runtime.

## 4. Environment Variables

Host path variables:

```text
PRETREND_POSTGRES_DATA_DIR=./.local/postgres-data
PRETREND_BACKUP_DIR=./.local/backups
PRETREND_HOST_DATA_DIR=./data
PRETREND_HOST_LOG_DIR=./logs
```

Container path variables:

```text
PRETREND_DATA_DIR=/app/data
PRETREND_LOG_DIR=/app/logs
PRETREND_ENV=local|test|sample|backfill
```

Current pipeline data readers still use `PRETREND_DATA_ROOT` for the file data lake. In Docker runtime docs, `PRETREND_DATA_DIR=/app/data` is the container mount target and `PRETREND_DATA_ROOT=/app/data` is the compatibility value used by existing Bronze/Silver/Gold jobs.

Secret variables must be defined only in `.env` and must not be committed or copied into Docker images:

```text
PRETREND_API_KEY=
FRED_API_KEY=
OPENAI_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
KIS_APP_KEY=
KIS_APP_SECRET=
```

`.env.example` may contain variable names and placeholder descriptions only.

## 5. Volume Contract

The active Postgres volume is controlled by `PRETREND_POSTGRES_DATA_DIR`.

```yaml
services:
  postgres:
    volumes:
      - ${PRETREND_POSTGRES_DATA_DIR:-./.local/postgres-data}:/var/lib/postgresql/data
      - ${PRETREND_BACKUP_DIR:-./.local/backups}:/backups

  api:
    volumes:
      - ${PRETREND_HOST_DATA_DIR:-./data}:/app/data
      - ${PRETREND_HOST_LOG_DIR:-./logs}:/app/logs
```

Rules:

- `./.local/postgres-data` is the default, not a fixed official path.
- External drive, local disk, and WSL2 mount paths use the same compose contract.
- `docker compose down -v` remains forbidden for operational data.
- If an external drive is used as the active DB volume, disconnecting it while Docker is running can corrupt the DB.
- Restore verification must use a separate test DB or volume, never overwrite the active DB.

## 6. OS Examples

Linux or macOS:

```bash
PRETREND_POSTGRES_DATA_DIR=/mnt/pretrend/postgres-data docker compose up -d postgres api
```

Windows PowerShell:

```powershell
$env:PRETREND_POSTGRES_DATA_DIR="E:\pretrend\postgres-data"
docker compose up -d postgres api
```

Windows with WSL2:

```bash
PRETREND_POSTGRES_DATA_DIR=/mnt/e/pretrend/postgres-data docker compose up -d postgres api
```

README procedures must include OS-specific `docker compose` commands. Makefile targets may exist as convenience helpers, but the Makefile must not be the only documented execution path.

## 7. Docker Build Context

Docker images must never include:

- `.env`
- `.env.airflow`
- API keys, tokens, or passwords
- `.local/`
- `data/`
- `logs/`
- `result/`
- Airflow runtime logs
- local caches and virtual environments
- large parquet/csv/db outputs

The dev/test image must include the files required to run tests and verify documentation contracts. Therefore `tests/` and required `docs/` content must be available to the dev/test image.

Preferred structure:

```text
Dockerfile.api
Dockerfile.api.dockerignore
Dockerfile.dev
Dockerfile.dev.dockerignore
```

Image roles:

- API builds use `Dockerfile.api` and `requirements_api.txt`.
- Dev/test builds use `Dockerfile.dev` and `requirements_ci.txt`.
- Dev/test builds include `dags/`, `tests/`, and required `docs/`.
- Both image contexts exclude `.env`, `.env.airflow`, `.local`, `data`, `logs`, and `result`.

If Dockerfile-specific ignore files are not reliable in the local Docker environment, keep root `.dockerignore` as a common safe exclude list and defer API image slimming to a follow-up optimization.

## 8. Data Bootstrap Contract

Pretrend has two data layers with different recovery rules:

| Layer | Role | Recovery Priority |
| --- | --- | --- |
| Postgres serving DB | API/similarity/explainability serving state | Restore from `pg_dump -Fc` first. |
| File data lake | Bronze/Silver/Gold/source data | Rebuild via bootstrap/backfill commands when needed. |

Backfill is a reconstruction path, not the first operational recovery path. For power-loss or machine migration recovery, use DB dump restore first when a current dump exists.

Recovery decision order:

1. If a current dump exists, restore the Postgres serving DB into a separate validation DB/volume first. Active recovery is an operator action after that validation evidence exists.
2. If the dump is missing or stale, rebuild the file data lake into the mounted data directory, then sync Gold Parquet into Postgres, then rebuild derived similarity/explainability serving tables where applicable.
3. Do not run historical explainability LLM backfill until the Phase 3 dashboard scope/window/cache key contract is finalized.

Sample mode:

- Uses repository fixtures or synthetic data only.
- Must not call external APIs.
- Must not be used to populate persistent serving DB state.

Backfill mode:

- A real volume must be mounted for `PRETREND_DATA_DIR` and existing `PRETREND_DATA_ROOT` consumers must resolve to the same path.
- `.env` must be present when external APIs are used.
- External API usage must be explicit.
- Test/sample mode must not call external APIs.

Existing bootstrap entrypoints:

| Step | Existing entrypoint | Notes |
| --- | --- | --- |
| Macro Bronze/Silver/Gold rebuild | `python -m pretrend.pipeline.macro_job --start YYYY-MM-DD --end YYYY-MM-DD` or `macro_pipeline_dag` | Uses `PRETREND_DATA_ROOT`; may call external data sources. |
| EOD Bronze/Silver/Gold rebuild | `python -m pretrend.pipeline.eod_job --start YYYY-MM-DD --end YYYY-MM-DD` or `eod_pipeline_dag` | Uses `PRETREND_DATA_ROOT`; may call external data sources. |
| Gold Parquet to Postgres sync | `gold_postgres_sync_dag` / `pretrend.pipeline.sync.gold_postgres.sync_gold_macro` and `sync_gold_eod` | Incremental UPSERT from Gold Parquet into serving DB. |
| Similarity derived table rebuild | `similarity_build_dag` with `query_start` / `query_end` conf | Rebuild by explicit query window. |
| Explainability cache build | `explainability_build_dag` latest/on-demand conf only | Default provider is mock. No full historical LLM backfill before Phase 3 contract. |
| Text data backfill | `python -m pretrend.pipeline.text.backfill ...` | Text observability path, not the primary serving DB recovery path. |

No new bootstrap runner is required for P30-3. The current contract is a documented operator sequence that composes existing DAGs/functions. A future `ops/worker` runner may wrap this sequence after P30-4 verifies the end-to-end reproducibility path.

## 9. DB Backup And Restore

Backup command:

```bash
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /backups/pretrend_obs_YYYYMMDD.dump'
```

Dump validation:

```bash
docker compose exec -T postgres sh -c 'test -s /backups/pretrend_obs_YYYYMMDD.dump'
docker compose exec -T postgres sh -c 'pg_restore -l /backups/pretrend_obs_YYYYMMDD.dump' >/tmp/pretrend_obs_YYYYMMDD.list
```

The catalog file must contain the expected schema objects before any restore is considered. At minimum, check migration metadata and serving tables:

```bash
grep -E 'TABLE DATA public (alembic_version|gold_macro_features|gold_eod_features|similarity_regime|similarity_gold|gold_market_state_similarity_feature|explainability_cache)' /tmp/pretrend_obs_YYYYMMDD.list
```

Restore validation must be done against a separate DB or separate volume. The active `pretrend_obs` DB must not be overwritten during verification.

Separate DB validation shape:

```bash
docker compose exec -T postgres sh -c 'createdb -U "$POSTGRES_USER" pretrend_restore_check'
docker compose exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d pretrend_restore_check --no-owner --no-privileges /backups/pretrend_obs_YYYYMMDD.dump'
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d pretrend_restore_check -Atc "SELECT COUNT(*) FROM alembic_version;"'
docker compose exec -T postgres sh -c 'dropdb -U "$POSTGRES_USER" pretrend_restore_check'
```

Separate volume validation shape:

```bash
PRETREND_POSTGRES_DATA_DIR=./.local/postgres-restore-check \
PRETREND_BACKUP_DIR=./.local/backups \
docker compose -p pretrend-restore-check up -d postgres
docker compose -p pretrend-restore-check exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges /backups/pretrend_obs_YYYYMMDD.dump'
docker compose -p pretrend-restore-check exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT COUNT(*) FROM alembic_version;"'
```

After restore validation, stop the check project without deleting operational volumes:

```bash
docker compose -p pretrend-restore-check stop postgres
```

Do not run `docker compose down -v` against the normal project or against any project name whose volume contains operational data.

## 10. Reproducibility Verification

P30 is not complete until a fresh clone can verify:

- Docker build for API runtime.
- Docker build for dev/test runtime.
- Docker pytest or agreed smoke test.
- `docker compose config --quiet`.
- Postgres volume mount path.
- Backup directory mount path.
- API health check.
- DB dump catalog check.
- Restore procedure in a separate DB/volume.
- Sensitive files excluded from Git/build context/image.
- README commands executable on Linux/WSL2 and Windows PowerShell.

Standard verification command set:

```bash
docker compose config --quiet
docker compose build
docker compose up -d postgres api
docker compose ps
docker build -t pretrend-dev -f Dockerfile.dev .
docker run --rm pretrend-dev pytest -q --tb=short
docker run --rm pretrend-dev pytest tests/ops/ -q --tb=short
```

Sensitive-file image checks:

```bash
docker run --rm --entrypoint sh pretrend-api-test -c 'test ! -e /app/.env && test ! -d /app/data && test ! -d /app/logs && test ! -d /app/result && test ! -d /app/tests && test ! -d /app/docs'
docker run --rm --entrypoint sh pretrend-dev -c 'test ! -e /app/.env && test ! -d /app/data && test ! -d /app/logs && test ! -d /app/result && test -d /app/tests && test -d /app/docs'
```

## 11. Docs And Agent Publication

`.agent`, `CLAUDE.md`, and `AGENTS.md` publication must use a whitelist. Do not unignore `.agent` wholesale.

Public whitelist:

```text
AGENTS.md
CLAUDE.md
.agent/README.md
.agent/STABLE_CONTEXT.md
.agent/INVARIANTS.md
.agent/WORKFLOW.md
.agent/CHANGE_GATES.md
.agent/TASK_QUEUE.md
.agent/TASK_TEMPLATE.md
.agent/PARENTS_TASK_TEMPLATE.md
.agent/task/P30_parent_reproducible_runtime.md
.agent/task/P30-0_formalize_runtime_contract.md
.agent/task/P30-1_runtime_volume_contract.md
.agent/task/P30-2_docker_build_test_runtime.md
.agent/task/P30-3_data_bootstrap_db_restore_contract.md
.agent/task/P30-4_reproducibility_verification.md
.agent/task/P30-5_agent_docs_publication_safety.md
.agent/task/P30-6_docs_marker_classification.md
```

Default excluded candidates:

- `.agent/settings.local.json`
- `.agent/RUN_LOG.md`
- `.agent/task/archive/`
- large archives
- local-path-heavy session notes
- files containing actual secret values

Docs should be classified with markers so publication and onboarding can be checked mechanically. Marker vocabulary is defined in `docs/README.md`.

Docs markers:

```text
contract
operation
testing
architecture
roadmap
agent
legacy
security
```

## 12. Change History

- 2026-05-15: Initial draft from P30 planning.
- 2026-05-15: P30-1 aligned compose runtime volume variables and OS-specific examples.
- 2026-05-15: P30-2 added separate API/dev-test Docker build roles and per-Dockerfile ignore files.
- 2026-05-15: P30-3 fixed restore-first/backfill-fallback data bootstrap contract and restore validation shape.
- 2026-05-15: P30-4 added standard reproducibility verification and sensitive-file image checks.
- 2026-05-15: P30-5/P30-6 fixed agent publication whitelist and docs marker classification.
