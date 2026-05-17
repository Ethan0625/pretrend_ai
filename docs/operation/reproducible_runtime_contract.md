# 재현 가능한 런타임 계약

Markers: contract, operation, security, testing
Status: active
Last Updated: 2026-05-17

## 1. 목적

Pretrend는 특정 Linux desktop에 묶이지 않고, 신규 clone에서도 실행·검증·복구 가능해야 한다.

이 문서는 Phase 3 dashboard 작업을 계속하기 전에 필요한 최소 runtime, data, backup, verification rule을 고정한다. 목표는 cloud deployment가 아니라 Linux, Windows PowerShell, Windows + WSL2에서 재현 가능한 로컬 개발·검증 runtime을 만드는 것이다.

## 2. 명시적 제외 범위

이 계약은 다음을 도입하지 않는다.

- Cloud deployment.
- Celery, Redis, Kubernetes, HA scheduling 같은 production Airflow 운영.
- MinIO/S3.
- LLM server Docker화.
- Broker/live trading 운영.
- Production scheduling.
- Git-tracked data lake file.

## 3. Runtime 역할

| Runtime | 역할 | 비고 |
| --- | --- | --- |
| `postgres` | TimescaleDB serving DB | API, similarity, explainability가 조회하는 Postgres mirror/cache table 저장. |
| `postgres-test` | 격리 pytest DB | 운영 DB와 분리된 TimescaleDB. migration/schema/synthetic row smoke 전용. |
| `api` | Read-only FastAPI service | Postgres 기반 Observability API 제공. |
| `dev/test` | 재현 가능한 검증 image | pytest, smoke check, repository audit, README 검증 실행. |
| `test-runner` | 격리 DB smoke runner | compose `test` profile service. test DB에 Alembic migration을 적용한 뒤 synthetic row DB smoke를 실행. |
| `worker` | 수동 backfill / ops helper | `docker/Dockerfile.dev` 기반 compose `ops` profile service. API image scope를 키우지 않고 data/log mount를 공유. |
| `backfill-once` | 1회성 file data lake bootstrap | compose `bootstrap` profile service. Macro/EOD Bronze/Silver/Gold를 1회 실행하고 Gold Parquet을 Postgres로 sync한 뒤 marker 기록. |
| `airflow-*` | 로컬 DAG scheduler runtime | Airflow 2 webserver, scheduler, metadata initialization용 compose `airflow` profile service. |

API runtime과 dev/test runtime은 분리한다.

- `docker/Dockerfile.api`: API service runtime.
- `docker/Dockerfile.dev`: pytest, smoke run, repository audit, reproducibility verification runtime.
- `docker/Dockerfile.airflow`: Airflow 2 scheduler/webserver image. DAG runtime dependency와 Pretrend source를 포함한다.

## 4. 환경 변수

Host path 변수:

```text
PRETREND_POSTGRES_DATA_DIR=./.local/postgres-data
PRETREND_BACKUP_DIR=./.local/backups
PRETREND_HOST_DATA_DIR=./data
PRETREND_HOST_LOG_DIR=./logs
PRETREND_HOST_DAGS_DIR=./dags
PRETREND_HOST_SRC_DIR=./src
PRETREND_STATE_DIR=./state
PRETREND_CODEX_BIN_DIR=./codex-bin
PRETREND_CODEX_HOME_DIR=./codex-home
PRETREND_AIRFLOW_HOME_DIR=./airflow_pretrend
PRETREND_AIRFLOW_LOG_DIR=./airflow_pretrend/logs
```

격리 pytest DB 변수:

```text
PRETREND_TEST_POSTGRES_USER=pretrend_test
PRETREND_TEST_POSTGRES_PASSWORD=CHANGE_ME
PRETREND_TEST_POSTGRES_DB=pretrend_test
PRETREND_TEST_POSTGRES_PORT=15432
PRETREND_TEST_POSTGRES_DATA_DIR=./.local/postgres-test-data
PRETREND_TEST_DATABASE_URL=postgresql+psycopg2://pretrend_test:CHANGE_ME@localhost:15432/pretrend_test
```

