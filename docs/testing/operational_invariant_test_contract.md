# 운영 invariant 테스트 계약

Markers: testing, contract
Status: active

## 1. 목적

Pretrend의 pytest는 단순히 함수가 실행되는지 확인하는 도구가 아니라, 운영 중 깨지면 안 되는 약속을 막는 수문장이다. 테스트는 다음 질문에 답해야 한다.

- 공개 API의 인증, 응답 스키마, 오류 계약이 바뀌었는가?
- Gold/Postgres serving table의 grain, key, PIT 규칙이 깨졌는가?
- 재실행 시 중복 append나 partial snapshot이 남는가?
- Airflow DAG가 import, schedule, task graph 단계에서 깨졌는가?
- Observability 코드가 archived Personal Track에 다시 결합되었는가?
- explanation/API 텍스트가 예측, 추천, 매매 판단 의미로 넘어갔는가?
- Docker, volume, backfill, restore 절차가 새 clone 기준으로 재현 가능한가?

각 테스트는 가능하면 함수명, class명, docstring, assertion 메시지 중 하나에 “어떤 회귀를 막는지”를 드러낸다. 실패 메시지는 기능명이 아니라 깨진 운영 약속을 바로 가리켜야 한다.

운영 장애를 직접 막는 테스트는 [운영 장애 시나리오 카탈로그](operational_failure_scenario_catalog.md)의 `OFS-*` ID를 기준으로 작성한다. 새 테스트를 추가할 때는 먼저 장애 시나리오, synthetic test data, 기대 invariant를 정의한 뒤 pytest로 고정한다.

## 2. Pytest Marker

| Marker | 의미 |
| --- | --- |
| `contract` | 공개 인터페이스, schema, boundary, 문서화된 동작 계약. |
| `invariant` | PIT, idempotency, grain/key, forbidden term, fail-open 같은 운영 불변조건. |
| `db` | 실제 또는 provisioned Postgres/TimescaleDB 연결이 필요한 테스트. |
| `dag` | Airflow DAG import, schedule, task graph 검증. |
| `slow` | 빠른 로컬 루프에 넣기 어려운 큰 fixture 또는 외부 provider 테스트. |
| `personal` | frozen Personal Track 회귀 자산. 기본 운영 gate에서는 제외한다. |

경로 기반 자동 분류는 루트 `conftest.py`가 담당한다. 테스트 파일을 추가하면 `tests/ops/test_pytest_gate_contract.py`가 해당 파일이 gate marker를 받는지 확인한다.

## 3. Named Gate

`pytest --gate <name>`은 marker expression을 사람이 기억하지 않아도 되도록 고정한 운영 명령이다.

| Gate | 명령 | 쓰는 시점 |
| --- | --- | --- |
| `fast` | `pytest --gate fast -q --tb=short` | 로컬 개발, GitHub Actions 기본 CI. `slow`, `db`, `personal` 제외. |
| `contracts` | `pytest --gate contracts -q --tb=short` | API/schema/boundary/invariant 변경 전후. |
| `runtime` | `pytest --gate runtime -q --tb=short` | Docker/Postgres/serving mirror/backfill 변경 후. |
| `dags` | `pytest --gate dags -q --tb=short` | Airflow DAG 또는 scheduling 변경 후. |
| `pre-dashboard` | `pytest --gate pre-dashboard -q --tb=short` | dashboard 진입 전 전체 active surface 점검. |
| `personal` | `pytest --gate personal -q --tb=short` | archived Personal Track을 명시적으로 점검할 때만. |
| `all` | `pytest --gate all -q --tb=short` | gate deselection 없이 pytest 기본 수집을 실행할 때. |

환경 변수로도 같은 정책을 적용할 수 있다.

```bash
PRETREND_PYTEST_GATE=fast pytest -q --tb=short
```

기존 marker expression은 디버깅용으로만 사용한다.

```bash
pytest -m "not slow and not db and not personal" -q --tb=short
pytest -m "contract or invariant" -q --tb=short
pytest -m "dag" -q --tb=short
```

