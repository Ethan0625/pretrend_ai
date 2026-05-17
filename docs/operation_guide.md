# 운영 가이드

Markers: operation, security
Status: active

> ℹ️ **현재 운영 기준**
>
> Pretrend는 금융·거시 데이터를 재현 가능한 방식으로 수집·정제하고,
> point-in-time 안전한 feature layer를 구축하기 위한 **market data platform**이다.
> 현재 기준으로 이 문서는 두 층위로 읽는다:
> - **현재 유효 운영 기준**: Docker runtime, Airflow 2, Bronze/Silver/Gold, Calendar, Postgres serving mirror, FastAPI read-only API
> - **보관 참고 섹션**: Strategy/Backtest/Paper/Broker 실행 규칙. 코드는 보존되지만 현재 공개 운영 표면이 아니다.
>
> 우선 참조:
> - `docs/architecture/track_separation.md`
> - `.agent/WORKFLOW.md`
> - `.agent/CHANGE_GATES.md`

## 현재 운영 기준
- 메인 영역: Reproducible Market Data Platform
- 운영 유지 범위: Infrastructure 파이프라인(`macro`, `eod`, `calendar`), Postgres serving mirror, FastAPI read-only API, Text observability
- 보관 범위: `strategy_engine`, `backtest`, `paper`, `broker`, Telegram bot orchestration
- 해석 원칙:
  - Calendar / Gold / Text 섹션은 현재 운영 기준으로 읽는다.
  - Strategy / Backtest / Paper / Walk-Forward / Telegram 보고 상세는 보관 reference로 읽는다.
  - 보관된 execution 서비스 인스턴스는 stop/disable/paused 상태를 유지한다.

## 재현 가능한 런타임 사전 점검 (P30)

Phase 3 dashboard 진입 전 Docker runtime, Postgres volume path, DB backup/restore, dev/test image, 신규 clone 검증, agent docs 공개 범위를 P30에서 고정한다.

장기 계약 문서:

- `docs/operation/reproducible_runtime_contract.md`

핵심 원칙:

- `PRETREND_POSTGRES_DATA_DIR`에 지정한 host path가 active Postgres volume 위치다.
- 지정하지 않으면 기존 `./.local/postgres-data`를 기본값으로 사용한다.
- 운영 복구 1순위는 `pg_dump -Fc` dump restore다.
- restore 검증은 active DB가 아닌 별도 DB/volume에서 수행한다.
- `docker compose down -v`는 운영 data volume 삭제 위험이 있으므로 사용하지 않는다.
- README 공식 절차는 OS별 `docker compose` 원 명령을 기준으로 작성한다.

기본 실행은 기존 repo-local path를 유지한다.

```bash
docker compose up -d postgres api
```

Linux/macOS 외장하드 또는 별도 mount path:

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

### DB backup / restore-first 복구

운영 복구는 serving DB dump restore를 1순위로 둔다. backfill은 dump가 없거나 오래된 경우에 파일 data lake를 재구성하는 fallback이다.

백업:

```bash
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /backups/pretrend_obs_YYYYMMDD.dump'
```

백업 파일 및 catalog 확인:

```bash
docker compose exec -T postgres sh -c 'test -s /backups/pretrend_obs_YYYYMMDD.dump'
docker compose exec -T postgres sh -c 'pg_restore -l /backups/pretrend_obs_YYYYMMDD.dump' >/tmp/pretrend_obs_YYYYMMDD.list
grep -E 'TABLE DATA public (alembic_version|gold_macro_features|gold_eod_features|similarity_regime|similarity_gold|gold_market_state_similarity_feature|explainability_cache)' /tmp/pretrend_obs_YYYYMMDD.list
```

restore 검증은 별도 DB 또는 별도 volume에서만 수행한다. active `pretrend_obs` DB를 검증 목적으로 덮어쓰지 않는다.

별도 DB 검증 절차:

```bash
docker compose exec -T postgres sh -c 'createdb -U "$POSTGRES_USER" pretrend_restore_check'
docker compose exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d pretrend_restore_check --no-owner --no-privileges /backups/pretrend_obs_YYYYMMDD.dump'
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d pretrend_restore_check -Atc "SELECT COUNT(*) FROM alembic_version;"'
docker compose exec -T postgres sh -c 'dropdb -U "$POSTGRES_USER" pretrend_restore_check'
```

Backfill fallback 순서:

1. `PRETREND_DATA_DIR` volume이 mount되어 있는지 확인한다.
2. 기존 pipeline 호환을 위해 `PRETREND_DATA_ROOT`가 같은 data path를 가리키게 한다.
3. Macro/EOD data lake를 필요한 기간만 재생성한다.
4. `gold_postgres_sync_dag`로 Gold Parquet을 serving DB에 UPSERT한다.
5. `similarity_build_dag`는 명시한 `query_start`/`query_end` 범위로 재생성한다.
6. `explainability_build_dag`는 latest/on-demand 범위만 사용한다. historical full LLM backfill은 Phase 3 dashboard의 scope/window/cache key 계약이 정해지기 전까지 수행하지 않는다.

## Observability Runtime 운영 명령 (Phase 0~3)

### Phase 0 — DB / Config / Models / Alembic (P17 진행 중)

#### Postgres + TimescaleDB 컨테이너 (P17-1 산출물)

```bash
# 컨테이너 기동
docker compose up -d postgres

# 상태 확인
docker compose ps postgres

# 접속
docker compose exec postgres psql -U pretrend -d pretrend_obs

# TimescaleDB 확장 확인
docker compose exec postgres psql -U pretrend -d pretrend_obs -c "\dx"

# 멱등성 검증은 별도 test DB/volume에서 수행한다.
# 운영 data volume이 연결된 compose project에서 `docker compose down -v`를 실행하지 않는다.
```

