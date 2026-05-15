# P30-4 — Reproducibility Verification

## 0. 문서 메타

- Task ID: `P30-4`
- Title: `Reproducibility Verification`
- Status: `DONE`
- Phase: `P30 — Reproducible Runtime & Data Bootstrap`
- Parent: `P30`
- Source(anchor): `.agent/task/P30-4_reproducibility_verification.md`
- Last Updated: `2026-05-15`
- Owner: `Codex`

### 병렬 실행 메타

- `parallel_safe`: `no`
- `depends_on`: `[P30-1, P30-2, P30-3]`
- `blocks`: `[P30 parent DONE]`
- `executor`: `local`
- `file_scope`:
  - 수정: [`README.md`, `docs/operation/reproducible_runtime_contract.md`, `docs/testing/operational_invariant_test_contract.md`, `docs/operation_guide.md`, `scripts/`, `tests/ops/`]
  - 읽기전용: [`docker-compose.yml`, `Dockerfile.api`, `Dockerfile.dev`, `.dockerignore`, `.env.example`]
- `merge_strategy`: `review`

---

## 1. 목표

- 현재 문제: Docker/restore/docs 절차가 실제 신규 clone 기준으로 검증되는 gate가 없다.
- 이번 task의 목표: build/test/smoke/restore/volume/security/README 절차를 한 번에 검증하는 기준을 만든다.
- 기대 효과: P30 완료 선언이 느낌이 아니라 재현 가능한 체크리스트가 된다.

---

## 2. 작업 범위

### 2.1 In-Scope

- 신규 clone 기준 build/test/smoke run 검증.
- DB restore 절차 검증.
- volume mount 확인.
- 민감 파일 미포함 확인.
- README 절차 검증.
- 필요한 경우 `tests/ops/` 또는 `scripts/check_*` 추가.

### 2.2 Out-of-Scope

- Phase 3 dashboard 구현.
- Cloudflare tunnel 검증.
- full Airflow E2E.
- active DB destructive restore.

### 2.3 수정 금지

- `.env` 값 출력.
- 운영 DB overwrite.
- volume 삭제.
- Docker image에 data/secrets 포함.

---

## 3. 설계 불변식

- 검증은 신규 clone 사용자가 따라 할 수 있는 절차여야 한다.
- OS별 README 명령이 실제 기준이다.
- Makefile은 보조이며 유일한 검증 경로가 아니다.
- restore 검증은 별도 DB/volume에서 수행한다.

---

## 4. 구현 요구사항

1. P30 검증 체크리스트를 docs/testing 또는 operation docs에 추가한다.
2. README 절차와 실제 명령을 동기화한다.
3. build/test/smoke 명령을 실행하고 결과를 task 문서에 기록한다.
4. DB restore 검증은 active DB를 건드리지 않는 방식으로 수행한다.
5. sensitive file exclusion을 Git/build context/image 관점에서 확인한다.

---

## 5. 검증 방법

```bash
docker compose config --quiet
docker compose build
docker compose up -d postgres api
docker compose ps
docker build -t pretrend-dev -f Dockerfile.dev .
docker run --rm pretrend-dev pytest -q --tb=short
```

volume/sensitive checks:

```bash
docker compose exec -T postgres sh -c 'test -d /var/lib/postgresql/data'
docker compose exec -T postgres sh -c 'test -d /backups'
git status --ignored --short .env .env.airflow .local data logs result .agent
```

---

## 6. 완료 기준

- [x] 신규 clone 기준 build/test/smoke 절차가 검증되었다.
- [x] DB restore 절차가 검증되었다.
- [x] volume mount가 확인되었다.
- [x] 민감 파일 미포함 확인이 완료되었다.
- [x] README 절차가 실제 명령과 일치한다.

## 7. 완료 기록

### 변경 요약

