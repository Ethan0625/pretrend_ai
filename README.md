# Pretrend: Reproducible Market Data Platform

### 금융·거시 데이터 재현성 플랫폼

v.26.05.17 (Reproducible Market Data Platform)

Pretrend는 금융·거시 데이터를 재현 가능한 방식으로 수집·정제하고, point-in-time 안전한 feature layer를 구축하기 위한 **market data platform** 프로젝트다.

이 프로젝트의 목적은 예측 모델이나 자동매매 시스템을 먼저 만드는 것이 아니라, 시장 판단 이전 단계에서 데이터 정합성, 시점 안전성, 재처리 가능성, 운영 재현성을 확보하는 것이다.

> 이 저장소는 **투자 추천/AI 매매 신호/수익률 예측 시스템이 아니다.**
> Bronze → Silver → Gold 데이터 레이어 위에서, ETF/Macro 데이터를 point-in-time 안전한 관측 입력으로 만드는 시스템이다.

**핵심 목표**: 재현 가능한 데이터 플랫폼을 직접 설계·검증·복구하는 경험 — 수집 안정성, 데이터 정합성, PIT 안전성, 운영 재현성, 배포 규율.

---

## 왜 만들었나

투자 영역에서는 "거시경제 흐름이 중요하다"는 말을 자주 하지만, 실제로 거시 이벤트와 시장 구조 변화가 어떤 방식으로 연결되는지를 반복적으로 확인할 수 있는 개인용 도구는 많지 않다. 저는 투자 전망을 제시하기보다, 무료로 접근 가능한 거시·ETF 데이터를 기반으로 시장 상태를 구조화하고, 특정 시점의 시장 구조가 과거 어떤 구간과 유사하거나 다른지를 재현 가능한 방식으로 관측하는 시스템을 만들고자 했다.

## 왜 이 방향인가

초기 Pretrend는 로컬 기반 매매 실험 구조였으나, 프로젝트 목적을 예측에서 데이터 플랫폼과 시장 구조 관측 기반으로 전환하면서 공개 운영 가능한 데이터 시스템으로 재설계하고 있다.

이에 따라 로컬 의존 배치 구조를 정리하고, 자동화된 스케줄러 기반 수집, Bronze/Silver/Gold 데이터 레이어, market state feature 생성, dashboard serving, freshness monitoring 구조로 전환하고 있다.

---

## 현재 범위

현재 공개 기준의 주 시스템은 **재현 가능한 market data platform**이다. 시장 구조 관측, historical similarity, explanation layer는 이 데이터 플랫폼 위에 올라가는 read-only 소비 계층이다.

- 현재 운영 범위: Macro/EOD data lake, PIT-safe Gold feature layer, Postgres serving mirror, similarity, explainability, read-only FastAPI, Docker/Airflow runtime.
- 보관 맥락: 초기 strategy/backtest/paper-trading 실험 코드는 구현 이력으로 repo에 남아 있지만, 현재 공개 운영 표면은 아니다.
- 공개 포지셔닝: 이 repo는 trading performance나 investment advice가 아니라, 재현 가능한 데이터/런타임 운영 역량을 보여준다.

---

## 프로젝트 성격

- **재현 가능한 market data platform**: 금융·거시 데이터를 반복 가능한 방식으로 수집·정제·제공한다.
- **재현 가능한 시계열 데이터 파이프라인**: Bronze → Silver → Gold 레이어 기반 PIT-safe snapshot.
- **계층형 데이터 아키텍처**: 원본 보존(Bronze), 정합성 보정(Silver), 관측 입력 준비(Gold)를 책임별로 분리.
- **과거 유사도 관측**: 현재 시장 구조와 과거 시기의 구조적 유사성 관측 — 예측 아닌 설명.
- **설명 계층**: LLM은 이미 구축된 관측 결과 설명에만 사용. 예측/추천 금지.

## 설계 이유

- 시계열 데이터를 바로 모델이나 전략으로 연결하면 `release_date`, `trade_date`, snapshot 기준이 섞이면서 재현성과 설명 가능성이 무너진다.
- 거시/가격 데이터는 같은 "날짜"를 갖고 있어도 실제로는 가용 시점이 다르므로, 판단 이전에 point-in-time 기준을 먼저 고정해야 한다.
- 배치 재실행이나 백필이 자주 일어나는 데이터 파이프라인에서는 overwrite, atomic write, lineage가 없으면 partial state와 schema drift가 누적된다.
- 전략 성능 실험보다 먼저, **동일 입력이면 동일 결과가 나오는 데이터 기반**을 만드는 것이 운영적으로 더 중요하다고 보고 설계했다.

## 아키텍처 개요

```text
Bronze -> Silver -> Gold Parquet SOT -> Postgres Mirror -> FastAPI -> Dashboard

Bronze         : 원천 수집과 원본 보존
Silver         : 정규화, 중복 제거, 계약 정렬 feature
Gold           : PIT-safe feature snapshot
Postgres       : API/dashboard 조회용 serving mirror/cache
FastAPI        : 읽기 전용 관측 API
```

- **Layer**는 데이터를 어떻게 만들고 저장하는가에 대한 책임을 가진다.
- **Gold Parquet**는 feature SOT이고, Postgres는 dashboard/API를 위한 serving mirror다.
- API와 dashboard는 관측 결과를 읽기만 하며, 데이터 레이어나 feature SOT를 다시 쓰지 않는다.

## 운영 원칙

