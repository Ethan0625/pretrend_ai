# P30 — Reproducible Runtime & Data Bootstrap

## 0. 문서 메타

- Parent Task ID: `P30`
- Title: `Reproducible Runtime & Data Bootstrap`
- Status: `DONE`
- Phase: `P30 — Phase 3 Preflight`
- Source(anchor): `.agent/task/P30_parent_reproducible_runtime.md`
- Last Updated: `2026-05-15`
- Owner: `Codex`

---

## 1. 목표

- 현재 문제: 프로젝트 실행/검증/복구 절차가 현재 Linux 데스크탑, repo-local volume, 수동 운영 지식에 묶여 있다.
- 상위 목표: 신규 clone, OS별 Docker 명령, Postgres volume path, DB dump/restore, dev/test image, 문서 공개 범위를 하나의 재현성 계약으로 고정한다.
- 기대 효과: Phase 3 dashboard 진입 전 runtime drift, secret leakage, 데이터 손실, 문서 혼선을 줄인다.

---

## 2. Why now

- 왜 지금 필요한가: P29가 Phase 2 stage gate를 완료했고, Phase 3 dashboard 전에는 runtime/backup/docs 재현성이 먼저 고정되어야 한다.
- 선행 조건: P29 완료분 commit/push 완료 (`dbbf98d`).
- 미루면 생기는 문제:
  - 다른 OS나 신규 머신에서 dev/test/API가 재현되지 않는다.
  - Postgres volume 위치가 로컬 머신에 고정된다.
  - 백업/restore가 검증되지 않아 정전/장비 이동 때 복구 리스크가 커진다.
  - `.agent` 문서 공개 시 secret/local path 노출 위험이 생긴다.

---

## 3. 배경

관련 문서:

- `docs/operation/reproducible_runtime_contract.md`
- `docs/operation_guide.md`
- `docs/environment.md`
- `docs/testing/operational_invariant_test_contract.md`
- `.agent/task/P30_draft_reproducible_runtime_data_bootstrap.md`
- `.agent/WORKFLOW.md`
- `.agent/CHANGE_GATES.md`

현재 운영 상태:

- `docker-compose.yml`은 `postgres`와 `api` 서비스를 가진다.
- Postgres image는 `timescale/timescaledb:2.27.0-pg16`로 고정되어 있다.
- 현재 기본 DB bind mount는 `./.local/postgres-data`다.
- API service는 `Dockerfile.api` 기반이다.
- 현재 `.dockerignore`는 API image 중심이라 `tests/`, `docs/`를 제외한다.

---

## 4. 상위 범위 정의

### 4.1 In-Scope

- Postgres serving DB volume host path 변수화.
- DB backup directory mount 계약.
- project data/log host path 변수화.
- API image와 dev/test image 분리.
- `.dockerignore` / Dockerfile-specific ignore 전략 정리.
- 신규 clone 기준 build/test/smoke/restore 검증.
- DB dump/restore 절차 문서화 및 별도 DB/volume 검증.
- `.agent`, `CLAUDE.md`, `AGENTS.md` 공개 whitelist 기준.
- docs marker 분류 기준.
- README / operation docs / environment docs 정합화.

### 4.2 Out-of-Scope

- Cloud deployment.
- Full Airflow Docker 운영화.
- MinIO/S3 도입.
- LLM server Docker화.
- Broker/live trading 운영화.
- Production scheduling.
- Phase 3 dashboard 기능 구현.
- data lake 전체 Git/Docker image 포함.

### 4.3 수정 금지

- 기존 DB volume 삭제.
- `docker compose down -v` 수행.
- `.env`, `.env.airflow`, real API key/token Git 포함.
- `data/`, `.local/postgres-data`, logs, result 대용량 산출물 Git 포함.
- Observability / Personal Track boundary 회귀.
- 기존 public API contract 임의 변경.

---

## 5. 설계 불변식

- Docker image는 runtime/source/test 환경만 담고 data/secrets/logs를 담지 않는다.
- `PRETREND_POSTGRES_DATA_DIR`에 지정한 host path가 active Postgres volume 위치다.
- `./.local/postgres-data`는 기본값일 뿐 공식 고정 경로가 아니다.
- 운영 복구 1순위는 `pg_dump -Fc` dump restore다.
- restore 검증은 active DB가 아니라 별도 DB/volume에서 수행한다.
- README 공식 절차는 OS별 `docker compose` 원 명령으로 제공한다.
- Makefile은 보조 UX일 수 있으나 유일한 공식 절차가 아니다.
- `.agent` 공개는 whitelist 방식으로만 한다.