- `docker compose config`가 `.env` 값을 펼쳐 출력할 수 있어 README / runtime contract / testing contract / task docs 기준을 `docker compose config --quiet`로 보정했다.
- dev/test image가 P30 ops audit에 필요한 repository metadata를 포함하도록 `Dockerfile.dev`에 `docker-compose.yml`, Dockerfiles, Dockerfile-specific ignore files, `.dockerignore`, `.env.example` copy를 추가했다.
- `.env.example`은 placeholder 문서이므로 Docker build context에서 dev/test image audit 용도로만 복사 가능하도록 ignore 예외(`!.env.example`)를 추가했다.
- `tests/ops/test_reproducible_runtime_contract.py`를 추가해 compose volume env, Docker ignore, image role separation, README/runtime gate, `.env.example` placeholder를 contract test로 보호했다.
- `docs/testing/operational_invariant_test_contract.md`에 P30 reproducible runtime / volume-sensitive / restore gate를 추가했다.

### 수정 파일

- `README.md`
- `.dockerignore`
- `Dockerfile.dev`
- `Dockerfile.api.dockerignore`
- `Dockerfile.dev.dockerignore`
- `docs/operation/reproducible_runtime_contract.md`
- `docs/testing/operational_invariant_test_contract.md`
- `tests/ops/test_reproducible_runtime_contract.py`
- `.agent/task/P30-4_reproducibility_verification.md`
- `.agent/task/P30_parent_reproducible_runtime.md`
- `.agent/TASK_QUEUE.md`

### 검증 결과

```bash
pytest tests/ops/ -q --tb=short
```

- PASS: `5 passed`.

```bash
docker compose config --quiet
docker compose build
docker compose up -d postgres api
docker compose ps
```

- PASS.
- `pretrend-api`: healthy.
- `pretrend-postgres`: healthy.

```bash
docker build -t pretrend-api-test -f Dockerfile.api .
docker build -t pretrend-dev -f Dockerfile.dev .
docker run --rm pretrend-dev pytest -q --tb=short
docker run --rm pretrend-dev pytest tests/ops/ -q --tb=short
```

- PASS.
- Full Docker pytest: `438 passed, 32 skipped`.
- Docker ops gate: `5 passed`.

```bash
docker compose exec -T postgres sh -c 'test -d /var/lib/postgresql/data'
docker compose exec -T postgres sh -c 'test -d /backups'
git status --ignored --short .env .env.airflow .local data logs result .agent
```

- PASS.
- `.env`, `.env.airflow`, `.local/`, `data/`, `logs/`, `result/`, `.agent/` are ignored.
- Git emitted a permission warning while traversing `.local/postgres-data/`; ignored status was still visible and no file contents were printed.

```bash
docker run --rm --entrypoint sh pretrend-api-test -c 'test ! -e /app/.env && test ! -d /app/data && test ! -d /app/logs && test ! -d /app/result && test ! -d /app/tests && test ! -d /app/docs'
docker run --rm --entrypoint sh pretrend-dev -c 'test ! -e /app/.env && test ! -d /app/data && test ! -d /app/logs && test ! -d /app/result && test -d /app/tests && test -d /app/docs && test -f /app/docker-compose.yml && test -f /app/.env.example'
```

- PASS.

```bash
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /backups/pretrend_test.dump'
docker compose exec -T postgres sh -c 'test -s /backups/pretrend_test.dump'
docker compose exec -T postgres sh -c 'createdb -U "$POSTGRES_USER" pretrend_restore_check_p30_4'
docker compose exec -T postgres sh -c 'pg_restore --exit-on-error -U "$POSTGRES_USER" -d pretrend_restore_check_p30_4 --no-owner --no-privileges /backups/pretrend_test.dump'
docker compose exec -T postgres sh -c 'dropdb -U "$POSTGRES_USER" pretrend_restore_check_p30_4'
```

- PASS.
- Restore check table counts before cleanup:
  - `alembic_version`: 1
  - `gold_macro_features`: 26106
  - `gold_eod_features`: 179037
  - `similarity_regime`: 576566
  - `similarity_gold`: 571877
  - `explainability_cache`: 4
- Restore check DB cleanup confirmed.

```bash
docker compose exec -T api python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health', timeout=5).status)"
```

- PASS: `200`.

### 남은 이슈

- Host-side `curl http://localhost:8000/health` returned `000` from the sandboxed command environment, while the API container healthcheck and in-container `/health` smoke returned healthy/200. This is treated as a sandbox boundary issue, not an API runtime failure.
- P30-5 and P30-6 remain pending for `.agent` publication whitelist and docs marker classification.