DB synthetic row 테스트는 `PRETREND_TEST_DATABASE_URL`이 가리키는 DB에서만 실행한다. DB 이름은 반드시 `pretrend_test*`여야 하며, 운영 DB 이름을 넣으면 테스트가 실패한다.

Bootstrap backfill 변수:

```text
PRETREND_BACKFILL_ON_START=1
PRETREND_BACKFILL_START_DATE=2003-01-01
PRETREND_BACKFILL_END_DATE=
PRETREND_BACKFILL_FORCE=0
PRETREND_BACKFILL_RUN_MACRO=1
PRETREND_BACKFILL_RUN_EOD=1
PRETREND_BACKFILL_SYNC_POSTGRES=1
PRETREND_BACKFILL_SYMBOLS=
PRETREND_BACKFILL_MARKER_PATH=/app/data/meta/bootstrap_backfill_once.json
PRETREND_GOLD_SYNC_FULL=0
PRETREND_GOLD_SYNC_START_DATE=
```

Container path 변수:

```text
PRETREND_DATA_DIR=/app/data
PRETREND_LOG_DIR=/app/logs
PRETREND_ENV=local|test|sample|backfill
```

기존 Bronze/Silver/Gold job은 file data lake 경로로 `PRETREND_DATA_ROOT`를 읽는다. Docker runtime에서는 `PRETREND_DATA_DIR=/app/data`가 mount target이고, 호환성을 위해 `PRETREND_DATA_ROOT=/app/data`도 같은 값을 사용한다.

Secret 변수는 `.env`에만 정의하고 commit하거나 Docker image에 복사하지 않는다.

```text
PRETREND_API_KEY=
FRED_API_KEY=
OPENAI_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
KIS_APP_KEY=
KIS_APP_SECRET=
```

`.env.example`은 변수명과 placeholder만 포함할 수 있다.

Airflow profile 변수:

```text
AIRFLOW_ADMIN_USER=
AIRFLOW_ADMIN_PASSWORD=
AIRFLOW_ADMIN_EMAIL=admin@example.local
```

`airflow-init`을 실행하기 전에 실제 Airflow admin user/password를 `.env`에 채워야 한다.

Strategy report analyzer 변수:

```text
PRETREND_REPORT_API_URL=http://api:8000/api/v1/report/strategy/analyze
# Docker Airflow에서 host-local FastAPI를 호출하는 mode:
# PRETREND_REPORT_API_URL=http://host.docker.internal:8100/api/v1/report/strategy/analyze
PRETREND_STATE_DB=/app/state/orchestrator.db
PRETREND_CODEX_BIN=
REPORT_ANALYZER_ENABLED=1
REPORT_ANALYZER_TIMEOUT=180
REPORT_LLM_PROVIDER=gemini
REPORT_LLM_MODEL=gemini-2.5-flash
REPORT_LLM_BASE_URL=
REPORT_LLM_TIMEOUT=
REPORT_LLM_FALLBACK_ENABLED=1
REPORT_LLM_RETRY=3
```

`PRETREND_CODEX_BIN`은 선택값이다. 비어 있으면 analyzer가 OS별 후보를 찾는다. Docker mode에서는 `PRETREND_CODEX_BIN_DIR`가 FastAPI container의 `/opt/pretrend/codex-bin`에 read-only mount되므로 Linux `codex` executable을 포함해야 한다. `PRETREND_CODEX_HOME_DIR`는 `/root/.codex`에 mount되어 Codex auth/session state를 재사용한다. 신뢰할 수 있는 로컬 머신에서만 host `.codex` directory를 가리킨다.

## 5. Volume 계약

Active Postgres volume은 `PRETREND_POSTGRES_DATA_DIR`가 제어한다.

