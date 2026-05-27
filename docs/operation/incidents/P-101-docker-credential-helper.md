Markers: operation
Status: active

# P-101 — Docker Desktop credential helper 실패

## 1. 요약

- ID: `P-101`
- 날짜: 2026-05-20
- 영역: Docker Runtime
- 심각도: Medium
- 상태: Resolved
- 관련 커밋: P31 dashboard Docker runtime work
- 관련 테스트: frontend typecheck/build, Docker web build
- 관련 계약 문서:
  - `docs/operation/RUN_LOG.md`
  - `docs/operation_guide.md`

---

## 2. 깨진 계약

Docker-first dashboard runtime은 public base image를 재현 가능하게 pull/build할 수 있어야 한다.

```text
docker compose --profile web-dev run --rm web-node npm install
docker compose build web
```

---

## 3. 증상

`node:22-alpine`, `nginx:1.27-alpine` public image pull 과정에서 Windows Docker credential helper 오류가 발생했다.

```text
error getting credentials - err: exit status 1
A specified logon session does not exist. It may already have been terminated.
```

---

## 4. 기대 동작

Public image pull은 Docker Hub private credential 없이도 성공해야 한다.

---

## 5. 근본 원인

- 코드 경로: 없음
- 데이터 경로: 없음
- 문서/계약 경로: Docker Desktop credential troubleshooting이 운영 문서에 없었음
- 누락된 검증: Docker Desktop credential helper 실패 시 public pull fallback 절차 부재
- 잘못된 가정: `credsStore: "desktop"`가 모든 Windows 로그인 세션에서 안정적으로 동작한다고 가정

---

## 6. 수정

- `%USERPROFILE%\.docker\config.json`을 백업했다.
- `credsStore: "desktop"`를 제거하고 public image pull을 재시도했다.
- Docker Desktop credential helper 이슈를 `RUN_LOG`와 운영 가이드에 기록했다.

---

## 7. 검증

- `docker pull node:22-alpine` PASS
- `docker pull nginx:1.27-alpine` PASS
- `docker compose --profile web-dev run --rm --no-TTY web-node npm run typecheck` PASS
- `docker compose --profile web-dev run --rm --no-TTY web-node npm run build` PASS
- `docker compose build web` PASS
- `pretrend-web` healthy

---

## 8. 예방 / 가드

- `docs/operation/RUN_LOG.md`에 원인과 조치 기록
- `docs/operation_guide.md`에 Docker credential helper troubleshooting 추가
- private image를 쓰는 경우 Docker Desktop sign in 또는 `docker login`을 먼저 수행하도록 메모

---

## 9. 남은 부채

- Docker Desktop 재로그인 시 `credsStore: "desktop"`가 재생성될 수 있다.
- public image만 사용하는 현재 프로젝트 범위에서는 해결 완료로 본다.

---

## 10. 메모

이 이슈는 코드 결함이 아니라 Windows Docker Desktop credential helper 상태와 로컬 로그인 세션의 결합 문제였다.