- **계약 우선**: 구현보다 `docs/architecture/*_contract.md`의 grain, key, invariant를 우선한다.
- **Point-in-time 안전성**: Gold는 `selected_release_date < trade_date` 규칙을 지켜 미래 정보 누출을 막는다.
- **Snapshot 재현성**: 결과는 `decision_date` 및 파티션 기준으로 저장하고, 동일 입력 재실행 시 overwrite로 동일 산출물을 남긴다.
- **원자적·멱등 write**: `_tmp_run` 경유 후 atomic rename, 동일 파티션 overwrite를 기본 원칙으로 둔다.
- **명시적 UNKNOWN 기반 fail-open**: 결측이 있어도 schema는 유지하고 downstream에는 `UNKNOWN`을 전달한다.
- **관측 가능성과 검증성**: lineage, evidence column, contract test로 "왜 이 값이 나왔는지"를 추적 가능하게 유지한다.
- **읽기 전용 serving 경계**: API와 dashboard는 Gold/Postgres 산출물을 조회하며 upstream feature generation을 변경하지 않는다.

## 재현 가능한 런타임

Phase 3 dashboard 진입 전 P30에서 Docker runtime, Postgres volume path, DB backup/restore, dev/test image, 신규 clone 검증 기준을 고정한다.

기본 실행은 repo-local path를 사용한다.

```bash
docker compose up -d postgres api web
```

Dashboard는 `http://localhost:3000`, API는 `http://localhost:8000`에서 확인한다.

Postgres data와 backup 위치는 host env var로 바꿀 수 있다.

Linux/macOS:

```bash
PRETREND_POSTGRES_DATA_DIR=/mnt/pretrend/postgres-data \
PRETREND_BACKUP_DIR=/mnt/pretrend/backups \
docker compose up -d postgres api
```

Windows PowerShell:

```powershell
$env:PRETREND_POSTGRES_DATA_DIR="E:\pretrend\postgres-data"
$env:PRETREND_BACKUP_DIR="E:\pretrend\backups"
docker compose up -d postgres api
```

Windows + WSL2:

```bash
PRETREND_POSTGRES_DATA_DIR=/mnt/e/pretrend/postgres-data \
PRETREND_BACKUP_DIR=/mnt/e/pretrend/backups \
docker compose up -d postgres api
```

런타임 계약:

- [docs/operation/reproducible_runtime_contract.md](docs/operation/reproducible_runtime_contract.md)

신규 clone / 새 머신 빠른 시작:

```powershell
git clone <repo-url> pretrend_ai
cd pretrend_ai
copy .env.example .env
docker compose config --quiet
```

OS와 shell에 의존하지 않는 1-command bootstrap은 다음 entrypoint를 사용한다. `.env`에 Postgres/API/Airflow/FRED 값을 채운 뒤 실행하면 Docker Compose 검증, Postgres 기동, data lake bootstrap, Gold-to-Postgres sync, FastAPI, Airflow 초기화와 기동, health check를 순서대로 수행한다.

```bash
python reproduce.py
```

주요 옵션:

```bash
python reproduce.py --dry-run
python reproduce.py --skip-airflow
python reproduce.py --force-backfill
python reproduce.py --backfill-start-date 2003-01-01 --backfill-end-date 2009-12-31 --gold-sync-start-date 2003-01-01
```

`.env`에는 로컬 Postgres, API, Airflow admin, host path, 외부 data API 값을 채운다. 최신 DB dump가 있으면 먼저 restore한다.

```powershell
docker compose up -d postgres
docker compose exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges /backups/pretrend_obs_YYYYMMDD.dump'
```

마운트된 file data lake가 비어 있거나 오래되었으면 다시 만들고, API와 Airflow를 초기화한다.

```powershell
docker compose --profile bootstrap up --build backfill-once
docker compose up -d api
docker compose --profile airflow up airflow-init
docker compose --profile airflow up -d airflow-webserver airflow-scheduler
```

`airflow-init`은 1회성 초기화 서비스다. `exited (0)`은 정상 성공 상태다.

Docker 이미지 역할:

```bash
# API serving 이미지
docker build -t pretrend-api-test -f docker/Dockerfile.api .

# tests/docs를 포함한 dev/test 이미지
docker build -t pretrend-dev -f docker/Dockerfile.dev .
docker run --rm pretrend-dev pytest --gate fast -q --tb=short

# DAG 운영용 Airflow 2 scheduler/webserver 이미지
docker build -t pretrend-airflow -f docker/Dockerfile.airflow .
```

`docker/Dockerfile.api`는 `requirements/api.txt`를 사용해 serving runtime을 작게 유지한다. `docker/Dockerfile.dev`는 `requirements/ci.txt`를 사용하며 재현성 검증에 필요한 `dags/`, `tests/`, `docs/`를 포함한다. `docker/Dockerfile.airflow`는 DAG scheduling을 위해 `requirements/airflow.txt`를 사용한다. data, logs, local DB volume, `.env`, 기타 secret은 Docker build context에서 제외한다.

P30 검증 게이트:

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

`test-runner`는 운영 DB가 아니라 `postgres-test` service의 격리된 `pretrend_test*` DB를 사용한다. 실행 전에 Alembic migration을 적용하고, 핵심 serving table에 synthetic row를 insert/read한 뒤 test DB 안에서 cleanup한다. 운영 DB에는 dummy row를 넣지 않는다.

Volume 및 민감 파일 확인:

```bash
docker compose exec -T postgres sh -c 'test -d /var/lib/postgresql/data'
docker compose exec -T postgres sh -c 'test -d /backups'
git status --ignored --short .env .env.airflow .local data logs result .agent
```

Data recovery는 restore-first 원칙을 따른다.