```yaml
services:
  postgres:
    volumes:
      - ${PRETREND_POSTGRES_DATA_DIR:-./.local/postgres-data}:/var/lib/postgresql/data
      - ${PRETREND_BACKUP_DIR:-./.local/backups}:/backups

  postgres-test:
    volumes:
      - ${PRETREND_TEST_POSTGRES_DATA_DIR:-./.local/postgres-test-data}:/var/lib/postgresql/data

  api:
    volumes:
      - ${PRETREND_HOST_DATA_DIR:-./data}:/app/data
      - ${PRETREND_HOST_LOG_DIR:-./logs}:/app/logs
      - ${PRETREND_STATE_DIR:-./state}:/app/state
      - ${PRETREND_CODEX_BIN_DIR:-./codex-bin}:/opt/pretrend/codex-bin:ro
      - ${PRETREND_CODEX_HOME_DIR:-./codex-home}:/root/.codex

  airflow-scheduler:
    volumes:
      - ${PRETREND_HOST_DATA_DIR:-./data}:/app/data
      - ${PRETREND_HOST_LOG_DIR:-./logs}:/app/logs
      - ${PRETREND_AIRFLOW_HOME_DIR:-./airflow_pretrend}:/opt/airflow/local
      - ${PRETREND_AIRFLOW_LOG_DIR:-./airflow_pretrend/logs}:/opt/airflow/logs
      - ${PRETREND_HOST_DAGS_DIR:-./dags}:/opt/airflow/dags:ro
      - ${PRETREND_HOST_SRC_DIR:-./src}:/opt/airflow/src:ro
```

규칙:

- `./.local/postgres-data`는 기본값일 뿐 고정 공식 경로가 아니다.
- 외장하드, local disk, WSL2 mount path는 같은 compose contract를 사용한다.
- Operational data가 있는 project에서 `docker compose down -v`는 금지한다.
- External drive를 active DB volume으로 쓸 때 Docker 실행 중 drive가 끊기면 DB가 손상될 수 있다.
- Restore verification은 반드시 별도 test DB 또는 별도 volume에서 수행하며 active DB를 덮어쓰지 않는다.
- DB contract smoke는 active DB에서 rollback하지 않고 `postgres-test`의 `pretrend_test*` DB에 synthetic row를 넣고 cleanup한다.

## 6. OS별 예시

Linux/macOS:

```bash
PRETREND_POSTGRES_DATA_DIR=/mnt/pretrend/postgres-data docker compose up -d postgres api
```

Windows PowerShell:

```powershell
$env:PRETREND_POSTGRES_DATA_DIR="E:\pretrend\postgres-data"
docker compose up -d postgres api
```

Windows + WSL2:

```bash
PRETREND_POSTGRES_DATA_DIR=/mnt/e/pretrend/postgres-data docker compose up -d postgres api
```

README 절차는 OS별 `docker compose` 원 명령을 포함해야 한다. Makefile target은 보조 UX일 수 있지만 유일한 공식 실행 경로가 되면 안 된다.

## 7. Docker build context

Docker image는 다음을 포함하면 안 된다.

- `.env`
- `.env.airflow`
- API key, token, password
- `.local/`
- `data/`
- `logs/`
- `result/`
- Airflow runtime log
- local cache와 virtual environment
- 대용량 parquet/csv/db output

Dev/test image는 test와 documentation contract 검증에 필요한 file을 포함해야 한다. 따라서 dev/test image에는 `tests/`와 필요한 `docs/` content가 있어야 한다.

권장 구조:

```text
docker/Dockerfile.api
docker/Dockerfile.api.dockerignore
docker/Dockerfile.dev
docker/Dockerfile.dev.dockerignore
docker/Dockerfile.airflow
docker/Dockerfile.airflow.dockerignore
requirements/api.txt
requirements/ci.txt
requirements/airflow.txt
```

Image 역할:

- API build는 `docker/Dockerfile.api`, `requirements/api.txt`를 사용한다.
- Dev/test build는 `docker/Dockerfile.dev`, `requirements/ci.txt`를 사용한다.
- Airflow build는 `docker/Dockerfile.airflow`, `requirements/airflow.txt`를 사용한다.
- Dev/test build는 `dags/`, `tests/`, 필요한 `docs/`를 포함한다.
- 모든 image context는 `.env`, `.env.airflow`, `.local`, `data`, `logs`, `result`를 제외한다.

## 8. Data bootstrap 계약

Pretrend에는 복구 규칙이 다른 두 data layer가 있다.

| Layer | 역할 | 복구 우선순위 |
| --- | --- | --- |
| Postgres serving DB | API/similarity/explainability serving state | `pg_dump -Fc` restore 우선. |
| File data lake | Bronze/Silver/Gold/source data | 필요할 때 bootstrap/backfill command로 재구성. |

Backfill은 reconstruction path이며 첫 번째 운영 복구 경로가 아니다. 정전 또는 머신 이동 복구 시 최신 dump가 있으면 DB dump restore를 먼저 사용한다.

복구 판단 순서:

1. 최신 dump가 있으면 Postgres serving DB를 별도 validation DB/volume에 먼저 restore한다. Active recovery는 validation evidence가 생긴 뒤 operator가 수행한다.
2. Dump가 없거나 오래되었으면 mounted data directory에 file data lake를 재구성한 뒤 Gold Parquet을 Postgres로 sync하고, 필요 시 similarity/explainability serving table을 다시 만든다.
3. Phase 3 dashboard scope/window/cache key 계약이 확정되기 전에는 historical explainability LLM backfill을 실행하지 않는다.

Sample mode는 repository fixture 또는 synthetic data만 사용한다. External API를 호출하거나 persistent serving DB state를 채우면 안 된다.

Backfill mode는 real volume이 `PRETREND_DATA_DIR`에 mount되어 있어야 하며, 기존 `PRETREND_DATA_ROOT` consumer도 같은 path를 가리켜야 한다. External API 사용은 명시적이어야 한다.

### 신규 clone / 새 머신 runbook

개발 환경을 새 머신으로 옮길 때는 다음 순서로 runtime을 복원한다.

1. Repository를 clone하고 local environment file을 만든다.

```powershell
git clone <repo-url> pretrend_ai
cd pretrend_ai
copy .env.example .env
```

2. `.env`에 local 값을 채운다. 필수 범주는 Postgres credential, `PRETREND_API_KEY`, Airflow admin credential, host path variable, backfill에 필요한 external data API key다. Secret 값은 committed file이나 Docker image에 들어가면 안 된다.

3. Service 시작 전 compose configuration을 검증한다.

```powershell
docker compose config --quiet
```

OS/shell 공통 1-command runtime reproduction은 repo root의 `reproduce.py`를 사용한다. 이 entrypoint는 Python 표준 라이브러리만 사용해 Docker Compose command를 직접 호출하므로 Windows, macOS, Linux에서 같은 명령 형태를 유지한다.

```bash
python reproduce.py
```

실행 순서는 다음과 같다.

1. `.env` 존재와 필수 secret placeholder 교체 여부를 확인한다.
2. `docker compose config --quiet`으로 runtime 계약을 검증한다.
3. Postgres를 먼저 기동하고, 선택적으로 `/backups` dump를 restore한다.
4. `backfill-once`를 marker 기반으로 실행한다.
5. Gold Parquet -> Postgres sync safety pass를 한 번 더 수행한다.
6. FastAPI를 기동한다.
7. Airflow init, webserver, scheduler를 기동한다.
8. `docker compose ps -a`와 API health check를 수행한다.

주요 옵션:

```bash
python reproduce.py --dry-run
python reproduce.py --skip-airflow
python reproduce.py --force-backfill
python reproduce.py --restore-dump pretrend_obs_YYYYMMDD.dump
python reproduce.py --backfill-start-date 2003-01-01 --backfill-end-date 2009-12-31 --gold-sync-start-date 2003-01-01
```

4. 최신 Postgres dump가 있으면 serving DB state를 먼저 restore한다.