환경 변수는 `.env`에 정의 (`.env.example` 참조):
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT`
- `DATABASE_URL` (sync, psycopg2)
- `DATABASE_URL_ASYNC` (async, asyncpg)

#### Alembic 마이그레이션 (P17-4 산출물)

```bash
# baseline 적용
conda run -n pytest-pretrend alembic upgrade head

# 현재 revision 확인
docker compose exec postgres psql -U pretrend -d pretrend_obs -c "SELECT * FROM alembic_version;"

# rollback (테스트용)
conda run -n pytest-pretrend alembic downgrade base
conda run -n pytest-pretrend alembic upgrade head

# 새 revision 생성 (Phase 2+ 도메인 모델 추가 시)
conda run -n pytest-pretrend alembic revision --autogenerate -m "add macro_observations hypertable"
```

#### Config / Models 사용 (P17-2, P17-3 산출물)

```bash
# Settings 로드 검증
conda run -n pytest-pretrend python -c "from pretrend.config import get_settings; s = get_settings(); print(s.app_env, s.database_url)"

# Models base import 검증
conda run -n pytest-pretrend python -c "from pretrend.models import Base, BaseSchema; print(Base.metadata.tables)"
```

### Phase 2 — FastAPI 서비스 (P28)

FastAPI 서비스는 `src/pretrend/api/`에 있으며, Postgres mirror와 explainability cache를 read-only로 조회한다.
로컬 운영 기준은 docker-compose `api` 서비스다.

필수 환경 변수는 `.env`에 둔다.

| 변수 | 필수 여부 | 설명 |
| --- | --- | --- |
| `PRETREND_API_KEY` | 필수 | `/api/v1/*` 요청의 `X-API-Key` 헤더와 비교한다. `/health`는 예외다. |
| `PRETREND_API_CORS_ORIGINS` | 선택 | Phase 3 React dashboard 대비용 CORS origin 목록. 기본값은 빈 목록이다. |
| `PRETREND_API_TRUSTED_HOSTS` | 선택 | TrustedHostMiddleware 허용 host 목록. 기본값은 `*`다. |

기동:

```bash
docker compose up -d postgres api
docker compose ps api
docker compose logs api --tail 30
```

종료:

```bash
docker compose stop api
```

기본 확인:

```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8000/docs -o /tmp/pretrend-api-docs.html
```

인증이 필요한 endpoint는 `X-API-Key` 헤더를 사용한다.

```bash
export PRETREND_API_KEY="$(grep '^PRETREND_API_KEY=' .env | cut -d= -f2-)"
curl -s -H "X-API-Key: $PRETREND_API_KEY" \
  "http://localhost:8000/api/v1/meta"
```

11 endpoint / 12 smoke call 기준:

```bash
curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8000/health"
curl -s -o /dev/null -w "%{http_code}\n" -H "X-API-Key: $PRETREND_API_KEY" "http://localhost:8000/api/v1/meta"
curl -s -o /dev/null -w "%{http_code}\n" -H "X-API-Key: $PRETREND_API_KEY" "http://localhost:8000/api/v1/regime?trade_date=2024-06-03"
curl -s -o /dev/null -w "%{http_code}\n" -H "X-API-Key: $PRETREND_API_KEY" "http://localhost:8000/api/v1/similarity?query_date=2024-06-03&view=regime&top_n=5"
curl -s -o /dev/null -w "%{http_code}\n" -H "X-API-Key: $PRETREND_API_KEY" "http://localhost:8000/api/v1/similarity?query_date=2024-06-03&view=gold&top_n=5"
curl -s -o /dev/null -w "%{http_code}\n" -H "X-API-Key: $PRETREND_API_KEY" "http://localhost:8000/api/v1/macro?trade_date=2024-06-03&indicator_id=CPIAUCSL"
curl -s -o /dev/null -w "%{http_code}\n" -H "X-API-Key: $PRETREND_API_KEY" "http://localhost:8000/api/v1/macro/timeline?indicator_id=CPIAUCSL&start=2024-01-01&end=2024-06-03"
curl -s -o /dev/null -w "%{http_code}\n" -H "X-API-Key: $PRETREND_API_KEY" "http://localhost:8000/api/v1/eod?symbol=SPY&trade_date=2024-06-03"
curl -s -o /dev/null -w "%{http_code}\n" -H "X-API-Key: $PRETREND_API_KEY" "http://localhost:8000/api/v1/eod/timeline?symbol=SPY&start=2024-01-01&end=2024-06-03"
curl -s -o /dev/null -w "%{http_code}\n" -H "X-API-Key: $PRETREND_API_KEY" "http://localhost:8000/api/v1/regime/explain?trade_date=2024-06-03"
curl -s -o /dev/null -w "%{http_code}\n" -H "X-API-Key: $PRETREND_API_KEY" "http://localhost:8000/api/v1/similarity/explain?query_date=2024-06-03&view=regime"
curl -s -o /dev/null -w "%{http_code}\n" -H "X-API-Key: $PRETREND_API_KEY" "http://localhost:8000/api/v1/macro/explain?trade_date=2024-06-03"
```

smoke call은 200 또는 정상적인 404를 허용한다. 401은 `PRETREND_API_KEY` / `X-API-Key` 불일치, 500은 API 로그와 DB 연결 설정을 우선 확인한다.

트러블슈팅:

- `PRETREND_API_KEY is required`: `.env`에 `PRETREND_API_KEY`가 없다.
- `API key invalid`: 요청 헤더의 `X-API-Key`가 `.env` 값과 다르다.
- DB 연결 실패: 컨테이너 내부에서는 `POSTGRES_HOST=postgres`, `POSTGRES_PORT=5432`로 override되어야 한다.
- `api` healthcheck 실패: `docker compose logs api --tail 50`로 startup error를 먼저 확인한다.
- `cannot stop container ... permission denied`: snap Docker와 system Docker가 동시에 남아 있거나 Docker socket이 꼬인 상태일 수 있다. `ps -ef | grep -E "dockerd|containerd" | grep -v grep`, `snap list docker`, `which docker`로 중복 설치를 확인하고, 하나의 Docker daemon만 남긴 뒤 `sudo systemctl restart docker.socket docker`를 실행한다.
- `could not access file "$libdir/timescaledb-2.27.0-dev"` 또는 `TimescaleDB version mismatch`: `latest-pg16` 이미지와 기존 DB catalog의 TimescaleDB version 문자열이 어긋난 상태다. `docker-compose.yml`은 `timescale/timescaledb:2.27.0-pg16`처럼 고정 tag를 사용한다. 이미 catalog가 `2.27.0-dev`로 남았으면 preload를 끈 repair 컨테이너에서 `pg_extension.extversion`을 `2.27.0`으로 정정한 뒤 compose postgres를 force recreate한다.
- `api -> postgres:5432` TCP timeout: host port 문제가 아니라 Docker bridge forwarding 문제일 수 있다. `docker compose down --remove-orphans`로 compose network를 재생성한 뒤 `docker compose up -d postgres api`를 실행한다. `docker compose down -v`는 데이터 볼륨 삭제 위험이 있으므로 사용하지 않는다.

운영 점검 명령:

```bash
docker compose exec -T api python -c "import socket; print(socket.gethostbyname('postgres')); s=socket.create_connection(('postgres', 5432), timeout=3); print('tcp-ok'); s.close()"
docker compose exec -T postgres psql -U pretrend -d pretrend_obs -c "SELECT extname, extversion FROM pg_extension;"
docker compose exec -T api sh -c "timeout 10 alembic current; echo exit=\$?"
```

외부 노출은 P28 범위가 아니다. Phase 3 dashboard가 로컬에서 검증된 뒤 별도 운영 task로 분리한다.

### Phase 3 — React Dashboard (계획)

(P20 시리즈 진입 시 본 섹션 갱신)

- `cd apps/web && npm run dev`
- 빌드 산출물: `apps/web/dist/`

## Agent 보조 개발 (Codex)
- **Workflow:** `dev` → `codex/<task>` 분기 → 작업/커밋 → PR/머지 → `dev` 반영.
- **Verification checklist:** `pytest --gate fast -q --tb=short` (필요 시 대상 파일 예: `pytest -q tests/pipeline/<file>.py`), `git diff --cached`.
- **Guardrails:** `.agent/WORKFLOW.md`, `.agent/CHANGE_GATES.md` 준수, 비공개 정보/시크릿 금지, 요청 없는 공개 API 변경 금지, 파티션 overwrite·멱등성 보존.
- **Rollback:** 브랜치 폐기 또는 `git restore`로 변경 취소.

## Calendar Pipeline 실행
- `macro_job.py` 실행 시 Calendar Bronze + Silver(`econ_events`, `fred_vintages`)가 함께 빌드된다.
- Calendar만 독립 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.calendar.runner --target all`
- Calendar 테스트 실행:
  - `conda run -n pytest-pretrend pytest tests/pipeline/test_calendar.py -v`

## Gold Macro Feature v1 실행
- `macro_job.py` 실행 시 Bronze → Silver → Gold(Macro v1)까지 1회 실행으로 동기화된다.
- 실행 명령:
  - `PYTHONPATH=src python -m pretrend.pipeline.macro_job --start 2024-01-01 --end 2024-06-30`
- Gold/Calendar 통합 테스트 실행:
  - `conda run -n pytest-pretrend pytest tests/pipeline/test_gold_macro_feature_v1.py -v`
  - `conda run -n pytest-pretrend pytest tests/pipeline/test_calendar.py -v`

## Gold EOD Feature v1 실행
- Gold EOD 단독 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.features.gold_eod_features --start 2024-01-01 --end 2024-06-30`
- EOD Bronze → Silver → Gold E2E 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.eod_job --start 2024-01-01 --end 2024-06-30`
- Airflow `eod_pipeline_dag`는 Bronze → Silver → Gold 순서로 실행된다.
- EOD Gold 테스트 실행:
  - `conda run -n pytest-pretrend pytest tests/pipeline/test_gold_eod_features.py -v`

## Text Pipeline 실행
- 단일 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.text.text_job --stage all --source sec,fed --date 2026-02-18`
- DAG 구조:
  - `text_pipeline_dag = Bronze(sec+fed) -> Silver -> Gold(rule) -> Gold LLM`
- Gold LLM 백필:
  - `PYTHONPATH=src python -m pretrend.pipeline.text.gold_llm_backfill --source fed_fomc --start 2006-01-01 --end 2026-12-31 --max-workers 4`
  - `PYTHONPATH=src python -m pretrend.pipeline.text.gold_llm_backfill --source sec_edgar --start 2006-01-01 --end 2026-12-31 --max-workers 4`
- Bronze/Silver 백필:
  - `PYTHONPATH=src python -m pretrend.pipeline.text.backfill --source sec_index,fomc_archive --start 2006-01-01 --end 2024-06-03 --chunk-years 1`
- Text 테스트:
  - `conda run -n pytest-pretrend pytest tests/pipeline/text/ -v`

### Text 운영 경계
- rule-based Gold 3종(`macro_hawkish_score`, `filing_risk_burst`, `policy_uncertainty_idx`)은 저장/관측 활성 상태다.
- Gold LLM 4종(`llm_tone`, `llm_topics`, `llm_tags`, `llm_summary`)은 observer-only다.
- Text feature는 Strategy/Paper/Backtest 실행 입력으로 직접 연결하지 않는다(영구 observer-only).
- Telegram 반영은 Phase 1.5에서 `시장 근거` 보조 문구와 `interpretation_summary` 생성까지만 허용한다.
- 용어:
  - `llm_summary`: text-only 문서 요약 필드
  - `interpretation_summary`: signal snapshot + text snapshot 결합 해석문

### SEC 수동 검증 주의
- `SECEdgarAdapter`는 `filings.recent + filings.files`를 모두 순회한다.
- 다만 live SEC 수동 검증은 네트워크/DNS가 가능한 환경에서만 의미가 있다.
- 현재 로컬 분석 환경에서 DNS가 차단되면 `company_tickers.json` 조회가 실패할 수 있다.

## Strategy Engine 실행 (보관 reference)
- 본 섹션은 현재 운영 명령이 아니라 참고용 legacy 기록이다.
- `strategy_engine_dag`는 2026-05-12부터 paused 상태를 유지한다.
- Strategy Engine v0 단일 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.strategy_engine.strategy_job --date 2024-06-03 --invested-ratio 0.10`
- Strategy Engine z-threshold 지정 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.strategy_engine.strategy_job --date 2024-06-03 --invested-ratio 0.10 --long-z-threshold 0.3`
- 입력 전제:
  - Gold Macro snapshot
  - Gold EOD snapshot
- 출력 경계:
  - `WHAT_TO_HOLD`
  - `HOW_MUCH_EXPOSURE`
  - `HOW_MUCH_TO_SELL`
- 스냅샷 저장 기준:
  - `decision_date` 파티션
  - overwrite + atomic write
  - `next_step_history` 증분 저장(`trade_date, decision_date_ref` key)

## 재현성 저장 원칙 (Compute once, store, compare many)
- 계산 가능한 전이예측 feature(`state_age/sojourn/hazard`)는 snapshot/history로 선저장한다.
- 소비자는 저장본을 우선 사용하고 결측 시에만 fail-open fallback을 사용한다.
- 결과 비교는 registry + summary artifact로 재실행 없이 조회 가능해야 한다.
- 실행 기준 bias는 `bias_20d` 단일 경로를 사용한다 (`1m/3m` alias 비사용).

### next_step 지평 마이그레이션 (5/10/20/60/120D)
- dry-run:
  - `python scripts/migrate_next_step_horizons.py --dry-run`
- apply:
  - `python scripts/migrate_next_step_horizons.py --apply`

## 통합 테스트 실행
- 전체 테스트:
  - `conda run -n pytest-pretrend pytest tests/ -v`
- 테스트 상태 기록 원칙:
  - 고정 숫자 대신 최신 pytest/CI 로그를 기준으로 확인

## 권장 E2E 실행 시퀀스
- Macro 파이프라인(Bronze→Silver→Calendar→Gold):
  - `PYTHONPATH=src python -m pretrend.pipeline.macro_job --start 2006-01-01 --end 2026-02-12`
- EOD 파이프라인(Bronze→Silver→Gold):
  - `PYTHONPATH=src python -m pretrend.pipeline.eod_job --start 2006-01-01 --end 2026-02-12`
- Strategy Engine 실행 (legacy reference):
  - `PYTHONPATH=src python -m pretrend.pipeline.strategy_engine.strategy_job --date 2024-06-03 --invested-ratio 0.10`

## Backtest Engine 실행 (보관 reference)
- 본 섹션은 현재 운영 명령이 아니라 참고용 legacy 기록이다.
- 실행 규칙(현재):
  - 월 첫 거래일: `monthly_addition` 자금 추가(DCA)
  - 월요일: 전 거래일(T-1) 기준 신호 평가
  - 화요일: `INCREASE` 실행(현금 배포 매수)
  - 금요일: `DECREASE` 단계 매도(`50% → 30% → 20%`, 3주)
  - `risk_gate=false(PANIC)`: `INCREASE` 허용, `DECREASE` 신규 생성 차단/진행 트랜치 동결
- v0(range-maintenance) 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v0`
- v1(target-seeking) 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v1`
- v2(2D target-seeking: long_phase × mid_regime) 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v2`
- v3(2D + next_step soft gate) 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3`
- v3.1(v3 + monthly bias lock) 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.1`
- v3.2(v3.1 + shock override/cooldown) 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.2`
- v3.3(v3.2 + hazard-aware override gate) 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.3`
- v3.4(v3.3 + tactical group transition gate) 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.4`
- v3.4.1(v3.4 + recovery-aware re-entry gate) 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.4.1`
  - 규칙: `WEAK>=2`일 때만 축소, `RELIEF 2연속` 또는 `MID=RISK_ON`에서 축소 해제
- v3.4.2-phase(v3.4.1 + phase-aware bias state machine) 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.4.2-phase`
  - 규칙: `RECOVERY -> RISK_ON_BIAS` baseline, 월요일 판정, hysteresis/cooldown(5거래일)
- v3.4.2a(v3.4.2-phase + 체류 규칙 완화 실험) 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.4.2a`
  - 규칙: cooldown 기본 5일 유지 + `mid=RISK_ON` 또는 `RELIEF 2연속`에서 cooldown 2일 압축
  - 보조 규칙: `run_universe` 복귀 + `RELIEF 2연속`이면 월요일에 `RISK_OFF -> NEUTRAL` 1단 완화(soft-only)
- 운영 기준:
  - `v3.4.2a`는 실험군으로만 유지한다.
  - 운영 기본 preset은 `v3.4.1`을 사용한다.
- 결과 저장 원칙:
  - `save_result()`를 호출한 실행만 아티팩트/registry에 저장된다.
  - 단순 `BacktestRunner().run()` 호출은 콘솔 결과만 생성하고 파일은 남기지 않는다.
- 권장 저장 경로(기간 포함):
  - `result/backtest_compare/<window>_<YYYYMMDD-YYYYMMDD>/<preset>/`
  - 예: `result/backtest_compare/long_20060103-20240603/v3.3/`
- 표준 저장 아티팩트(`save_result`):
  - `{stem}.parquet` (legacy daily log)
  - `{stem}_daily_nav.parquet`
  - `{stem}_trades.parquet`
  - `{stem}_config.json`
  - `{stem}_metrics.json` (legacy)
  - `{stem}_summary_metrics.parquet`
  - `{stem}_summary_metrics.json`
  - `{stem}_diagnostics.parquet`
  - `{stem}_final_positions.parquet`
- registry 저장:
  - `result/backtest/registry/pipeline=backtest/run_date=YYYY-MM-DD/registry.parquet`
  - `artifact_path`/`run_id`/기간/버전 메타로 재실행 없이 비교 조회 가능
- 결과 저장 후 비교(실행 직후 + 저장본 재조회):
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v2`
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.1`
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.2`
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.3`
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.4`
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.4.1`
- v2 + DCA 월 적립금 지정 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v2 --monthly-addition 300`
- v1 + tactical override 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v1 --tactical SECTOR COMMODITY`

아티팩트 누락 점검/재생성:
```bash
# 1) 저장 파일 확인
find result/backtest_compare -maxdepth 3 -type d | sort

# 2) 특정 preset 파일 확인
find result/backtest_compare/long_20060103-20240603/v3.3 -maxdepth 1 -type f | sort

# 3) registry 확인
python - << 'PY'
import pandas as pd
p='result/backtest/registry/pipeline=backtest/run_date=2026-02-25/registry.parquet'
df=pd.read_parquet(p)
print(df[['pipeline','preset','start_date','end_date','artifact_path','run_id']].tail(20).to_string(index=False))
PY
```

Backtest/Walk-forward 해석 키:
- `sojourn_prob_*`: 현재 상태가 해당 기간(5/10/20/60/120일) 더 유지될 확률
- `transition_hazard_*`: 해당 기간 내 상태 전환 위험도 (`1 - sojourn_prob`)
- `PRETREND_HAZARD_THRESHOLD_10D`:
  - v3.3 hazard-aware override 게이트 임계치 (기본 `0.95`)
  - `transition_hazard_10d < threshold`일 때 override 억제
- `bias_state_source` / `bias_switch_reason` / `bias_cooldown_left`:
  - v3.4.2-phase 상태머신 메타
  - SIGNAL/PAPER에서 전환 근거 설명용으로 사용
- `cooldown_compressed_flag/reason`, `hard_gate_exit_assist_flag/reason`:
  - v3.4.2a 체류 완화 메타
  - PAPER_RESULT의 게이트/강도 섹션에서 보조 설명으로 노출

## Paper Trading 기본 조건 (보관 reference)
- 본 섹션은 현재 운영 명령이 아니라 참고용 legacy 기록이다.
- 초기 자금: `1,000,000원`
- 월 첫 거래일 DCA: `300,000원`
- 환산 환율: KIS 실시간 `fx_usdkrw` 우선, 결측 시 내부 fallback `1300`
- 실행 규칙:
  - 월요일: 전 거래일(T-1) 기준 신호 평가
  - 화요일: `INCREASE` 실행(현금 배포 매수)
  - 금요일: `DECREASE` 분할 매도(`50% -> 30% -> 20%`)
- 코어 제약:
  - `SCHD` 매도 금지
  - phase별 매수 강도만 조절(`next_invested_ratio`)
- 입력 범위 제어:
  - `PAPER_START_DATE` 환경변수(기본 `2026-01-01`) 이후 구간만 누적 계산
- 통화 처리:
  - 운영 입력(초기 자금/DCA)은 KRW로 관리
  - 실제 체결 계산은 USD(가격 소스: Gold EOD `adj_close`)로 환산 후 실행
- 계약 참조:
  - `docs/architecture/paper_execution_ledger_contract.md`
  - `docs/architecture/paper_trading_alert_contract.md`
  - `docs/architecture/next_step_signal_contract.md`
  - `docs/architecture/walk_forward_validation_contract.md`

### Paper Broker (KIS 모의투자 — broker_mock_trading_dag)
- **DAG**: `broker_mock_trading_dag` (strategy stages + broker state 기반 KIS MOCK 주문 실행, 수동 트리거)
- **선행**: `strategy_engine_dag` 실행 완료 후 해당 날짜의 strategy stages(`exposure`, `what_to_hold`, `next_step`)가 존재해야 함
- 실행 경로:
  - `strategy_engine_dag` → strategy stages 저장 (`data/strategy/...`)
  - `broker_mock_trading_dag` → strategy stages 직접 로드
  - `build_broker_target_orders()` → broker 잔고/현재가 기반 목표 수량 계산
  - KIS MOCK 주문 실행 → 결과 저장
- 저장 경로 (MOCK 전용):
  - `data/paper/MOCK/broker_orders/decision_date=...`
  - `data/paper/MOCK/broker_fills/decision_date=...`
  - `data/paper/MOCK/broker_cancelled/decision_date=...`
  - `data/paper/MOCK/reconciliation/decision_date=...`
  - `data/paper/MOCK/broker_bootstrap/decision_date=...`
  - `data/paper/MOCK/fx_daily/decision_date=...`
  - `data/paper/MOCK/market_probe/decision_date=...`
  - `data/paper/MOCK/candidate_report/decision_date=...`
- 실패 정책: fail-open (브로커 실패 시 Telegram 경고 후 계속 진행)
- 장 시간 게이트: 미국 ET 09:30~16:00 평일 외 실행 시 `status="skipped"` 반환 — 주문 없이 종료
- 환경변수:
  - `KIS_IS_MOCK=true`
  - `KIS_DRY_RUN=true` (권장 기본)
  - `BROKER_FILL_WAIT_SEC=30` — 미체결 취소 전 대기 시간(초), 기본 30
  - `BROKER_SKIP_MARKET_HOURS_CHECK=1` — 장 시간 체크 우회 (테스트/수동 실행 전용)
  - 모의 우선 키: `KIS_MOCK_APP_KEY`, `KIS_MOCK_APP_SECRET`, `KIS_MOCK_ACCOUNT_NO`, `KIS_MOCK_PRODUCT_CODE`, `KIS_MOCK_BASE_URL`
  - 실전 키(준비용): `KIS_LIVE_APP_KEY`, `KIS_LIVE_APP_SECRET`, `KIS_LIVE_ACCOUNT_NO`, `KIS_LIVE_PRODUCT_CODE`, `KIS_LIVE_BASE_URL`
  - 레거시 fallback: `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_ACCOUNT_NO`, `KIS_PRODUCT_CODE`, `KIS_BASE_URL`
  - 토큰 정책: 1시간 만료 기준 55분 선제 갱신 + 401/403 시 1회 재발급 재시도
  - 환율 정책: 가능하면 KIS 응답(`fx_usdkrw`) 우선 사용, 없으면 내부 fallback `1300`
- FAILED- prefix 주문: KIS 오류(장마감, 계좌 한도 등)로 ODNO 미수신 시 `order_id=FAILED-{8자리}` 기록 — fill check/cancel 없이 warn 처리
- 미체결 취소: ACCEPTED 주문은 `BROKER_FILL_WAIT_SEC` 대기 후 자동 취소, PARTIAL_FILLED는 경고만

### SIM/MOCK 동시 운영 기준
- 실행/저장은 SIM과 MOCK를 항상 수행한다.
- Telegram 발송은 `PAPER_TELEGRAM_MODE`로 제어한다:
  - `sim`: SIM 상세 1건
  - `mock`: MOCK 상세 1건
  - `compare`: 비교 요약 1건 + SIM 상세 1건 + MOCK 상세 1건
  - `off`: 미발송
### SIM / broker_mock 실행 모델 차이

| 항목 | SIM | broker_mock |
| --- | --- | --- |
| 초기 자금 | `PAPER_INITIAL_CAPITAL_KRW` (기본 1,000,000원) | KIS 실제 잔고 |
| DCA | 월 첫 거래일 `PAPER_MONTHLY_ADDITION_KRW` 자동 주입 | 없음 (실제 입금으로 관리) |
| 가격 소스 | Gold EOD `adj_close` (전날 종가) | KIS 실시간 현재가 |
| 요일 실행 규칙 | 화=`INCREASE`, 금=`DECREASE` | P4-4 구현 전: 신호 기반 즉시 실행 |
| 분할 매도 | `50% -> 30% -> 20%` staged sell | P4-4 구현 전: 없음 |
| SCHD 매도 금지 | 적용 | P4-4 구현 전: 없음 |
| Level 2 가드레일 | `NAV/TC < 0.85`, `ATH 낙폭 < -0.20` 시 INCREASE 차단 | P4-4 구현 전: 없음 |

- 혼동 방지 식별 필드:
  - `execution_mode` (`SIM`, `MOCK`)
  - `capital_source` (`ENV_SIM`, `BROKER_BALANCE`)
  - `broker_source` (`NONE`, `KIS_MOCK`, `KIS_LIVE`)
  - `nav_source` (`SIM_LEDGER`, `BROKER_SNAPSHOT`)

### Level 2 운영 경계 절차
- 중단 트리거:
  - `NAV / total_invested_capital < 0.85` (누적 투입원금 대비 -15%)
  - `(NAV - peak_NAV) / peak_NAV < -0.20` (ATH 대비 -20% 낙폭)
  - `PANIC streak >= 5`는 경고만 발송 (hard stop 아님)
- 중단 시 조치:
  - `INCREASE` 실행 차단 (Tuesday 매수 스킵)
  - `DECREASE`는 허용 (추가 손실 방지 목적 매도는 계속)
  - DCA 현금 주입 유지
  - `guardrail_paused=True` 기록
  - Telegram `risk_warnings`에 `🚨 Level 2 가드레일 발동` 포함
- 재개 조건:
  - `NAV / total_invested_capital >= 0.90`
  - `ATH 대비 낙폭 >= -0.15`
- 승인 포인트:
  - 별도 수동 승인 없이 자동 복귀를 기본으로 한다.

※ 임계값 근거: `docs/architecture/paper_execution_ledger_contract.md §10` (백테스트 2006~2024 실증)

## Walk-Forward 실행 (보관 reference)
- 본 섹션은 현재 운영 명령이 아니라 참고용 legacy 기록이다.
- v2 4년 창 / 2년 슬라이드 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.walk_forward --preset v2 --window-years 4 --step-years 2`
- v3.3 4년 창 / 2년 슬라이드 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.walk_forward --preset v3.3 --window-years 4 --step-years 2`
- 결과 저장(`parquet` + `summary.json`):
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.walk_forward --preset v2 --window-years 4 --step-years 2 --save`

## 결과 레지스트리 조회 (보관 reference)
- 저장 경로: `PRETREND_RESULT_ROOT/backtest/registry/pipeline=*/run_date=*/registry.parquet`
- 권장: 같은 구간(v2/v3.1/v3.2/v3.3) 실행 후 registry 기반 비교표를 재생성해 실행결과와 일치성 확인

## Backtest 테스트 실행 (보관 reference)
- Backtest 테스트:
  - `conda run -n pytest-pretrend pytest tests/pipeline/backtest/ -v`

## Airflow 서비스 관리 (systemd)

- 상태 해석:
  - `macro_pipeline_dag`, `eod_pipeline_dag`, `text_pipeline_dag` 관련 서비스는 운영 기준으로 본다.
  - `strategy_engine_dag`, `paper_trading_dag`, `broker_mock_trading_dag`, Telegram bot 관련 운영은 정지 상태 유지가 현재 기준이다.

### Legacy execution DAG paused 처리 (2026-05-12~)

Airflow systemd 자체는 가동 유지 (macro/eod/text DAG 운영 필요). Legacy execution DAG만 paused:

```bash
# Airflow UI에서 paused 처리 (CLI도 가능)
# /admin → DAG list에서 paper_trading_dag, broker_mock_trading_dag, strategy_engine_dag pause