```bash
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /backups/pretrend_obs_YYYYMMDD.dump'
docker compose exec -T postgres sh -c 'test -s /backups/pretrend_obs_YYYYMMDD.dump'
docker compose exec -T postgres sh -c 'pg_restore -l /backups/pretrend_obs_YYYYMMDD.dump' >/tmp/pretrend_obs_YYYYMMDD.list
```

Restore 검증은 별도 DB를 사용한다.

```bash
docker compose exec -T postgres sh -c 'createdb -U "$POSTGRES_USER" pretrend_restore_check'
docker compose exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d pretrend_restore_check --no-owner --no-privileges /backups/pretrend_obs_YYYYMMDD.dump'
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d pretrend_restore_check -Atc "SELECT COUNT(*) FROM alembic_version;"'
docker compose exec -T postgres sh -c 'dropdb -U "$POSTGRES_USER" pretrend_restore_check'
```

Backfill은 최신 dump가 없거나 오래된 경우에만 사용한다. Backfill은 먼저 file data lake를 재구성하고, 이후 Gold Parquet을 Postgres로 sync한다. serving DB 상태 복구의 1순위 경로가 아니다. 기존 data lake job은 `PRETREND_DATA_ROOT`를 읽으므로, Docker/backfill 실행 시 container에 mount된 data directory와 같은 path를 가리키게 해야 한다.

```bash
PRETREND_DATA_ROOT=/app/data
```

새 file data lake이거나 비어 있는 경우, scheduled DAG를 unpause하기 전에 1회성 Docker bootstrap을 실행한다. 이 작업은 Macro/EOD Bronze -> Silver -> Gold를 채우고, Gold Parquet을 Postgres로 sync한 뒤 `data/meta/bootstrap_backfill_once.json` marker를 기록한다. 이후 실행은 강제 옵션이 없으면 skip된다.

```bash
docker compose --profile bootstrap up --build backfill-once
```

기본 backfill 시작일은 `2003-01-01`이고 종료일은 직전 평일이다. 긴 기본값은 장기 regime 비교와 rolling EOD feature warmup을 함께 확보하기 위함이다. 범위를 바꾼 뒤 다시 실행하려면 `PRETREND_BACKFILL_FORCE=1`을 설정한다.

과거 구간을 나중에 앞쪽으로 붙이는 경우에는 Postgres sync가 최신 watermark 이후만 읽지 않도록 historical sync 범위도 함께 지정한다.

```bash
PRETREND_BACKFILL_START_DATE=2003-01-01 \
PRETREND_BACKFILL_END_DATE=2009-12-31 \
PRETREND_BACKFILL_MARKER_PATH=/app/data/meta/backfill_2003_2009.json \
PRETREND_GOLD_SYNC_START_DATE=2003-01-01 \
docker compose --profile bootstrap up --build backfill-once
```

같은 marker guard가 `macro_pipeline_dag`, `eod_pipeline_dag`, `gold_postgres_sync_dag` 앞단에서 실행된다. bootstrap marker가 없는 상태에서 DAG를 manual trigger하면 Airflow가 먼저 1회성 Macro/EOD Bronze -> Silver -> Gold backfill과 Gold-to-Postgres sync를 수행한 뒤 정상 DAG task를 이어간다.

Airflow는 scheduled DAG 운영을 위한 선택적 compose profile로 제공된다. Docker runtime은 Airflow 2.10.5로 고정하며, 익숙한 `webserver` + `scheduler` 구조를 유지한다.

```bash
docker compose --profile bootstrap up --build backfill-once
docker compose --profile airflow build airflow-init airflow-webserver airflow-scheduler
docker compose --profile airflow up airflow-init
docker compose --profile airflow up -d airflow-webserver airflow-scheduler
```

`http://localhost:8080`을 열고 실행할 관측 DAG만 unpause한다. local FAB admin 계정은 `.env`의 `AIRFLOW_ADMIN_USER`, `AIRFLOW_ADMIN_PASSWORD`로 생성 또는 갱신된다. archived execution DAG는 명시적으로 테스트할 때만 unpause한다.

`strategy_engine_dag`는 optional archived strategy-report DAG로 실행할 수 있다. LLM report 생성은 `PRETREND_REPORT_API_URL`이 가리키는 FastAPI endpoint에 위임된다. Docker 내부 Codex 분석을 쓰려면 Linux `codex` binary를 `PRETREND_CODEX_BIN_DIR`로 mount하고, Codex auth/session state를 `PRETREND_CODEX_HOME_DIR`로 mount한다. Windows host-local Codex 분석을 쓰려면 host에서 FastAPI를 실행하고 Airflow의 `PRETREND_REPORT_API_URL`을 `http://host.docker.internal:8100/api/v1/report/strategy/analyze`로 설정한다. 이 경로는 container가 host port에 접근할 수 있는 Docker Desktop/Windows networking에 의존한다.

Restore 검증은 반드시 별도 DB 또는 별도 volume에서 수행하며, active `pretrend_obs` DB를 덮어쓰면 안 된다.

## 명시적 제외 범위

- 투자 추천 / 매수·매도 신호 / 수익률 예측 시스템
- LLM 기반 매매 판단 또는 자동 전략 추천
- 초반부터 Kubernetes / microservice / event bus 등 과설계
- 거대한 범용 플랫폼 / multi-agent orchestration
- 자동매매 시스템 자체를 실서비스로 운용하는 것
- 모델 예측 성능이나 수익률 경쟁을 프로젝트 핵심 가치로 내세우는 것

---

## 현재 구현 범위

