# P30-2 — Docker Build/Test Runtime

## 0. 문서 메타

- Task ID: `P30-2`
- Title: `Docker Build/Test Runtime`
- Status: `DONE`
- Phase: `P30 — Reproducible Runtime & Data Bootstrap`
- Parent: `P30`
- Source(anchor): `.agent/task/P30-2_docker_build_test_runtime.md`
- Last Updated: `2026-05-15`
- Owner: `Codex`

### 병렬 실행 메타

- `parallel_safe`: `conditional`
- `depends_on`: `[P30-1]`
- `blocks`: `[P30-4]`
- `executor`: `local`
- `file_scope`:
  - 수정: [`Dockerfile.api`, `Dockerfile.dev`, `.dockerignore`, `Dockerfile.api.dockerignore`, `Dockerfile.dev.dockerignore`, `requirements*.txt`, `README.md`, `docs/operation/reproducible_runtime_contract.md`]
  - 읽기전용: [`tests/`, `docs/`, `src/`, `pyproject.toml`]
- `merge_strategy`: `review`

---

## 1. 목표

- 현재 문제: 현재 `.dockerignore`는 API image 중심이라 `tests/`, `docs/`가 빠져 dev/test image 검증에 맞지 않는다.
- 이번 task의 목표: API runtime image와 dev/test image를 분리하고 Docker 내부 pytest/smoke 실행 기반을 만든다.
- 기대 효과: 신규 clone에서 Python/패키지 차이를 줄이고 동일한 검증 환경을 사용할 수 있다.

---

## 2. 작업 범위

### 2.1 In-Scope

- `Dockerfile.dev` 추가 또는 확정.
- API image와 dev/test image 역할 분리.
- Dockerfile-specific ignore 지원 여부 확인.
- `tests/`와 필요한 `docs/`가 dev/test image에서 사용 가능하도록 build context 조정.
- data/secrets/cache는 image/build context에서 제외.

### 2.2 Out-of-Scope

- API endpoint 변경.
- 테스트 코드 의미 변경.
- 전체 dependency refactor.
- Airflow Docker image 추가.

### 2.3 수정 금지

- `.env` 또는 secret 값 image 포함.
- `data/`, `.local/`, `logs/`, `result/` image 포함.
- API service runtime contract 임의 변경.

---

## 3. 설계 불변식

- `Dockerfile.api`는 API serving runtime용이다.
- `Dockerfile.dev`는 pytest, smoke run, docs verification용이다.
- Docker image는 data/secrets/logs를 포함하지 않는다.
- dev/test image에는 test 실행에 필요한 `tests/`와 문서 검증에 필요한 `docs/`가 포함되어야 한다.

---

## 4. 구현 요구사항

1. 현재 Docker 버전에서 `Dockerfile.<name>.dockerignore` 동작 여부를 확인한다.
2. 가능하면 `Dockerfile.api.dockerignore`와 `Dockerfile.dev.dockerignore`를 사용한다.
3. 불가능하면 root `.dockerignore`를 공통 안전 제외 규칙으로 둔다.
4. `Dockerfile.dev`를 추가하고 pytest 실행 entry를 검증한다.
5. README에 API build와 dev/test build를 구분해 문서화한다.

---

## 5. 검증 방법

```bash
docker build -t pretrend-api-test -f Dockerfile.api .
docker build -t pretrend-dev -f Dockerfile.dev .
docker run --rm pretrend-dev pytest -q --tb=short
```

민감 파일 확인 후보:

```bash
docker run --rm pretrend-dev sh -c 'test ! -f .env && test ! -d data && test ! -d .local'
```

---

## 6. 완료 기준

- [x] API image와 dev/test image 목적이 분리되어 있다.
- [x] dev/test image에서 agreed pytest 또는 smoke test가 실행된다.
- [x] build context에서 data/secrets/logs/result가 제외된다.
- [x] README에 두 image의 역할이 설명되어 있다.

---

## 7. 검증 결과

검증일: 2026-05-15

실행한 명령:

```bash
docker build -t pretrend-api-test -f Dockerfile.api .
docker build -t pretrend-dev -f Dockerfile.dev .
docker run --rm pretrend-api-test sh -c 'test ! -d tests && test ! -d docs && test ! -f .env && test ! -d data && test ! -d .local && test ! -d logs && test ! -d result && echo api-image-layout-ok'
docker run --rm pretrend-dev sh -c 'test -d dags && test -d tests && test -d docs && test ! -f .env && test ! -d data && test ! -d .local && test ! -d logs && test ! -d result && echo dev-image-layout-ok'
docker run --rm pretrend-dev pytest -q --tb=short
```

결과:

- API image build PASS.
- Dev/test image build PASS.
- Dockerfile-specific ignore 동작 확인:
  - `Dockerfile.api` build context: `138.82kB`
  - `Dockerfile.dev` build context: `5.84MB` before `dags/` fix, `254.31kB` after incremental rebuild output; dev image includes `dags/`, `tests/`, `docs/`.
- API image layout check: `api-image-layout-ok`.
- Dev/test image layout check: `dev-image-layout-ok`.
- Docker dev/test pytest: `433 passed, 32 skipped`.

수정 중 발견 및 조치:

- 첫 Docker pytest는 `dags/` 미포함으로 DAG tests 21개가 `ModuleNotFoundError`로 실패했다.
- `Dockerfile.dev`에 `COPY dags/ ./dags/`를 추가해 해결했다.
