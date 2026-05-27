# Run Log

Markers: operation
Status: active

## 목적

로컬 운영/검증 중 발생한 재현성 이슈와 조치 내역을 짧게 기록한다. Secret 값, 개인 토큰, 실제 API key, private path는 기록하지 않는다.

---

## 2026-05-27 — Docker Desktop 재시작 후 Postgres crash recovery 지연

### 상황

Docker Desktop/WSL 연결이 끊긴 뒤 `docker compose ps`가 `//./pipe/docker_engine` 연결 오류를 반환했다. Docker Desktop을 다시 실행한 뒤 Compose 상태는 복구되었지만, `api`와 `web`은 healthy인 반면 `postgres`는 한동안 `running (unhealthy)` 상태였다.

API `/health`는 200을 반환했지만 `/api/v1/meta` 같은 DB 의존 endpoint는 500을 반환했다.

### 원인

이전 정전/중단 이후 Postgres data directory가 crash recovery를 수행하고 있었다. 로그에는 아래 패턴이 나타났다.

```text
PANIC: could not fdatasync file ...: I/O error
database system was interrupted
syncing data directory (pre-fsync)
FATAL: the database system is starting up
```

`api` healthcheck는 프로세스 생존 여부를 확인하므로 DB가 아직 복구 중이어도 healthy로 보일 수 있다. 반면 serving endpoint는 Postgres 연결과 쿼리에 의존하므로 recovery 중에는 500이 날 수 있다.

### 조치

1. Docker Desktop을 완전히 재시작했다.
2. `docker compose ps`로 daemon 연결과 container 상태를 확인했다.
3. `docker compose logs --tail=120 postgres`로 Postgres recovery 로그를 확인했다.
4. `postgres`가 `healthy`로 돌아온 뒤 `/api/v1/meta`를 재확인했다.

### 결과

- `pretrend-postgres`가 `running (healthy)`로 복귀했다.
- API 재시작 없이 DB 의존 endpoint가 정상 응답했다.
- serving freshness 기준 최신 날짜는 `2026-05-20`으로 확인되어, `2026-05-21`부터 최신 완전 거래일까지 증분 backfill이 필요하다.

### 후속 메모

- `docker compose down -v`는 사용하지 않는다. 운영 data volume 삭제 위험이 있다.
- `postgres`가 10분 이상 `unhealthy` 상태를 유지하거나 `pg_control`, `base`, `I/O error` panic이 반복되면 기존 data directory를 보존한 뒤 dump restore + Gold/similarity/cache 재생성으로 전환한다.
- API `/health`가 200이어도 `/api/v1/meta`를 함께 확인해야 serving DB까지 정상이라고 판단할 수 있다.

---

## 2026-05-20 — Docker Desktop credential helper 오류

### 상황

P31 frontend를 Docker-first로 구성하면서 `node:22-alpine`, `nginx:1.27-alpine` public image pull이 필요했다.

`docker compose --profile web-dev run --rm web-node npm install` 실행 시 다음 오류가 발생했다.

```text
error getting credentials - err: exit status 1, out: `A specified logon session does not exist. It may already have been terminated.`
```

### 원인

Windows Docker CLI가 `%USERPROFILE%\.docker\config.json`의 `credsStore: "desktop"` 설정을 통해 Docker Desktop credential helper를 호출했지만, 현재 Windows/Docker Desktop 로그인 세션에서 helper가 정상 응답하지 않았다.

Public image pull 자체가 막힌 것은 아니며, credential helper 호출 단계에서 실패한 것이다.

### 조치

1. `%USERPROFILE%\.docker\config.json`을 백업했다.
   - 백업 파일명 패턴: `config.json.bak-pretrend-YYYYMMDDHHMMSS`

2. `credsStore: "desktop"`를 제거하고 최소 설정으로 변경했다.

```json
{"auths":{}}
```

3. public image를 단독 pull한 뒤 compose 검증을 재시도했다.

```powershell
docker pull node:22-alpine
docker pull nginx:1.27-alpine
docker compose --profile web-dev run --rm --no-TTY web-node npm run typecheck
docker compose --profile web-dev run --rm --no-TTY web-node npm run build
docker compose build web
docker compose up -d web
```

### 결과

- `node:22-alpine` pull PASS.
- `nginx:1.27-alpine` pull PASS.
- frontend typecheck PASS.
- frontend production build PASS.
- `docker compose build web` PASS.
- `pretrend-web` container healthy.
- `http://localhost:3000/` 200 OK.
- `http://localhost:3000/healthz` `ok`.

### 후속 메모

- 현재 Pretrend Docker runtime은 public image만 사용하므로 `credsStore` 제거로 프로젝트 실행에는 영향이 없다.
- Docker Hub private image를 쓰거나 Docker Hub rate limit 회피가 필요하면 Docker Desktop sign in 또는 `docker login`을 다시 수행해야 한다.
- Docker Desktop에 다시 로그인하면 `credsStore: "desktop"` 설정이 재생성될 수 있다. 같은 오류가 재발하면 `docs/operation_guide.md`의 Docker credential helper 트러블슈팅을 따른다.