## 4. 테스트 그룹별 계약

| 그룹 | 보호하는 운영 약속 | 기본 marker |
| --- | --- | --- |
| `api_contract` | FastAPI endpoint의 auth, response schema, error behavior. | `contract` |
| `gold_feature` | Gold Parquet SOT의 grain, required columns, PIT rule, lineage. | `invariant`, `contract` |
| `gold_sync` | Gold Parquet -> Postgres mirror의 upsert, watermark, idempotency. | `db`, `invariant` |
| `similarity` | min-gap, score/rank 범위, historical comparison 의미. | `invariant` |
| `explainability` | evidence-bound, prediction-free, fail-open, cache behavior. | `invariant` |
| `boundary` | Observability와 archived Personal Track의 import boundary. | `contract` |
| `dag` | Airflow DAG import와 task graph shape. | `dag`, `contract` |
| `runtime_reproducibility` | Docker compose, mounted volume, sensitive-file exclude, restore/backfill runbook. | `contract`, `invariant` |
| `personal_archive` | frozen Personal Track 회귀 자산 보존. | `personal`, `slow` |

## 5. Docker/P30 재현성 Gate

Docker dev/test image에서는 named gate를 우선 사용한다.

```bash
docker compose config --quiet
docker compose build
docker compose up -d postgres api
docker compose ps
docker build -t pretrend-dev -f docker/Dockerfile.dev .
docker run --rm pretrend-dev pytest --gate fast -q --tb=short
docker run --rm pretrend-dev pytest --gate runtime -q --tb=short
```

volume과 민감 파일 제외는 pytest 밖의 운영 명령으로 확인한다.

```bash
docker compose exec -T postgres sh -c 'test -d /var/lib/postgresql/data'
docker compose exec -T postgres sh -c 'test -d /backups'
git status --ignored --short .env .env.airflow .local data logs result .agent
docker run --rm --entrypoint sh pretrend-api-test -c 'test ! -e /app/.env && test ! -d /app/data && test ! -d /app/logs && test ! -d /app/result && test ! -d /app/tests && test ! -d /app/docs'
docker run --rm --entrypoint sh pretrend-dev -c 'test ! -e /app/.env && test ! -d /app/data && test ! -d /app/logs && test ! -d /app/result && test -d /app/tests && test -d /app/docs'
```

restore gate는 active DB가 아니라 별도 DB에서 수행한다.

```bash
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /backups/pretrend_test.dump'
docker compose exec -T postgres sh -c 'test -s /backups/pretrend_test.dump'
docker compose exec -T postgres sh -c 'createdb -U "$POSTGRES_USER" pretrend_restore_check'
docker compose exec -T postgres sh -c 'pg_restore --exit-on-error -U "$POSTGRES_USER" -d pretrend_restore_check --no-owner --no-privileges /backups/pretrend_test.dump'
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d pretrend_restore_check -Atc "SELECT COUNT(*) FROM alembic_version;"'
docker compose exec -T postgres sh -c 'dropdb -U "$POSTGRES_USER" pretrend_restore_check'
```

pytest에서는 `tests/ops/test_restore_shadow_db.py`가 shadow DB 이름과 `pg_restore` command plan을 먼저 고정한다. 실제 dump 복구까지 확인하려면 `PRETREND_RESTORE_CHECK_DUMP`에 dump 경로를 지정하고 `pytest tests/ops/test_restore_shadow_db.py -q --tb=short`를 실행한다.

DB contract 테스트는 connection 확인에서 끝내지 않는다. 다만 운영 DB에 synthetic row를 넣지 않는다. `tests/ops/test_db_synthetic_data_contract.py`는 `PRETREND_TEST_DATABASE_URL`이 가리키는 격리 test DB에서만 실행되며, DB 이름이 `pretrend_test*`가 아니면 실패한다. 이 DB는 Alembic head까지 migrate된 상태여야 하고, 테스트는 핵심 serving table에 synthetic row를 insert/read한 뒤 test DB 내부에서만 cleanup한다.