현재 repo의 운영 표면은 재현 가능한 market data platform이다. 시장 구조 관측, 유사도 비교, 설명 API는 이 플랫폼의 첫 번째 read-only 활용 표면이다.

* **데이터 레이크**: Macro/EOD Bronze → Silver → Gold Parquet SOT.
* **Postgres 제공 미러**: Gold feature table, similarity output, explanation cache.
* **API**: meta, regime, similarity, macro, EOD view를 제공하는 FastAPI 읽기 전용 endpoint.
* **스케줄링**: 반복 가능한 DAG 실행을 위한 Airflow 2 Docker profile.
* **런타임 재현성**: Docker Compose, host volume 계약, backup/restore, 1회성 backfill, 새 머신 runbook.
* **설명 가능성**: LLM 분석은 explanation/report text 생성에만 한정하며 trade recommendation을 만들지 않는다.

### 현재 운영 중인 데이터 파이프라인

데이터 파이프라인은 현재 운영 범위에 포함된다. Docker/Airflow 재현성 작업도 이 파이프라인을 새 머신에서 다시 구동하고, 필요 시 backfill할 수 있게 만드는 것이 핵심이다.

* **Macro/EOD Bronze → Silver → Gold 파이프라인**
  * Macro/EOD 원천 데이터를 Bronze에 보존하고, Silver에서 정규화/feature화한 뒤, Gold Parquet SOT를 만든다.
  * 롤링 재처리와 파티션 overwrite 기반 멱등성을 유지한다.
* **Calendar Pipeline (Release Evidence)**
  * Bronze/Silver Calendar (`econ_events`, `fred_vintages`) 구현 완료.
  * Gold PIT-safe 조인을 위한 release evidence를 제공한다.
* **Gold Macro Feature v1**
  * Silver Macro + Silver Calendar 기반 Gold Macro Feature 생성.
  * `macro_job.py` 또는 `macro_pipeline_dag.py`로 Bronze → Silver → Gold 동기화.
* **Gold EOD Feature v1**
  * Silver EOD Feature 기반 Gold EOD Fact Mart 생성.
  * `gold_eod_features.py`, `eod_job.py`, `eod_pipeline_dag.py`에서 Bronze → Silver → Gold 체인으로 동작.
* **Gold → Postgres Sync**
  * `gold_postgres_sync_dag.py`가 Gold Parquet을 Postgres serving mirror로 sync한다.
  * API, similarity, explainability, dashboard는 이 serving mirror를 읽는다.
* **Airflow 2 Docker Profile**
  * `macro_pipeline_dag`, `eod_pipeline_dag`, `gold_postgres_sync_dag`는 현재 데이터 파이프라인 운영 DAG다.
  * 빈 data lake에서는 `backfill-once` 또는 DAG bootstrap marker guard가 Macro/EOD Bronze → Silver → Gold와 Gold sync를 먼저 수행한다.

<details>
<summary>보관된 strategy/backtest 구현 맥락</summary>

아래 내용은 초기 strategy experiment의 과거 맥락으로 보존한다. 현재 공개 운영 표면은 아니다.

* 🧭 **Risk-Control 전략 문서 구조(v0)**

  * 전략 흐름: `Layer -> Market Structure(4축) -> Composer -> Universe-ETF -> Allocation Engine -> Weekly Report`
  * 상태 기반 Allocation 중심으로 문서/계약 구조 정리
  * v0는 총 투자 비율(`invested_ratio`) 조절만 수행, Universe-ETF 내부 가중치 조절은 제외
* 🧠 **Strategy Engine v0 구현**

  * Gold Macro + Gold EOD snapshot을 입력으로 7단계 파이프라인 실행
  * 단계: Axis Features(4축) → Axis×Horizon(3-state 집약 + detail) → Market Position → Policy Selector → Universe-ETF → Allocation → Sell Advisor
  * 출력 경계: WHAT_TO_HOLD / HOW_MUCH_EXPOSURE / HOW_MUCH_TO_SELL
  * `decision_date` snapshot 저장 및 재현성(멱등 overwrite) 보장
  * Telegram 보고:
    - SIGNAL: `시장 컨텍스트` + `다음 스텝 가설(5/10/20/60/120D bias+hazard+expected)` + `시장 근거 4축` + `전술 그룹 다음 스텝`
    - PAPER_RESULT: `모의계좌 체결 요약 + PnL + 포지션 + 게이트/강도(effective_bias, hard_gate, tactical_strength)` + `전술 적용 근거(그룹 게이트)`
  * Telegram 표기 별칭:
    - `중기 성향` = `mid_regime`
    - `단기 공황 여부` = `is_panic = not risk_gate`
    - `전술 실행` = `run_universe (허용/제한)`
  * Long Engine v1: `delta_6m` rolling z-score 정규화 + `z_threshold=0.3` 운영
  * Mid Engine v1.1: breadth 계산을 `iwm/spy ratio`에서 `iwm-spy spread`로 교체(음수 SPY 구간 부호 반전 버그 수정)
  * Short Engine 보강: `smallcap_stress(iwm_spy_vol_spread > 0.005)` 추가, secondary PANIC 4신호 체계 적용