# 또는 CLI
airflow dags pause paper_trading_dag
airflow dags pause broker_mock_trading_dag
airflow dags pause strategy_engine_dag

# 운영 유지 DAG는 unpause 상태
airflow dags unpause macro_pipeline_dag
airflow dags unpause eod_pipeline_dag

# Telegram bot systemd 정지 + 자동 시작 해제
sudo systemctl stop telegram-claude-bot.service
sudo systemctl disable telegram-claude-bot.service
```

확인:
```bash
systemctl is-active telegram-claude-bot.service  # → inactive
airflow dags list-runs --dag-id paper_trading_dag --no-backfill | head  # 최근 run 없음 (paused)
```

### Project Airflow CLI guard

Airflow CLI는 반드시 프로젝트 Airflow home과 DAG folder를 명시해서 실행한다. 이 env 없이 실행하면 기본 `~/airflow` metadata DB를 조회해 example DAG만 보이거나 active DAG 상태를 잘못 판단할 수 있다.

```bash
env \
  AIRFLOW_HOME=$PWD/airflow_pretrend \
  PYTHONPATH=$PWD/src \
  AIRFLOW__CORE__DAGS_FOLDER=$PWD/dags \
  AIRFLOW__CORE__LOAD_EXAMPLES=False \
  AIRFLOW__CORE__DEFAULT_TIMEZONE=Asia/Seoul \
  conda run -n airflow-pretrend airflow dags list