Docker test profile은 운영 DB와 분리된 Postgres/TimescaleDB와 test runner를 제공한다. `test-runner`는 pytest 실행 전에 test DB에 Alembic migration을 먼저 적용한다.

```bash
docker compose --profile test up -d postgres-test
docker compose --profile test run --rm test-runner
```

## 6. 운영 SQL Check

데이터 최신성과 row coverage는 pytest fixture로 완전히 흡수되기 전까지 SQL 운영 점검으로 유지한다.

```sql
SELECT COUNT(*), MAX(trade_date) FROM gold_macro_features;
SELECT COUNT(*), MAX(trade_date) FROM gold_eod_features;
SELECT COUNT(*), MAX(trade_date) FROM gold_market_state_similarity_feature;
SELECT COUNT(*), MAX(query_date) FROM similarity_regime;
SELECT COUNT(*), MAX(query_date) FROM similarity_gold;
SELECT use_case, COUNT(*), MAX(query_date) FROM explainability_cache GROUP BY 1;
```

## 7. 남은 자동화 후보

| 후보 | 이유 | Marker |
| --- | --- | --- |
| Alembic shadow upgrade/downgrade | schema rebuild 가능성을 수동 확인에 남기지 않기 위함. | `db`, `invariant`, `slow` |
| API forbidden term live-response | 문서/negative fixture가 아니라 실제 응답이 observer-only인지 확인. | `invariant` |
| Airflow metadata paused-state check | archived execution DAG가 의도치 않게 켜지는 것을 방지. | `dag`, `contract` |

## 8. Boundary Import 검사 기준 (allowlist-aware)

`tests/observability/test_boundary_imports.py`는 grep 기반이 아니라 Python AST 파싱 기반이다. `ast.Import` / `ast.ImportFrom` 노드를 순회하며 아래 `FORBIDDEN_MODULE_PREFIXES` 튜플로 시작하는 import를 위반으로 판정한다.

```python
FORBIDDEN_MODULE_PREFIXES = (
    "pretrend.pipeline.backtest",
    "pretrend.pipeline.strategy_engine",
    "pretrend.pipeline.paper",
    "pretrend.pipeline.broker",
    "pretrend.backtest",
    "pretrend.paper",
    "pretrend.broker",
)
```

**허용 범위(implicit allowlist)**: 위 튜플에 포함되지 않은 모든 모듈 경로는 허용된다. 스캔 범위는 `src/pretrend/observability/**/*.py`이므로, 다른 경로(예: `dags/`, `tests/`, `src/pretrend/pipeline/strategy_engine/` 내부)는 검사 대상이 아니다.

**re-export shim 패턴**: backward compat을 위해 Personal Track 모듈이 Observability 모듈 기능을 re-export하는 shim을 두는 것은 허용된다. 이 경우 shim 파일은 Personal Track namespace(`pretrend.pipeline.strategy_engine.*`) 안에 두며, Observability 코드가 Personal Track namespace를 import하는 방향이 되면 안 된다.

**금지 목록 확장 시**: 새 Personal Track 네임스페이스가 추가되면 `FORBIDDEN_MODULE_PREFIXES` 튜플에 추가하고, `boundary` 그룹 테스트를 재실행해 위반 0을 확인한다.

---

## 9. 변경 이력

- 2026-05-15: P29 운영 invariant 테스트 계약 초안 작성.
- 2026-05-15: P30 runtime, volume, restore gate 추가.
- 2026-05-17: `pytest --gate` named gate와 경로 기반 marker 분류 계약 추가.
- 2026-05-17: shadow restore command plan과 observability chain smoke를 P2 pytest anchor로 승격.
- 2026-05-17: 운영 장애 시나리오 카탈로그와 synthetic test data 기준 연결.
- 2026-05-17: DB contract 테스트는 운영 DB rollback 대신 격리된 `pretrend_test*` DB synthetic row insert/read로 검증하도록 명시.
- 2026-05-27: §8 Boundary import 검사 기준 추가 — AST 기반 allowlist-aware 기준, re-export shim 패턴, 금지 목록 확장 방법 명시 (follow-up-P29-1.C).