* 🧪 **Backtest Engine v2 + Walk-Forward**

  * Preset v2(`long_phase × mid_regime` 2D lookup) 지원
  * Walk-Forward 분석 CLI(`window-years`, `step-years`) 및 parquet/json 저장 지원
  * 결과 지표 JSON(`*_metrics.json`) 저장 지원
  * v3 확장: `next_step_signal snapshot` 기반 soft gate allocation 지원
  * v3.1: monthly bias lock 운영
  * v3.2: monthly lock + shock override(PANIC/RISK_OFF streak, cooldown) 운영
  * v3.3: v3.2 + hazard-aware override gate(`transition_hazard_10d`) 운영
  * v3.4: v3.3 + tactical group transition gate(`group_transition_signal`) 운영
  * v3.4.1: v3.4 + recovery-aware re-entry gate(`WEAK>=2` 진입, `RELIEF 2연속`/`MID=RISK_ON` 해제)
  * v3.4.2-phase: v3.4.1 + phase-aware bias state machine(`RECOVERY -> RISK_ON_BIAS`, 월요일 판정, cooldown=5)
  * v3.4.2a: v3.4.2-phase + 체류 규칙 완화(조건부 cooldown 압축 + hard-gate exit assist)
  * 실행 기준 bias는 `bias_20d` 단일 경로 사용(`1m/3m` alias 미사용)
  * 운영 기본 preset: `v3.4.1` (`v3.4.2-phase`, `v3.4.2a`는 실험군)
* 🧾 **Paper Engine (stateful EOD simulation)**
  * `src/pretrend/pipeline/paper/` 모듈에서 운용 시뮬레이션 실행
  * `next_step_signal` 기반 tactical 강도 조절(soft gate) + 하드게이트 우선 적용
  * 운영 입력(KRW: 초기자금/DCA)은 KIS 환율(`fx_usdkrw`) 우선, 결측 시 `PAPER_FX_USDKRW` fallback으로 USD 환산 후 체결 계산
* ♻️ **재현성 저장 체계 (Feature Snapshot + Result Registry)**
  * `next_step_history`(year/month partition, key=`trade_date+decision_date_ref`)로 전이예측 feature 선저장
  * backtest/walk-forward/paper 결과를 표준 아티팩트 + registry(parquet partition)로 저장
  * 동일 조건 비교를 “재실행 없이 조회” 가능하도록 운영
* 📝 **Text Pipeline + LLM Observer**
  * `text_pipeline_dag`: `Bronze -> Silver -> Gold(rule) -> Gold LLM` 4단계 운영
  * Gold LLM은 Ollama 로컬 기반 observer-only 계층이며 `text_annotation_v2` taxonomy 구조를 사용
  * 백필 경로:
    - FOMC Archive / SEC Index Bronze 백필
    - `gold_llm_backfill.py`로 FOMC/SEC Gold LLM 백필
  * SEC EDGAR adapter는 `filings.recent` + `filings.files`를 모두 순회해 과거 filing coverage를 확장
* 🧮 **거시 지표 기반 Macro Feature 생성**

  * FRED 연동
  * YoY / MoM / Rolling / Regime Feature
* 📈 **EOD 가격 기반 Feature 생성**

  * Return / Trend / Volatility / Momentum / Risk
* 📦 **운영 친화적 저장 구조**

  * Parquet + 연/월 파티션
* 🧪 **Pre-production 검증 중심 설계**

  * 로컬 실행 + DAG 기반 재현성 확보

> ❌ 자동매매, 모델 학습, 실시간 추론은 **현재 범위에 포함되지 않는다.**
> ❌ Text LLM feature는 현재 **Strategy/Paper/Backtest 실행 입력에 직접 연결되지 않는다**. 이 경계는 영구 observer-only 원칙으로 유지한다.
> ❌ 이 저장소의 공개 포지션은 투자 자동화가 아니라, 그 이전 단계의 데이터 기반과 운영 계약이다.

---

## 1. 폴더 구조

[그림] 상위 폴더 구조

```text
pretrend_ai/
├─ README.md                 # 프로젝트 진입점
├─ docker-compose.yml        # 기본 로컬 runtime 진입점
├─ pyproject.toml            # package/test 설정
├─ requirements.txt          # CPU-only 로컬 개발/검증 진입점
├─ .env.example              # 환경 변수 템플릿
├─ docker/                   # 역할별 Dockerfile과 Dockerfile별 ignore
│  ├─ Dockerfile.api
│  ├─ Dockerfile.dev
│  └─ Dockerfile.airflow
├─ requirements/             # 역할별 Python 의존성
│  ├─ api.txt
│  ├─ ci.txt
│  └─ airflow.txt
├─ docs/                     # 설계·환경·운영·데이터 문서
├─ dags/                     # Airflow DAG
├─ src/pretrend/
│  ├─ api/                   # FastAPI 읽기 전용 API
│  ├─ models/                # DB model/schema
│  ├─ observability/         # regime, similarity, explainability
│  ├─ ops/                   # bootstrap/backfill 운영 helper
│  ├─ pipeline/              # Ingest → Feature 파이프라인
│  │  ├─ config/             # Observability SOT 등 공통 설정
│  │  ├─ ingest/
│  │  ├─ features/
│  │  └─ calendar/           # Calendar release evidence 파이프라인
│  └─ utils/
├─ migrations/               # Alembic migration
├─ tests/                    # pytest contract/unit/integration tests
├─ data/                     # host-mounted Bronze/Silver/Gold data lake (gitignored)
├─ logs/                     # host-mounted runtime logs (gitignored)
├─ state/                    # local runtime state DB (gitignored)
└─ airflow_pretrend/         # Airflow metadata/log mount (gitignored)
```

---

## 2. 데이터 레이어 구조 (Layer)

### 2.1 Bronze Layer — Macro Econ Indicators

* 데이터 소스: **FRED API**
* 목적: 원천 데이터 보존 + 재현성 확보