```

Legacy execution pause 상태 확인:

```bash
env \
  AIRFLOW_HOME=$PWD/airflow_pretrend \
  PYTHONPATH=$PWD/src \
  AIRFLOW__CORE__DAGS_FOLDER=$PWD/dags \
  AIRFLOW__CORE__LOAD_EXAMPLES=False \
  AIRFLOW__CORE__DEFAULT_TIMEZONE=Asia/Seoul \
  conda run -n airflow-pretrend airflow dags list | grep -E "strategy_engine_dag|paper_trading_dag|broker_mock_trading_dag"
```

서비스 파일 위치: `airflow_pretrend/airflow-scheduler.service`, `airflow_pretrend/airflow-webserver.service`
시스템 등록 위치: `/etc/systemd/system/`
환경변수 파일: `.env.airflow` (EnvironmentFile 지시자로 로드)

### 핵심 구성 요소
- **WorkingDirectory**: 프로젝트 루트 (`$PWD`)
- **PATH**: conda 환경 bin 디렉토리 포함 (SequentialExecutor subprocess에서 `airflow` 명령 사용)
- **EnvironmentFile**: `.env.airflow` — FRED_API_KEY, TELEGRAM 토큰, DAGS_FOLDER, DEFAULT_TIMEZONE 등
- **AIRFLOW__CORE__DEFAULT_TIMEZONE**: `Asia/Seoul` (`.env.airflow`에서 설정)

### 최초 등록 / 서비스 파일 업데이트
서비스 파일 수정 후 반드시 복사 + daemon-reload + restart:
```bash
sudo cp airflow_pretrend/airflow-scheduler.service /etc/systemd/system/
sudo cp airflow_pretrend/airflow-webserver.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable airflow-scheduler airflow-webserver
sudo systemctl restart airflow-scheduler airflow-webserver
```

### 서비스 상태 확인
```bash
systemctl status airflow-scheduler --no-pager
systemctl status airflow-webserver --no-pager
```

### 서비스 시작 / 중지 / 재시작
```bash
sudo systemctl start airflow-scheduler airflow-webserver
sudo systemctl stop airflow-scheduler airflow-webserver
sudo systemctl restart airflow-scheduler airflow-webserver
```

### 로그 확인
재시작 시 덮어쓰기 — 최신 실행 로그만 유지된다.
```bash
# 실시간 스트림
tail -f airflow_pretrend/logs/scheduler.log
tail -f airflow_pretrend/logs/webserver.log