```powershell
docker compose up -d postgres
docker compose exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges /backups/pretrend_obs_YYYYMMDD.dump'
```

5. Mounted file data lake가 비어 있거나 오래되었으면 1회성 bootstrap을 실행한다. 이 작업은 Macro/EOD Bronze/Silver/Gold를 재구성하고 Gold Parquet을 Postgres로 sync한다.

```powershell
docker compose --profile bootstrap up --build backfill-once
```

6. Serving runtime과 scheduler runtime을 시작한다.

```powershell
docker compose up -d api
docker compose --profile airflow up airflow-init
docker compose --profile airflow up -d airflow-webserver airflow-scheduler
```

7. Runtime health를 확인한다.

```powershell
docker compose ps
curl -H "X-API-Key: <PRETREND_API_KEY>" http://localhost:8000/api/v1/meta
```

`airflow-init`은 1회성 initializer다. `exited (0)`이면 성공이며 Airflow metadata는 `PRETREND_AIRFLOW_HOME_DIR`에 유지된다.

기존 bootstrap entrypoint:

| 단계 | 기존 entrypoint | 비고 |
| --- | --- | --- |
| Macro Bronze/Silver/Gold rebuild | `python -m pretrend.pipeline.macro_job --start YYYY-MM-DD --end YYYY-MM-DD` 또는 `macro_pipeline_dag` | `PRETREND_DATA_ROOT` 사용. 외부 data source를 호출할 수 있음. |
| EOD Bronze/Silver/Gold rebuild | `python -m pretrend.pipeline.eod_job --start YYYY-MM-DD --end YYYY-MM-DD` 또는 `eod_pipeline_dag` | `PRETREND_DATA_ROOT` 사용. 외부 data source를 호출할 수 있음. |
| Gold Parquet to Postgres sync | `gold_postgres_sync_dag` / `sync_gold_macro`, `sync_gold_eod` | Gold Parquet에서 serving DB로 incremental UPSERT. |
| Similarity derived table rebuild | `similarity_build_dag` with `query_start` / `query_end` conf | 명시 query window로 rebuild. |
| Explainability cache build | `explainability_build_dag` latest/on-demand conf only | Default provider는 mock. Phase 3 contract 전 full historical LLM backfill 금지. |
| Text data backfill | `python -m pretrend.pipeline.text.backfill ...` | Text observability path. Primary serving DB recovery path가 아니다. |

Docker runtime은 이 reconstruction path를 위해 1회성 `backfill-once` service를 제공한다. 외부 data source를 호출할 수 있으므로 `bootstrap` profile 뒤에 둔다. 이 service는 Macro/EOD Bronze/Silver/Gold를 실행하고, Gold Parquet을 Postgres로 sync한 뒤 `PRETREND_BACKFILL_MARKER_PATH`를 기록한다. 이후 실행은 `PRETREND_BACKFILL_FORCE=1`이 없으면 자동 skip된다.

기본 bootstrap range는 `2003-01-01`부터 직전 평일까지다. 긴 기본값은 의도적이다. 장기 regime 비교와 `ret_20d`, `ma_120`, `vol_60d` 같은 EOD feature warmup data가 필요하다.

1회성 bootstrap:

```bash
docker compose --profile bootstrap up --build backfill-once
```

강제 재실행:

```bash
PRETREND_BACKFILL_FORCE=1 docker compose --profile bootstrap up --build backfill-once
```

Historical prepend처럼 기존 Postgres watermark보다 과거 구간을 나중에 채우는 경우에는 Gold sync 범위를 별도로 연다. 그렇지 않으면 Parquet은 생겨도 Postgres mirror가 최신 watermark 이후만 읽어 과거 row가 API에 노출되지 않을 수 있다.

```bash
PRETREND_BACKFILL_START_DATE=2003-01-01 \
PRETREND_BACKFILL_END_DATE=2009-12-31 \
PRETREND_BACKFILL_MARKER_PATH=/app/data/meta/backfill_2003_2009.json \
PRETREND_GOLD_SYNC_START_DATE=2003-01-01 \
docker compose --profile bootstrap up --build backfill-once
```

