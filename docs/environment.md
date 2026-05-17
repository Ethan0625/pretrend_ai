# 개발/운영 환경 구성

Markers: operation, security
Status: active

**프로젝트:** Pretrend — Reproducible Market Data Platform
**버전:** 2026.05.16
**목적:** 신규 clone / 새 머신에서 같은 데이터 플랫폼 런타임을 재현하기 위한 환경 기준

이 문서는 현재 운영 기준의 환경만 다룬다. Pretrend의 기준 환경은 금융·거시 데이터를 재현 가능한 방식으로 수집·정제하고, point-in-time 안전한 feature layer를 만드는 **Docker Compose + host bind mount + Airflow 2 profile**이다. 과거 GPU 서버, vLLM, 로컬 Conda Airflow 중심 설정은 기본 운영 기준이 아니다.

참조:

- [`README.md`](../README.md)
- [`operation/reproducible_runtime_contract.md`](operation/reproducible_runtime_contract.md)
- [`operation_guide.md`](operation_guide.md)

---

## 1. 기준 환경

### 필수 조건

| 항목 | 기준 |
| --- | --- |
| OS | Windows + Docker Desktop, 또는 Linux + Docker Engine |
| Docker | Docker Compose v2 사용 |
| Python | 3.11 계열 |
| DB | `timescale/timescaledb:2.27.0-pg16` |
| Airflow | Docker image 기반 Airflow 2.10.5 |
| GPU | 필수 아님 |

Pretrend의 현재 운영 표면은 file data lake, Postgres serving mirror, FastAPI read-only API, Airflow DAG 실행이다. 기본 설치에 CUDA/PyTorch/vLLM stack은 포함하지 않는다.

### 권장 로컬 기준

Windows에서는 Docker Desktop을 켠 뒤 PowerShell에서 루트 `docker-compose.yml`을 기준으로 실행한다.

```powershell
docker compose config --quiet
docker compose up -d postgres api
docker compose ps
```

Linux 또는 WSL2에서도 명령은 동일하다. 경로 차이는 `.env`의 host path 변수로 흡수한다.

---

## 2. 파일/폴더 구조

현재 repo의 운영 관련 파일 배치는 다음을 기준으로 한다.

```text
pretrend_ai/
├─ README.md                         # 프로젝트 진입점
├─ docker-compose.yml                # 기본 로컬 runtime 진입점
├─ pyproject.toml                    # package/test 설정
├─ requirements.txt                  # CPU-only 로컬 개발/검증 진입점
├─ .env.example                      # 환경 변수 템플릿
├─ .dockerignore                     # 기본 build context 제외 규칙
├─ docker/
│  ├─ Dockerfile.api                 # FastAPI serving image
│  ├─ Dockerfile.api.dockerignore
│  ├─ Dockerfile.dev                 # test/docs/ops 검증 image
│  ├─ Dockerfile.dev.dockerignore
│  ├─ Dockerfile.airflow             # Airflow 2 webserver/scheduler image
│  └─ Dockerfile.airflow.dockerignore
├─ requirements/
│  ├─ api.txt                        # API runtime 최소 의존성
│  ├─ ci.txt                         # dev/test 검증 의존성
│  └─ airflow.txt                    # DAG runtime 의존성
├─ dags/                             # Airflow DAG
├─ migrations/                       # Alembic migration
├─ src/pretrend/
│  ├─ api/                           # FastAPI read-only API
│  ├─ models/                        # SQLAlchemy/Pydantic schema
│  ├─ observability/                 # regime, similarity, explainability
│  ├─ ops/                           # bootstrap/backfill helper
│  └─ pipeline/                      # Bronze/Silver/Gold pipeline
├─ tests/                            # pytest test suite
├─ docs/                             # 설계/운영/데이터 문서
├─ data/                             # host-mounted file data lake, gitignored
├─ logs/                             # host-mounted logs, gitignored
├─ state/                            # local runtime state, gitignored
└─ airflow_pretrend/                 # Airflow metadata/log mount, gitignored
```

`docker-compose.yml`은 루트에 둔다. 새 환경에서 `docker compose ...` 명령을 바로 사용할 수 있게 하는 진입점이기 때문이다. Dockerfile 실물과 Dockerfile별 ignore 파일은 `docker/` 아래에서 역할별로 관리한다.

