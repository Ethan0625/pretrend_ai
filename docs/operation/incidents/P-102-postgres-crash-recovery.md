Markers: operation
Status: active

# P-102 — Postgres Crash Recovery 동안 API Health와 Serving Readiness 불일치

## 1. 요약

- ID: `P-102`
- 날짜: 2026-05-27
- 영역: Postgres / API
- 심각도: High
- 상태: Monitoring
- 관련 커밋: P32 runtime hardening work
- 관련 테스트: API smoke, `/api/v1/meta` freshness check
- 관련 계약 문서:
  - `docs/operation/RUN_LOG.md`
  - `docs/operation_guide.md`
  - `docs/operation/reproducible_runtime_contract.md`

---

## 2. 깨진 계약

Serving runtime은 API process health와 DB-backed serving readiness를 구분해서 판단해야 한다.

```text
/health == process alive
/api/v1/meta == DB-backed serving surface ready
```

---

## 3. 증상

Docker Desktop/WSL 재시작 후 `api`와 `web`은 healthy였지만 `postgres`는 `running (unhealthy)` 상태였다.

API `/health`는 200을 반환했지만 `/api/v1/meta` 같은 DB 의존 endpoint는 500 또는 timeout을 반환했다.

Postgres 로그에는 아래 패턴이 나타났다.

```text
PANIC: could not fdatasync file ...: I/O error
database system was interrupted
syncing data directory (pre-fsync)
FATAL: the database system is starting up
```

---

## 4. 기대 동작

DB-backed API 정상 여부는 `/health`만으로 판단하지 않고 `/api/v1/meta` freshness까지 확인해야 한다.

---

## 5. 근본 원인

- 코드 경로: API healthcheck는 process 생존만 확인
- 데이터 경로: Postgres data directory crash recovery
- 문서/계약 경로: recovery 중 health와 readiness 차이를 설명하는 runbook 부재
- 누락된 검증: `/health`와 `/api/v1/meta`를 구분한 운영 점검 절차 부족
- 잘못된 가정: `api healthy`면 DB-backed endpoint도 정상이라고 가정

---

## 6. 수정

- Docker Desktop을 재시작하고 Postgres crash recovery 완료를 대기했다.
- `docker compose ps postgres`와 `docker compose logs --tail=120 postgres`로 recovery 상태를 확인했다.
- `postgres`가 healthy로 돌아온 뒤 `/api/v1/meta`를 재확인했다.
- 운영 가이드에 `/health`와 `/api/v1/meta`의 의미 차이를 기록했다.

---

## 7. 검증

- `pretrend-postgres`가 `running (healthy)`로 복귀
- API 재시작 없이 DB 의존 endpoint 정상 응답
- `/api/v1/meta` freshness 확인
- 이후 `2026-05-21`부터 `2026-05-26`까지 증분 backfill 수행

---

## 8. 예방 / 가드

- `RUN_LOG`에 crash recovery 판단 절차 기록
- `operation_guide`에 DB-backed endpoint 500 troubleshooting 추가
- `docker compose down -v` 금지 원칙 재강조
- 10분 이상 recovery가 끝나지 않거나 `pg_control`/`I/O error`가 반복되면 data directory 보존 후 dump restore로 전환

---

## 9. 남은 부채

- underlying host filesystem 또는 Docker Desktop/WSL I/O 문제가 재발할 수 있어 `Monitoring`으로 둔다.
- API `/health`를 DB readiness까지 포함하는 deep health로 확장할지는 별도 task에서 판단한다.

---

## 10. 메모

이번 케이스에서 API 재시작은 필요하지 않았다. Postgres recovery 완료 후 기존 API connection path가 정상화됐다.