전체 Gold Parquet을 다시 mirror에 upsert해야 하면 `PRETREND_GOLD_SYNC_FULL=1`을 1회성으로 사용한다. Scheduled DAG의 상시 설정값으로 두지 않는다.

같은 marker guard가 `macro_pipeline_dag`, `eod_pipeline_dag`, `gold_postgres_sync_dag`에 포함되어 있다. Manual Airflow run은 먼저 `pretrend.ops.backfill_once.run_backfill_once()`를 호출해야 한다. Marker가 있으면 fast skip하고, marker가 없으면 full Macro/EOD Bronze/Silver/Gold bootstrap과 Gold-to-Postgres sync를 수행한 뒤 normal incremental task를 진행한다.

범위를 좁히거나 custom sequence가 필요하면 `worker` service로 manual operator command를 실행할 수 있다.

```bash
docker compose run --rm worker python -m pretrend.pipeline.macro_job --start YYYY-MM-DD --end YYYY-MM-DD
docker compose run --rm worker python -m pretrend.pipeline.eod_job --start YYYY-MM-DD --end YYYY-MM-DD
docker compose run --rm worker python -c "from pretrend.pipeline.sync.gold_postgres import sync_gold_macro, sync_gold_eod; print(sync_gold_macro()); print(sync_gold_eod())"
```

### Airflow Docker profile

Dockerized scheduler path는 선택사항이며 `airflow` profile 뒤에 있다. 일반 API recovery를 가볍게 유지하면서도 DAG 기반 운영 모델을 보존한다.

로컬 Docker runtime은 backup된 desktop runtime과 맞추기 위해 Airflow 2.10.5로 고정한다. `airflow-webserver`, `airflow-scheduler`, FAB authentication, `SequentialExecutor`, SQLite metadata DB file을 사용한다.

최초 시작:

```bash
docker compose --profile bootstrap up --build backfill-once
docker compose --profile airflow build airflow-init airflow-webserver airflow-scheduler
docker compose --profile airflow up airflow-init
docker compose --profile airflow up -d airflow-webserver airflow-scheduler
```

UI는 `http://localhost:8080`에서 확인한다. Admin account는 `.env`의 `AIRFLOW_ADMIN_USER`, `AIRFLOW_ADMIN_PASSWORD`로 생성 또는 갱신된다. 둘 중 하나가 비어 있으면 `airflow-init`은 실패해야 한다.

`strategy_engine_dag`는 LLM report generation을 `PRETREND_REPORT_API_URL`을 통해 FastAPI service에 위임한다. Airflow는 scheduler/data-runner이며, 선택된 API runtime이 Codex analyzer execution을 소유한다. Docker API mode에서는 `api` container가 담당한다. Linux `codex` binary를 `PRETREND_CODEX_BIN_DIR`에 복사 또는 mount하고, Codex state는 `PRETREND_CODEX_HOME_DIR`로 mount한다. Host-local FastAPI mode에서는 Windows host process가 VS Code extension binary/session을 재사용하고, Airflow는 `http://host.docker.internal:8100/...`을 호출한다.

Host-local FastAPI mode:

```powershell
$env:PYTHONPATH = "src"
$env:PRETREND_STATE_DB = ".\state\orchestrator.db"
uvicorn pretrend.api.main:app --host 0.0.0.0 --port 8100
```

Airflow container용 `.env` 설정:

```text
PRETREND_REPORT_API_URL=http://host.docker.internal:8100/api/v1/report/strategy/analyze
```

`.env` 변경 후 Airflow 재생성:

```bash
docker compose --profile airflow up -d --force-recreate airflow-webserver airflow-scheduler
```

DAG 목록 확인:

```bash
docker compose --profile airflow run --rm airflow-init airflow dags list
```

Scheduled collection이 필요할 때 unpause할 권장 DAG:

