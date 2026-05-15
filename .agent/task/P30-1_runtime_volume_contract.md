# P30-1 — Runtime Volume Contract

## 0. 문서 메타

- Task ID: `P30-1`
- Title: `Runtime Volume Contract`
- Status: `DONE`
- Phase: `P30 — Reproducible Runtime & Data Bootstrap`
- Parent: `P30`
- Source(anchor): `.agent/task/P30-1_runtime_volume_contract.md`
- Last Updated: `2026-05-15`
- Owner: `Codex`

### 병렬 실행 메타

- `parallel_safe`: `no`
- `depends_on`: `[]`
- `blocks`: `[P30-2, P30-3, P30-4]`
- `executor`: `local`
- `file_scope`:
  - 수정: [`docker-compose.yml`, `.env.example`, `docs/operation/reproducible_runtime_contract.md`, `docs/operation_guide.md`, `docs/environment.md`, `README.md`]
  - 읽기전용: [`.agent/task/P30_parent_reproducible_runtime.md`, `.agent/task/P30_draft_reproducible_runtime_data_bootstrap.md`]
- `merge_strategy`: `review`

---

## 1. 목표

- 현재 문제: Postgres serving DB bind mount가 repo-local `./.local/postgres-data`에 사실상 고정되어 있다.
- 이번 task의 목표: DB/data/log/backup host path를 env var로 바꿀 수 있게 하고 OS별 실행 예시를 문서화한다.
- 기대 효과: Linux 로컬, 외장하드, Windows PowerShell, WSL2 경로를 같은 compose 계약으로 사용할 수 있다.

---

## 2. 작업 범위

### 2.1 In-Scope

- `PRETREND_POSTGRES_DATA_DIR` 도입.
- `PRETREND_BACKUP_DIR` 도입.
- `PRETREND_HOST_DATA_DIR` / `PRETREND_HOST_LOG_DIR` 도입.
- compose 기본값은 기존 경로와 호환되게 유지.
- README 또는 operation docs에 OS별 path 예시 추가.

### 2.2 Out-of-Scope

- DB restore 실제 수행.
- dev/test Docker image 구현.
- Airflow full Docker 운영화.
- 외장하드 고가용성/장애 대응.

### 2.3 수정 금지

- 기존 DB data 삭제.
- `docker compose down -v`.
- `.env` 값 출력 또는 commit.
- Postgres image tag 변경.

---

## 3. 설계 불변식

- `PRETREND_POSTGRES_DATA_DIR`에 지정한 host path가 active Postgres volume 위치다.
- 지정하지 않으면 기존 `./.local/postgres-data` 기본값을 사용한다.
- `PRETREND_BACKUP_DIR`은 `/backups`로 mount한다.
- restore는 이 task에서 수행하지 않는다.

---

## 4. 구현 요구사항

1. `docker-compose.yml`의 postgres volume을 env var 기반으로 변경한다.
2. `api` service에 app data/log mount가 필요한지 검토하고 최소 변경으로 반영한다.
3. `.env.example`에 새 env var와 설명을 추가한다.
4. `docs/operation/reproducible_runtime_contract.md`와 운영 문서의 경로 계약을 동기화한다.
5. README에 Linux/WSL2/Windows PowerShell 예시를 추가한다.

---

## 5. 검증 방법

```bash
docker compose config
docker compose ps
docker compose exec -T postgres sh -c 'test -d /var/lib/postgresql/data'
docker compose exec -T postgres sh -c 'test -d /backups'
```

검증 메모:

- Docker 명령은 running compose 상태에 따라 escalation이 필요할 수 있다.
- active DB를 덮어쓰거나 volume을 삭제하지 않는다.

---

## 6. 완료 기준

- [x] compose config가 유효하다.
- [x] 기본값으로 기존 local DB path가 유지된다.
- [x] env var override 예시가 문서화되어 있다.
- [x] backup dir mount가 확인된다.
- [x] `.env.example`에는 secret 값이 없다.

---

## 7. 검증 결과

검증일: 2026-05-15

실행한 명령:

```bash
docker compose config --quiet
docker compose up -d postgres api
docker compose ps
docker compose exec -T postgres sh -c 'test -d /var/lib/postgresql/data && echo postgres-data-ok'
docker compose exec -T postgres sh -c 'test -d /backups && echo backups-ok'
docker compose exec -T api sh -c 'test -d /app/data && test -d /app/logs && echo app-mounts-ok'
git status --short --ignored .env .env.airflow .local data logs result
```

결과:

- `docker compose config --quiet` PASS.
- `postgres` / `api` 재생성 후 healthy 상태 확인.
- `postgres` data mount 확인: `postgres-data-ok`.
- `postgres` backup mount 확인: `backups-ok`.
- `api` data/log mount 확인: `app-mounts-ok`.
- `.env`, `.env.airflow`, `.local`, `data`, `logs`, `result`는 ignored 상태 유지.
- `.env.example`에는 `CHANGE_ME` / `DEMO_KEY` placeholder만 존재하며 실제 secret 값은 포함하지 않는다.

주의:

- `docker compose down -v`는 사용하지 않았다.
- `docker compose up -d postgres api`로 service recreate가 발생했다.