**비즈니스 키:** `(indicator_id, date)`
**멱등성:** 동일 기간 재실행 시 동일 Parquet overwrite

---

### 2.2 Silver Layer — Macro Features

* 입력: Bronze Macro
* 출력: 판단·모델 입력으로 사용 가능한 Macro Feature

주요 Feature:

* YoY / MoM / Rolling 통계
* Inflation / Labor / Rate / Yield Curve Regime

> Silver Layer는 **모델이 아닌 Feature 재사용성 관점**에서 설계됨

---

### 2.3 Bronze Layer — EOD Daily Prices

* 데이터 소스: **Yahoo Finance (yfinance)**
* 대상: **Observability SOT 32개 ETF (Always-on)**
* 분류 라벨(`asset_group`, `asset_name`, `asset_subtype`)은 Bronze에서 1회 확정

**비즈니스 키:** `(symbol, trade_date)`
**멱등성:** 거래일 단위 overwrite

---

### 2.4 Silver Layer — EOD Price Features

* Return / Trend / Volatility / Risk
* Bronze에서 확정된 분류 라벨(`asset_group`, `asset_name`, `asset_subtype`)을 수정 없이 pass-through
* 데이터 품질 플래그 포함

  * 결측 보정 여부
  * 부분 거래일
  * 이상치 여부

> EOD Silver Feature는
> **Universe-ETF 계산 및 Gold Layer 결합의 입력 데이터**로 사용됨

---

### 2.5 Gold Layer — EOD Feature v1 Fact Mart

* 입력: Silver EOD Features
* Grain: `(symbol, trade_date)` (중복 제거 후 1행 보장)
* 라벨 전파: `asset_group`, `asset_name`, `asset_subtype` carry-forward
* Lineage: `run_id_gold`, `ingestion_ts_gold`
* 저장 경로:
  - `data/gold/eod/eod_features/symbol=XXX/year=YYYY/month=MM/gold_eod_features_YYYYMM.parquet`

---

## 3. Strategy Engine 설계 개념

Strategy Engine은 **데이터 수집 여부를 제어하지 않는다.**
Strategy Engine은 **정제된 Gold snapshot을 기반으로 실행 경계 출력**을 생성한다.

```text
Gold Macro / Gold EOD Snapshot
        ↓
Strategy Engine (Axis×Horizon 3-state → Policy → Universe-ETF → Allocation → Sell)
        ↓
WHAT_TO_HOLD / HOW_MUCH_EXPOSURE / HOW_MUCH_TO_SELL
```

* ETF / Macro 데이터: **항상 수집**
* Strategy Engine은 `decision_date` 단위 snapshot 결과를 저장

---

## 4. 실행 방법

### 4.0 Universe 용어 기준

| 용어 | 의미 | 상태 |
| --- | --- | --- |
| Universe-ETF (Execution Universe) | Strategy Engine에서 Observability ETF 후보를 선별하는 현재 실행 모듈 | 구현/운영 중 |
| Universe-Stock (Research Universe, U0~U3) | Macro→Theme→Stock 파이프라인 기반 종목 유니버스 | 로드맵(미착수) |

현재 시스템 성격:
- 현재 운용은 **ETF 실행 유니버스(= Universe-ETF)** 중심이다.
- 종목 선택 파이프라인 **Universe-Stock(U0~U3)**는 `docs/roadmap/milestones.md` 기준으로 확장한다.

### 4.1 빠른 시작 (개발/테스트)

```bash
# 의존성 설치 (editable)
python -m pip install -e .
# Parquet 엔진이 없으면 선택적으로 설치
pip install pyarrow  # 또는 fastparquet
```

테스트 실행:

```bash
pytest --gate fast -q --tb=short
pytest --gate contracts -q --tb=short
pytest --gate runtime -q --tb=short
pytest --gate dags -q --tb=short
pytest --gate pre-dashboard -q --tb=short

# DB schema/dummy-row smoke는 운영 DB가 아니라 격리 test DB에서 실행한다.
docker compose --profile test run --rm test-runner

# 특정 케이스만 볼 때는 경로를 직접 지정한다.
pytest -q tests/pipeline/test_eod_silver_writer_idempotency.py
pytest -q tests/pipeline/text/
pytest -q tests/pipeline/test_macro_silver_writer.py
```

## 테스트와 CI가 보호하는 약속

이 저장소의 테스트와 CI는 "pytest가 돌아간다"는 사실보다, **데이터 파이프라인의 운영 약속이 깨지지 않았는지**를 확인하는 장치에 가깝다.
테스트 추가 기준은 [운영 장애 시나리오 카탈로그](docs/testing/operational_failure_scenario_catalog.md)를 따른다. 새 테스트는 가능한 한 `OFS-*` 시나리오 ID와 synthetic test data를 기준으로 작성한다.

- 재실행 시 동일 파티션에 중복 append가 남지 않도록 **idempotent overwrite**를 보호한다.
- Calendar/Gold 계층에서 `selected_release_date < trade_date`가 무너지지 않도록 **point-in-time 규칙**을 보호한다.
- contract test로 레이어별 grain, key, required columns가 흔들리지 않도록 **schema / contract drift**를 막는다.
- `_tmp_run` 이후 atomic rename 패턴이 깨져 partial snapshot이 남지 않도록 **snapshot write safety**를 점검한다.
- Strategy/Paper/Backtest 입력이 Gold snapshot 계약을 벗어나지 않도록 **downstream input boundary**를 보호한다.
- DB contract smoke는 격리된 `pretrend_test*` DB에 migration을 적용한 뒤 synthetic row를 넣고 읽어 **실제 schema/constraint 동작**을 확인한다.
- 운영 복구 테스트는 active DB를 덮지 않고 shadow restore DB와 test DB를 사용해 **복구 가능성**을 확인한다.
- `.github/workflows/ci.yaml`은 `main`, `dev`에 대한 push / pull request 시 `pytest --gate fast -q --tb=short`를 실행해 빠른 운영 수문장을 기본선에서 감시한다. DB/restore/DAG 운영 변경은 로컬 또는 Docker에서 `runtime`, `dags`, `pre-dashboard` gate를 추가로 실행한다.