```bash
docker compose --profile airflow run --rm airflow-init airflow dags unpause eod_pipeline_dag
docker compose --profile airflow run --rm airflow-init airflow dags unpause macro_pipeline_dag
docker compose --profile airflow run --rm airflow-init airflow dags unpause gold_postgres_sync_dag
docker compose --profile airflow run --rm airflow-init airflow dags unpause similarity_build_dag
docker compose --profile airflow run --rm airflow-init airflow dags unpause explainability_build_dag
```

Archived execution DAG는 명시적으로 테스트하지 않는 한 paused 상태를 유지한다.

```bash
docker compose --profile airflow run --rm airflow-init airflow dags pause strategy_engine_dag
docker compose --profile airflow run --rm airflow-init airflow dags pause paper_trading_dag
docker compose --profile airflow run --rm airflow-init airflow dags pause broker_mock_trading_dag
```

규칙:

- Airflow metadata는 `/opt/airflow/local/airflow.db`에 저장되며 `PRETREND_AIRFLOW_HOME_DIR`가 backing한다.
- DAG task는 `/app/data`에 file data를 쓰며 `PRETREND_HOST_DATA_DIR`가 backing한다.
- Airflow log는 `/opt/airflow/logs`에 쓰며 `PRETREND_AIRFLOW_LOG_DIR`가 backing한다.
- Strategy report analyzer state는 `/app/state`에 쓰며 `PRETREND_STATE_DIR`가 backing한다.
- File data lake가 비어 있으면 scheduled EOD/Macro/Gold sync DAG를 unpause하기 전에 `backfill-once`를 실행한다.
- 최신 DB dump restore가 첫 번째 recovery path이며, Airflow scheduling은 restore 이후 ongoing collection을 재개한다.

## 9. DB backup / restore

Backup command:

```bash
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /backups/pretrend_obs_YYYYMMDD.dump'
```

Dump validation:

```bash
docker compose exec -T postgres sh -c 'test -s /backups/pretrend_obs_YYYYMMDD.dump'
docker compose exec -T postgres sh -c 'pg_restore -l /backups/pretrend_obs_YYYYMMDD.dump' >/tmp/pretrend_obs_YYYYMMDD.list
```

Restore 전에 catalog file에 예상 schema object가 있어야 한다. 최소한 migration metadata와 serving table을 확인한다.

```bash
grep -E 'TABLE DATA public (alembic_version|gold_macro_features|gold_eod_features|similarity_regime|similarity_gold|gold_market_state_similarity_feature|explainability_cache)' /tmp/pretrend_obs_YYYYMMDD.list
```

Restore validation은 별도 DB 또는 별도 volume에서 수행한다. Verification 과정에서 active `pretrend_obs` DB를 덮어쓰면 안 된다.

별도 DB validation shape:

```bash
docker compose exec -T postgres sh -c 'createdb -U "$POSTGRES_USER" pretrend_restore_check'
docker compose exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d pretrend_restore_check --no-owner --no-privileges /backups/pretrend_obs_YYYYMMDD.dump'
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d pretrend_restore_check -Atc "SELECT COUNT(*) FROM alembic_version;"'
docker compose exec -T postgres sh -c 'dropdb -U "$POSTGRES_USER" pretrend_restore_check'
```

별도 volume validation shape:

```bash
PRETREND_POSTGRES_DATA_DIR=./.local/postgres-restore-check \
PRETREND_BACKUP_DIR=./.local/backups \
docker compose -p pretrend-restore-check up -d postgres
docker compose -p pretrend-restore-check exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges /backups/pretrend_obs_YYYYMMDD.dump'
docker compose -p pretrend-restore-check exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT COUNT(*) FROM alembic_version;"'
```

검증 후 check project는 operational volume을 삭제하지 않고 stop한다.

```bash
docker compose -p pretrend-restore-check stop postgres
```

정상 project나 operational data가 들어 있는 project name에는 `docker compose down -v`를 실행하지 않는다.

## 10. 재현성 검증