---

## 6. 세부 task 분해

| Task ID | 제목 | 상태 | 목적 | Source(anchor) |
| --- | --- | --- | --- | --- |
| `P30-0` | Formalize Runtime Contract | DONE | P30 parent/leaf 구조와 장기 runtime contract 문서 고정 | `.agent/task/P30-0_formalize_runtime_contract.md` |
| `P30-1` | Runtime Volume Contract | DONE | DB/data/log/backup host path env 계약과 compose 문서화 | `.agent/task/P30-1_runtime_volume_contract.md` |
| `P30-2` | Docker Build/Test Runtime | DONE | API image와 dev/test image 분리, ignore 전략 정리 | `.agent/task/P30-2_docker_build_test_runtime.md` |
| `P30-3` | Data Bootstrap & DB Restore Contract | DONE | dump/restore 우선 복구와 backfill fallback 계약 | `.agent/task/P30-3_data_bootstrap_db_restore_contract.md` |
| `P30-4` | Reproducibility Verification | DONE | 신규 clone build/test/smoke/restore/volume/security 검증 | `.agent/task/P30-4_reproducibility_verification.md` |
| `P30-5` | Agent Docs Publication Safety | DONE | `.agent`/CLAUDE/AGENTS 공개 whitelist와 보안 점검 | `.agent/task/P30-5_agent_docs_publication_safety.md` |
| `P30-6` | Docs Marker Classification | DONE | docs marker 기준과 공개/운영/계약 문서 분류 | `.agent/task/P30-6_docs_marker_classification.md` |

실행 순서:

```text
P30-0 -> P30-1 -> P30-2 -> P30-3 -> P30-4 -> P30-5 -> P30-6
```

P30-5와 P30-6은 문서 성격이 강하지만, 공개 범위와 marker 기준이 맞물리므로 P30 본체 안에서 처리한다.

---

## 7. 상위 완료 기준

- [x] `docs/operation/reproducible_runtime_contract.md`가 현재 P30-0~P30-4 구현/문서와 정합하다.
- [x] host DB volume path가 env var로 조정 가능하다.
- [x] 기본값은 기존 `.local/postgres-data` 운영을 깨지 않는다.
- [x] 외장하드/Windows/WSL2/Linux 경로 예시가 문서화되어 있다.
- [x] API image와 dev/test image가 역할별로 분리되어 있다.
- [x] Docker build context에 secrets/data/logs/result가 포함되지 않는다.
- [x] Docker 내부 pytest 또는 지정된 smoke test가 실행 가능하다.
- [x] 신규 clone 기준 README 절차가 검증되어 있다.
- [x] DB dump/restore 절차가 별도 DB/volume에서 검증되어 있다.
- [x] volume mount 확인 절차가 있다.
- [x] 민감 파일 미포함 검증 절차가 있다.
- [x] `.agent` 공개 범위는 whitelist 방식으로 관리된다.
- [x] docs marker 기준이 정의되어 공개/운영/계약 문서 분류에 사용된다.

---

## 8. 검증 기준

Parent 검증은 leaf task 검증 결과의 집합으로 판단한다.

필수 검증 후보:

```bash
docker compose config --quiet
docker compose build
docker compose up -d postgres api
docker compose ps
docker build -t pretrend-dev -f Dockerfile.dev .
docker run --rm pretrend-dev pytest -q --tb=short
```

DB restore 검증은 active DB를 덮어쓰지 않는 별도 DB/volume에서만 수행한다.

---

## 9. 변경 이력

- 2026-05-15: Initial parent task created from P30 draft.
- 2026-05-15: P30-1 completed runtime volume contract and mount checks.
- 2026-05-15: P30-2 completed split API/dev-test Docker runtime and Docker pytest.
- 2026-05-15: P30-3 completed restore-first/backfill-fallback data bootstrap contract and dump catalog validation.
- 2026-05-15: P30-4 completed Docker build/test/smoke, separate-DB restore, volume, sensitive-file, and README procedure verification.
- 2026-05-15: P30-5/P30-6 completed agent docs publication whitelist and docs marker classification. P30 parent DoD complete.