### 4.2 환경 준비

```bash
conda activate pretrend-dev
export FRED_API_KEY=YOUR_FRED_API_KEY
```

### 4.3 Strategy Engine 실행

```bash
# Strategy Engine 단일 실행
PYTHONPATH=src python -m pretrend.pipeline.strategy_engine.strategy_job --date 2024-06-03 --invested-ratio 0.10

# z-threshold 지정 실행
PYTHONPATH=src python -m pretrend.pipeline.strategy_engine.strategy_job --date 2024-06-03 --invested-ratio 0.10 --long-z-threshold 0.3

# 전체 테스트
conda run -n pytest-pretrend pytest tests/ -v
```

### 4.4 Backtest / Walk-Forward 실행

규칙 기반 전이예측(MVP):
- `5/10/20/60/120 거래일` 지평으로 `sojourn_prob`(지속확률) / `transition_hazard`(전환위험도) 산출
- ML 없이 snapshot 확장 필드(nullable)로 제공

```bash
# Backtest preset v2
PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v2

# Walk-Forward (4년 창, 2년 슬라이드)
PYTHONPATH=src python -m pretrend.pipeline.backtest.walk_forward --preset v2 --window-years 4 --step-years 2

# Backtest preset v3 (next_step soft gate)
PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3

# Backtest preset v3.1 (v3 + monthly bias lock)
PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.1

# Backtest preset v3.2 (v3.1 + shock override/cooldown)
PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.2

# Backtest preset v3.3 (v3.2 + hazard-aware override)
PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.3

# Backtest preset v3.4 (v3.3 + tactical group transition gate)
PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.4

# Backtest preset v3.4.1 (v3.4 + recovery-aware re-entry gate)
PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.4.1

# Walk-Forward 저장 (parquet + summary json)
PYTHONPATH=src python -m pretrend.pipeline.backtest.walk_forward --preset v2 --window-years 4 --step-years 2 --save

# Walk-Forward v3.3 (duration/transition diagnostics)
PYTHONPATH=src python -m pretrend.pipeline.backtest.walk_forward --preset v3.3 --window-years 4 --step-years 2
```

결과 저장/비교 원칙:
- `BacktestRunner().run()`만 호출하면 파일이 저장되지 않는다.
- 비교/재현성 용도는 `save_result()`를 포함한 실행으로 아티팩트를 저장해야 한다.
- 권장 경로: `result/backtest_compare/<window>_<YYYYMMDD-YYYYMMDD>/<preset>/`
- 표준 산출물:
  - `*_daily_nav.parquet`, `*_trades.parquet`, `*_summary_metrics.parquet/json`
  - `*_diagnostics.parquet`, `*_final_positions.parquet`, `*_config.json`
  - legacy: `*.parquet`, `*_metrics.json`
- registry:
  - `result/backtest/registry/pipeline=backtest/run_date=YYYY-MM-DD/registry.parquet`
  - `artifact_path`, `run_id`, 기간/버전 메타로 재실행 없이 비교 조회 가능

v2 preset 성과 비교(2006-01 ~ 2024-06, DCA $300/월):

| 엔진 | XIRR | MDD | Sharpe |
| --- | --- | --- | --- |
| v0 | +8.00% | -15.71% | 1.69 |
| v1 | +6.94% | -17.74% | 1.65 |
| v1.1 | +7.25% | -15.65% | 1.68 |

---

### 4.3 Bronze → Silver 실행 예시

```bash
PYTHONPATH=src python -m pretrend.pipeline.ingest.macro \
  --start 2010-01-01 \
  --end 2025-12-01
```

```bash
PYTHONPATH=src python -m pretrend.pipeline.features.macro_features \
  --start 2010-01-01 \
  --end 2025-12-01
```

```bash
PYTHONPATH=src python -m pretrend.pipeline.calendar.runner --target all
```

```bash
PYTHONPATH=src python -m pretrend.pipeline.macro_job \
  --start 2024-01-01 \
  --end 2024-06-30
```

```bash
PYTHONPATH=src python -m pretrend.pipeline.features.gold_eod_features \
  --start 2024-01-01 \
  --end 2024-06-30
```

```bash
PYTHONPATH=src python -m pretrend.pipeline.eod_job \
  --start 2024-01-01 \
  --end 2024-06-30
```

---

### 4.4 Airflow 기반 실행 (권장)

* DAG:

  * `macro_pipeline_dag.py`
  * `eod_pipeline_dag.py`
  * `strategy_engine_dag.py` (Telegram `SIGNAL`)
  * `paper_trading_dag.py` (Telegram `PAPER_RESULT`, EOD 1회)
  * `paper_trading_dag.py`는 옵션으로 KIS mock broker 실행 경로를 지원
    (`PAPER_BROKER_ENABLED=1`, 기본 `0`)