---

## 3. 의존성 정책

| 파일 | 용도 |
| --- | --- |
| `requirements.txt` | 로컬 개발/검증 기본 진입점. `requirements/ci.txt`를 참조한다. |
| `requirements/api.txt` | API container 최소 runtime 의존성. |
| `requirements/ci.txt` | pytest, docs/runtime contract 검증 의존성. |
| `requirements/airflow.txt` | Airflow DAG runtime 의존성. |

기본 requirements에는 GPU 추론 stack을 넣지 않는다. 현재 explainability/report 경로는 외부 API 또는 Codex binary 호출 방식이며, Python runtime 안에 CUDA stack을 설치할 필요가 없다.

로컬 Python 환경이 필요할 때만 다음처럼 설치한다.

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
```

Docker 기준 검증은 아래 명령을 사용한다.

```bash
docker build -t pretrend-dev -f docker/Dockerfile.dev .
docker run --rm pretrend-dev pytest --gate fast -q --tb=short
```

---

## 4. 환경 변수

실제 값은 `.env`에 둔다. `.env`는 gitignored이며, 템플릿은 `.env.example`이다.

### 필수 값

| 변수 | 설명 |
| --- | --- |
| `POSTGRES_USER` | Postgres 사용자 |
| `POSTGRES_PASSWORD` | Postgres 비밀번호 |
| `POSTGRES_DB` | serving DB 이름 |
| `POSTGRES_PORT` | host 노출 포트 |
| `PRETREND_API_KEY` | API key |
| `AIRFLOW_ADMIN_USER` | Airflow admin 계정 |
| `AIRFLOW_ADMIN_PASSWORD` | Airflow admin 비밀번호 |
| `AIRFLOW_ADMIN_EMAIL` | Airflow admin 이메일 |

### Host path 값

| 변수 | 기본값 | container mount |
| --- | --- | --- |
| `PRETREND_POSTGRES_DATA_DIR` | `./.local/postgres-data` | `/var/lib/postgresql/data` |
| `PRETREND_BACKUP_DIR` | `./.local/backups` | `/backups` |
| `PRETREND_HOST_DATA_DIR` | `./data` | `/app/data` |
| `PRETREND_HOST_LOG_DIR` | `./logs` | `/app/logs` |
| `PRETREND_STATE_DIR` | `./state` | `/app/state` |
| `PRETREND_AIRFLOW_HOME_DIR` | `./airflow_pretrend` | `/opt/airflow/local` |
| `PRETREND_AIRFLOW_LOG_DIR` | `./airflow_pretrend/logs` | `/opt/airflow/logs` |
| `PRETREND_HOST_DAGS_DIR` | `./dags` | `/opt/airflow/dags` |
| `PRETREND_HOST_SRC_DIR` | `./src` | `/opt/airflow/src` |

Windows 경로, 외장 디스크, WSL2 경로를 사용할 때는 `.env`에서 위 값을 명시한다.

### Backfill / Gold sync 값

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `PRETREND_BACKFILL_START_DATE` | `2003-01-01` | 1회성 data lake bootstrap 시작일 |
| `PRETREND_BACKFILL_END_DATE` | 빈 값 | 빈 값이면 직전 평일까지 실행 |
| `PRETREND_BACKFILL_FORCE` | `0` | marker가 있어도 backfill을 다시 실행할지 여부 |
| `PRETREND_BACKFILL_MARKER_PATH` | `/app/data/meta/bootstrap_backfill_once.json` | bootstrap 완료 marker |
| `PRETREND_GOLD_SYNC_START_DATE` | 빈 값 | Postgres mirror sync를 특정 과거 날짜부터 다시 열 때 사용 |
| `PRETREND_GOLD_SYNC_FULL` | `0` | 전체 Gold Parquet을 1회성으로 다시 upsert할 때만 사용 |

---

## 5. Compose 서비스

| 서비스 | 역할 |
| --- | --- |
| `postgres` | TimescaleDB serving DB |
| `api` | FastAPI read-only API |
| `worker` | 수동 ops/backfill helper, `ops` profile |
| `backfill-once` | 1회성 data lake bootstrap, `bootstrap` profile |
| `airflow-init` | Airflow metadata/user 초기화, `airflow` profile |
| `airflow-webserver` | Airflow UI, `airflow` profile |
| `airflow-scheduler` | Airflow scheduler, `airflow` profile |

기본 API/Postgres 실행:

```bash
docker compose up -d postgres api
```

빈 file data lake bootstrap:

```bash
docker compose --profile bootstrap up --build backfill-once
```

OS 공통 1-command runtime reproduction:

```bash
python reproduce.py
```

`python reproduce.py`는 `.env` 검증, `docker compose config --quiet`, Postgres 기동, marker 기반 backfill, Gold-to-Postgres sync, API/Airflow 기동, health check를 순서대로 실행한다. shell-specific syntax가 필요한 환경변수 prefix 대신 다음 옵션을 사용한다.

```bash
python reproduce.py --force-backfill
python reproduce.py --skip-airflow
python reproduce.py --dry-run
```

Airflow 실행:

```bash
docker compose --profile airflow up airflow-init
docker compose --profile airflow up -d airflow-webserver airflow-scheduler
```

`airflow-init`은 1회성 initializer다. `exited (0)` 상태는 정상이다.

---

## 6. Data lake와 DB 복구 기준

Postgres serving DB는 최신 `pg_dump -Fc` dump가 있으면 restore를 우선한다. File data lake가 비어 있거나 오래되었을 때만 backfill을 사용한다.

```bash
docker compose up -d postgres
docker compose exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges /backups/pretrend_obs_YYYYMMDD.dump'
docker compose --profile bootstrap up --build backfill-once
docker compose up -d api
```

주의:

- `docker compose down -v`는 운영 데이터 삭제 위험이 있으므로 사용하지 않는다.
- `PRETREND_HOST_DATA_DIR`와 `PRETREND_POSTGRES_DATA_DIR`는 의도한 host 경로를 가리키는지 먼저 확인한다.
- `PRETREND_DATA_DIR`와 `PRETREND_DATA_ROOT`는 container 내부에서 `/app/data`로 맞춘다.

---

## 7. Airflow DAG 기준

현재 데이터 파이프라인 운영 DAG:

| DAG | 역할 |
| --- | --- |
| `macro_pipeline_dag` | Macro Bronze → Silver → Gold |
| `eod_pipeline_dag` | EOD Bronze → Silver → Gold |
| `gold_postgres_sync_dag` | Gold Parquet → Postgres mirror |

위 DAG에는 bootstrap marker guard가 포함되어 있다. Marker가 없으면 manual trigger 시 먼저 `backfill-once`와 같은 Macro/EOD Bronze → Silver → Gold bootstrap 및 Gold-to-Postgres sync를 수행한 뒤 정상 task를 이어간다.

---

## 8. 선택 기능

### Codex binary 기반 report 분석

Docker 내부에서 Codex binary를 사용할 때는 다음 mount를 사용한다.

| 변수 | 기본값 | container path |
| --- | --- | --- |
| `PRETREND_CODEX_BIN_DIR` | `./codex-bin` | `/opt/pretrend/codex-bin` |
| `PRETREND_CODEX_HOME_DIR` | `./codex-home` | `/root/.codex` |

Windows host-local Codex 분석을 사용할 때는 host에서 FastAPI를 실행하고 Airflow의 `PRETREND_REPORT_API_URL`을 `http://host.docker.internal:8100/api/v1/report/strategy/analyze` 형태로 지정한다.

### GPU/LLM runtime

GPU, Ollama, vLLM, model cache는 현재 Docker 재현성 기준의 필수 항목이 아니다. 필요할 때 별도 문서 또는 별도 compose profile로 다룬다.

---

## 9. 검증 게이트

```bash
docker compose config --quiet
docker compose build
docker compose up -d postgres api
docker compose ps
docker build -t pretrend-dev -f docker/Dockerfile.dev .
docker run --rm pretrend-dev pytest --gate fast -q --tb=short
```

문서/운영 계약 변경 후 최소 검증:

```bash
pytest tests/ops/test_reproducible_runtime_contract.py -q --tb=short
```