# 에러만
tail -f airflow_pretrend/logs/scheduler-error.log
tail -f airflow_pretrend/logs/webserver-error.log
```

### DAG별 태스크 로그
Airflow 내부 태스크 로그는 systemd와 무관하게 AIRFLOW_HOME 아래에 누적된다.
```bash
ls airflow_pretrend/logs/dag_id=*/run_id=*/task_id=*/
```

### 트러블슈팅
| 증상 | 원인 | 조치 |
|------|------|------|
| Scheduler restart loop (`FileNotFoundError: 'airflow'`) | systemd 서비스에 PATH 미설정 | 서비스 파일에 `Environment=PATH=...` 추가 후 재배포 |
| `.env.airflow` 변수 미적용 (TIMEZONE=utc 등) | `EnvironmentFile` 누락 또는 대시 prefix(`-`) | `EnvironmentFile=/path/.env.airflow` (대시 없이) 설정 |
| DAG 미인식 | `DAGS_FOLDER` 경로 불일치 | `.env.airflow`의 `AIRFLOW__CORE__DAGS_FOLDER` 확인 |
| 서비스 파일 수정 후 반영 안됨 | `/etc/systemd/system/`에 복사 안됨 | `sudo cp` + `daemon-reload` + `restart` |

환경변수 확인 (실행 중 프로세스):
```bash
cat /proc/$(systemctl show airflow-scheduler -p MainPID --value)/environ | tr '\0' '\n' | grep -E "TIMEZONE|DAGS_FOLDER"
```

## Airflow DAG 스케줄 요약

| DAG | 스케줄 (KST) | 설명 |
|-----|-------------|------|
| `eod_pipeline_dag` | 매일 08:00 KST | EOD Bronze→Silver→Gold (미국 장 마감 후 2시간+) |
| `macro_pipeline_dag` | 매일 09:00 KST | FRED Macro Bronze→Silver→Gold |
| `strategy_engine_dag` | paused | Legacy execution DAG (운영 중단) |
| `paper_trading_dag` | paused | Legacy execution DAG (운영 중단) |

실행 순서(현재 운영): EOD(08:00) → Macro(09:00). Legacy execution DAG는 paused 상태다.
모든 DAG의 `start_date`는 `tz="Asia/Seoul"` 기준이며, `default_timezone=Asia/Seoul`로 설정됨.

### Telegram 알림 설정
`.env.airflow`에 설정 (systemd가 EnvironmentFile로 로드):
```
TELEGRAM_BOT_TOKEN=<bot_token>
TELEGRAM_CHAT_ID=<chat_id>
```
미설정 시 알림만 스킵되고 파이프라인은 정상 실행된다.

Telegram 표기 기준(혼동 방지):
- `중기 성향`: `mid_regime` 표시 별칭 (`RISK_ON/NEUTRAL/RISK_OFF`)
- `단기 공황 여부`: 사용자 표시 별칭 (`is_panic = not risk_gate`)
  - `예` = 단기 PANIC
  - `아니오` = 단기 정상
- `전술 실행`: `run_universe` 스위치 표시 (`허용/제한`)
- `message_type`:
  - `SIGNAL` = `strategy_engine_dag` 메시지
  - `PAPER_RESULT` = `paper_trading_dag` 메시지
- snapshot 단일소스 원칙:
  - SIGNAL/PAPER의 next-step 표시는 `next_step_signal snapshot` 값을 직접 소비한다.
  - snapshot 결측 시 즉석 재계산 없이 `UNKNOWN/N/A` fail-open 표기만 허용한다.
- SIGNAL `다음 스텝 가설` 표기:
  - `10D bias+confidence + transition_hazard_10d + transition_expected_10d` 상세
  - `5D/20D/60D/120D bias+confidence` 요약 1줄
  - `horizon_bias_diversity_count`, `horizon_bias_diversity_ratio_60d`, `horizon_conf_spread` 진단 1줄
- SIGNAL `전술 그룹 다음 스텝` 표기:
  - `asset_group별 state_now -> expected_10d`
  - `group_transition_hazard_10d` (결측 시 `N/A`)
- PAPER_RESULT `게이트/강도` 표기:
  - `effective_bias`, `bias_source`, `override_reason`
  - `hard_gate(run_universe/risk_gate)`
  - `effective_max_tactical_slots`, `effective_tactical_weight`, `hazard_10d`
  - `paper_start_date` (누적 시뮬레이션 시작일)
- PAPER_RESULT 식별 필드:
  - `execution_mode`, `capital_source`, `broker_source`, `nav_source`
- LLM 해석 레이어(향후 확장):
  - 적용 범위는 문장 요약/해석에 한정(신호 생성/게이트/배분 입력 변경 금지)
  - LLM 실패/지연 시 결정론 템플릿으로 fallback, DAG 성공 상태 유지
  - 운영 비용 상한은 환경변수로 관리(`PRETREND_LLM_DAILY_BUDGET_USD`, 기본 0=비활성)
- PAPER_RESULT `전술 적용 근거` 표기:
  - `group_gate_applied_groups`, `group_gate_reduced_groups`, `group_gate_source`
- 실패 정책:
  - Telegram 전송 오류/토큰 미설정 시 fail-open (경고 로그만 남기고 DAG 성공 유지)

### SIGNAL 메시지 구조 (8섹션 고정)

`strategy_engine_dag`가 생성하는 SIGNAL 메시지는 아래 8개 섹션으로 고정된다.
섹션 순서·헤더 문자열은 계약 변경 없이 변경 불가.

| 순서 | 섹션 헤더 | 표시 내용 | 비고 |
|------|-----------|-----------|------|
| 1 | 헤더 | 날짜 · `message_type=SIGNAL` · `source_job=strategy_engine_dag` · action(비중 변화) | 공황 시 `⚠️ 단기 공황 — 매도 동결` 삽입 |
| 2 | `── 시장 컨텍스트 ──` | 3-state(장기/중기/단기) + 스위치(공황여부/전술실행) | `build_context_lines()` + `build_switch_lines()` |
| 3 | `── 다음 스텝 가설 ──` | **10D 상세** (bias/hazard/expected) + 지평 요약(5/20/60/120D) + 분화도 | **10D 중심 원칙** |
| 4 | `── 시장 근거 ──` | 4축(매크로·가격·수급구조·심리) | `build_evidence_lines()` |
| 5 | `── 진단 요약 ──` | 12셀 품질 (coverage/unknown 비율) | snapshot 결측 시 즉석 계산 fallback |
| 6 | `── 전술 그룹 다음 스텝 ──` | asset_group별 state→expected(5D/10D) + hazard | `format_group_transition_lines()` |
| 7 | `── 전술 ETF (SPY 대비 20일 상대강도) ──` | 그룹별 상위 ETF + RS 수치 | COUNTRY→COMMODITY→BOND→SECTOR 순 |

**10D-centric 원칙**: `다음 스텝 가설` 섹션에서 10D bias/hazard/expected를 1차(상단)로 표시하고,
나머지 지평(5D·20D·60D·120D)은 한 줄 요약으로 압축한다. 10D는 요약 줄에 포함하지 않는다.

## Cloudflare Tunnel 진입 조건

Phase 3 dashboard 로컬 E2E 검증 완료 후 별도 운영 task로 진입할 때 아래 checklist를 충족한다.

- [ ] Dashboard local E2E 검증 완료
- [ ] API key auth 확인
- [ ] `.env` gitignore 확인
- [ ] DB port 외부 노출 없음
- [ ] CORS 허용 범위 결정
- [ ] read-only endpoint만 외부 노출
- [ ] Swagger/OpenAPI 공개 여부 결정
- [ ] 로그에 secret/DB URL 노출 없음
- [ ] `cloudflared` config 문서화
- [ ] local runtime runbook 작성
- [ ] Cloudflare exposure checklist 작성

**Status**: Phase 3 dashboard 진행 후 별도 운영 task에서 진입한다.