* 특징:

  * 매 실행 시 **직전월 1일 ~ 전일 롤링 재처리**
  * 파티션 overwrite 기반 멱등성
  * Airflow는 대규모 운영 목적이 아니라, **배치 재현성과 파이프라인 경계 명확화**를 위해 사용
  * Telegram은 동일 채널에서 `SIGNAL`/`PAPER_RESULT`를 `message_type`으로 구분
  * 운영 메시지의 next-step 값은 `next_step_signal snapshot` 단일소스를 사용
    (결측 시 `UNKNOWN/N/A` fail-open 표기)
  * 전이 지평은 거래일 기준 `5/10/20/60/120D`로 고정
  * SIGNAL/PAPER는 상태머신 메타(`bias_state_source/switch/reason/cooldown`)를 함께 표기해 전환 근거를 설명
  * Telegram 전송 실패는 fail-open (경고 로그 후 DAG 성공 유지)
  * Broker 실행 실패도 fail-open (paper 시뮬레이션/알림은 유지)

</details>

---

## 5. Codex 사용 정책

- 모든 작업 전 `AGENTS.md` 규칙을 준수하고, 작은/검토 가능한 diff를 유지한다 (선호: ≤300 LOC).
- `dev`에서 분기한 `codex/<task>` 브랜치로 작업한다.
- 한 번에 하나의 작업만 포함하고, 실행 가능한 검증 명령(예: `pytest --gate fast -q --tb=short`, 단일 테스트 파일은 `pytest -q tests/pipeline/<file>.py`)을 제시한다.
- 안정성을 위해 가능하면 범위가 좁은 변경(예: tests-only, docs-only)으로 작업한다.

---

## 5. 문서

* 프로젝트 요약: `/docs/project_summary.md`
* 시스템 요약: `/docs/system_overview.md`
* 환경 구성: `/docs/environment.md`
* 운영 재현성: `/docs/operation/reproducible_runtime_contract.md`
* AI 도구 사용 기준: `/docs/operation/agent_adoption_notes.md`
* 로드맵: `/docs/roadmap/milestones.md`
* 데이터 설계:
  * `/docs/data/data_model.md`
  * `/docs/data/data_requirements.md`
  * `/docs/data/data_ingest_datasources.md`
  * `/docs/data/market_structure_data_inventory.md`
  * `/docs/architecture/universe_design.md`
* 아키텍처: `/docs/architecture.md`
* 관측 런타임 아키텍처:
  * `/docs/architecture/system_map_2026q2.md`
  * `/docs/architecture/runtime_flow.md`
  * `/docs/architecture/pipeline_window_policy.md`
  * `/docs/architecture/boundary_contract.md`
  * `/docs/api/observability_api_contract.md`
* 전략 설계/계약(보관/reference):
  * `/docs/architecture/strategy_architecture.md`
  * `/docs/architecture/market_structure_long_contract.md`
  * `/docs/architecture/market_structure_mid_contract.md`
  * `/docs/architecture/market_structure_short_contract.md`
  * `/docs/architecture/market_structure_composer_contract.md`
  * `/docs/architecture/universe_contract.md`
  * `/docs/architecture/allocation_engine_contract.md`
  * `/docs/architecture/paper_execution_ledger_contract.md`
  * `/docs/architecture/paper_trading_alert_contract.md`
* 변경 이력: `/docs/changelog.md`

---

## 6. 로드맵

### 현재 로드맵

상세 진행표: [`docs/roadmap/milestones.md`](docs/roadmap/milestones.md)

* [x] **기반 구축**: PostgreSQL + TimescaleDB, config, models, Alembic, Docker Compose
* [x] **Regime modules**: `src/pretrend/observability/` 하위 market structure feature module 정리
* [x] **Serving layer**: Gold Postgres schema, sync DAG, similarity, explainability, FastAPI
* [x] **Runtime 재현성**: Docker runtime, Airflow 2 profile, backup/restore, one-shot backfill
* [x] **Phase 3 Dashboard**: `apps/web/` 8 screen, Recharts chart, explanation view, Docker web runtime
* [ ] **Phase 4+ visual 확장**: ETF heatmap, similarity replay, window-aware explainability
* [ ] **Managed runtime 검토**: 외부 hosting은 가용성/사용자 요구가 생길 때만 검토

### Infrastructure (완료)
* [x] FRED Macro Bronze Ingest
* [x] Macro Silver Feature
* [x] EOD Bronze Ingest (Observability SOT 32 ETFs)
* [x] EOD Silver Feature
* [x] Calendar Pipeline v1 (econ_events + fred_vintages)
* [x] Gold Macro Feature v1
* [x] Gold EOD Feature v1
* [x] Airflow DAG 기반 통합 파이프라인

### 보관된 전략 실험
* [x] Strategy Engine v0/v1/v2/v3.x
* [x] Backtest Engine + Walk-Forward
* [x] Paper Engine + KIS mock broker

### 명시적 제외 범위
* Kubernetes / microservice / event bus
* 자동매매 실서비스 운용
* AI 매수/매도 추천

---

> 📌 본 프로젝트는 **개인 연구 및 운영형 런타임 설계·운영 학습용**입니다.
> **시장 구조를 관측·설명하는 런타임을 운영하기 위한 프로젝트**이며,
> **실거래, 실자금 운용, 외부 서비스 제공을 수행하지 않습니다.**

---

## 면접용 1분 요약

- 본 프로젝트는 자동매매나 모델 성능을 전면에 두지 않는다.
- 핵심은 시장 구조를 운영 가능한 수준으로 관측·설명하는 **관측 런타임**을 운영하는 것이다.
- 우선순위: 수집 안정성 → 재현성 → 관측 가능성 → 런타임 안정성 → 설명 가능성 → dashboard → AI 요약. AI는 항상 후순위다.
