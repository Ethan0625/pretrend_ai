# Run Log

Markers: operation
Status: active

## 목적

로컬 운영/검증 중 발생한 재현성 이슈와 조치 내역을 짧게 기록한다. Secret 값, 개인 토큰, 실제 API key, private path는 기록하지 않는다.

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