P30은 fresh clone에서 다음을 검증할 수 있어야 완료다.

- API runtime Docker build.
- Dev/test runtime Docker build.
- Docker pytest 또는 합의된 smoke test.
- `docker compose config --quiet`.
- Postgres volume mount path.
- Backup directory mount path.
- API health check.
- DB dump catalog check.
- 별도 DB/volume restore procedure.
- Sensitive file이 Git/build context/image에서 제외됨.
- README command가 Linux/WSL2와 Windows PowerShell에서 실행 가능함.

표준 검증 command set:

```bash
docker compose config --quiet
docker compose build
docker compose up -d postgres api
docker compose ps
docker build -t pretrend-dev -f docker/Dockerfile.dev .
docker run --rm pretrend-dev pytest --gate fast -q --tb=short
docker run --rm pretrend-dev pytest --gate runtime -q --tb=short
docker compose --profile test run --rm test-runner
```

`test-runner`는 운영 DB와 분리된 `postgres-test`를 사용한다. 실행 순서는 test DB healthcheck, Alembic migration, `tests/ops/test_db_synthetic_data_contract.py` 순서다. 이 테스트는 핵심 serving table에 synthetic row를 넣고 읽은 뒤 test DB 내부에서 cleanup한다.

Sensitive-file image check:

```bash
docker run --rm --entrypoint sh pretrend-api-test -c 'test ! -e /app/.env && test ! -d /app/data && test ! -d /app/logs && test ! -d /app/result && test ! -d /app/tests && test ! -d /app/docs'
docker run --rm --entrypoint sh pretrend-dev -c 'test ! -e /app/.env && test ! -d /app/data && test ! -d /app/logs && test ! -d /app/result && test -d /app/tests && test -d /app/docs'
```

## 11. Docs / Agent 공개 정책

`.agent`, `CLAUDE.md`, `AGENTS.md` 공개는 whitelist 방식으로만 한다. `.agent` 전체를 unignore하지 않는다.

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

기본 제외 후보:

- `.agent/settings.local.json`
- `.agent/RUN_LOG.md`
- `.agent/task/archive/`
- large archives
- local-path-heavy session notes
- 실제 secret 값이 포함된 file

Docs는 marker로 분류해 publication과 onboarding을 기계적으로 확인할 수 있어야 한다. Marker vocabulary는 `docs/README.md`에 정의한다.

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

## 12. 변경 이력

- 2026-05-15: P30 planning에서 initial draft 작성.
- 2026-05-15: P30-1 compose runtime volume variable과 OS별 예시 정렬.
- 2026-05-15: P30-2 API/dev-test Docker build 역할 분리와 Dockerfile별 ignore file 추가.
- 2026-05-15: P30-3 restore-first/backfill-fallback data bootstrap contract와 restore validation shape 고정.
- 2026-05-15: P30-4 standard reproducibility verification과 sensitive-file image check 추가.
- 2026-05-15: P30-5/P30-6 agent publication whitelist와 docs marker classification 고정.
- 2026-05-15: Restore-first recovery priority를 유지하면서 local Docker Airflow profile 추가.
- 2026-05-16: Docker Airflow profile을 backup된 desktop runtime과 맞추기 위해 Airflow 2.10.5 webserver/scheduler로 고정.
- 2026-05-16: Scheduled DAG 운영 전 raw data lake를 재구성하는 Docker `backfill-once` bootstrap profile 추가.
- 2026-05-16: Empty file data lake에서 manual Airflow run이 안전하도록 Macro/EOD/Gold sync DAG에 bootstrap marker guard 추가.
- 2026-05-16: `.env`, restore, backfill, API, Airflow startup 순서를 연결한 신규 clone / 새 머신 runbook 추가.
- 2026-05-16: 문서 기준 언어를 한국어로 정리.
- 2026-05-17: 운영 DB rollback 방식 대신 격리 `postgres-test`/`test-runner` profile과 synthetic row DB smoke 검증 절차 추가.
