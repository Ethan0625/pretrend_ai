v2026.05.12

# Task Queue — Pretrend AI Observability Track

## 🔔 2026Q2 방향 재정의 — Observability Track 신설

**핵심 결정 (2026-05-12)**:
- 본 프로젝트는 **Market Structure Observability Runtime**으로 재정의됨.
- **Two-Track 분리**: Observability Track(메인, 신규 본진) + Personal Track(기존 자산, 동결 + 운영 중단).
- **외부 노출 roadmap**: Phase 0~2 로컬, Phase 3 dashboard 로컬 검증 후 별도 운영 task로 외부 노출 등록. AWS는 Phase 4 이후 의제.
- **Commit scope 표준** (`observability` / `infra` / `personal-frozen`): `.agent/WORKFLOW.md §6.2`

**참조 문서**:
- 트랙 분리 원칙: `docs/architecture/track_separation.md`
- 리팩토링 계획: `.agent/REFACTOR_2026Q2.md`
- Workflow 표준: `.agent/WORKFLOW.md`
- Agent 방향: `.agent/DIRECTION.md`
- Cloud migration plan: private Claude planning note (local path excluded from public docs)

**Legacy queue (Pre-2026Q2)**:
- `.agent/task/archive/TASK_QUEUE_pre-2026Q2.md` — P1~P16 history. 참고용.

---

## 큐 운영 기준

- 큐는 `Active Queue`와 `Completed`로 분리한다.
- Active 항목은 `Why now / DoD / Risk / Source(anchor)`를 유지한다.
- Completed 항목은 `결과 / Artifacts / Verification / Source(anchor)`를 기록한다.
- 작업지시 상세는 `.agent/task/` 개별 문서에 분리 보관한다.
- Personal Track 신규 작업 금지 — 큐에 등록 자체를 하지 않는다.

---

## 상태 요약 (2026-05-27)

| 항목 | 상태 | Source(anchor) |
|---|---|---|
| **P17 Observability Phase 0 Foundation** | DONE | `.agent/task/archive/P17/P17_parent_observability_phase0.md` |
| **P18 axis_features 추출 (Phase 1 첫 타깃)** | DONE | `.agent/task/archive/P18/P18_parent_axis_features_extraction.md` |
| **P19 axis_horizon_state 추출 (Phase 1 두 번째 모듈)** | DONE | `.agent/task/archive/P19/P19_parent_axis_horizon_state_extraction.md` |
| **P20 market_position 추출 (Phase 1 세 번째 모듈)** | DONE | `.agent/task/archive/P20/P20_parent_market_position_extraction.md` |
| **P21 group_transition 추출 (Phase 1 네 번째 모듈)** | DONE | `.agent/task/archive/P21/P21_parent_group_transition_extraction.md` |
| **P22 next_step 추출 + report_context_* 사전 추출** | DONE | `.agent/task/archive/P22/P22_parent_next_step_extraction.md` |
| **P23 Personal Track 테스트 archive 분리** | DONE | `.agent/task/archive/P23/P23_parent_personal_tests_archive.md` |
| **P24 Gold layer Postgres schema 도입** | DONE | `.agent/task/archive/P24/P24_parent_gold_postgres_schema.md` |
| **P25 Gold Postgres sync DAG 도입** | DONE | `.agent/task/archive/P25/P25_parent_gold_postgres_sync.md` |
| **P26 observability/similarity/ 모듈** | DONE | `.agent/task/archive/P26/P26_parent_observability_similarity.md` |
| **P27 observability/explainability/ LLM 설명 layer** | DONE | `.agent/task/archive/P27/P27_parent_observability_explainability.md` |
| **P28 Observability FastAPI read-only API** | DONE | `.agent/task/archive/P28/P28_parent_observability_api.md` |
| **P29 Phase 2 Stage Gate** | DONE | `.agent/task/archive/P29/P29_parent_phase2_audit.md` |
| Personal Track 전체 | FROZEN + SERVICE STOPPED | `docs/architecture/track_separation.md §2.2` |
| Infrastructure (Bronze/Silver/Gold, Macro/EOD DAG) | OPERATIONAL | 운영 유지 |
| **Phase 2 stage gate** | DONE | P22~P29 완료 + P29 follow-up hotfix 반영. Phase 3 dashboard 진입 준비 |
| **P30 Reproducible Runtime & Data Bootstrap** | DONE | `.agent/task/archive/P30/P30_parent_reproducible_runtime.md` |
| **P31 Observability Dashboard** | DONE | `.agent/task/archive/P31/P31_parent_observability_dashboard.md` |
| **Phase 3 코드/UI layer** | DONE | P31 — `apps/web/` + 8 screen + 4 chart + docker 통합 |
| **P32 Phase 3 후속작업** | DONE | `.agent/task/archive/P32/P32_parent_phase3_followup.md` |
| **P33 Debug History System** | DONE | `.agent/task/archive/P33/P33_parent_debug_history.md` |
| **P34 Observability Regime Feature Pipeline 독립화** | DONE | `.agent/task/archive/P34/P34_parent_regime_pipeline_independence.md` |
| **P35 Similarity Replay: 유사 구간 이후 궤적 탐색** | DONE | `.agent/task/archive/P35/P35_parent_similarity_replay.md` |
| **P36 Macro 관측 강화 (Overview UI + Reaction 관측)** | TODO | `.agent/task/P36_parent_macro_observability.md` |

---

## Active Queue

### P34 — Observability Regime Feature Pipeline 독립화

**Why now**: `similarity_regime`이 Personal Track frozen 코드(`strategy_job`) 산출물에 의존해 수동 개입 없이는 Gold Macro/EOD와 날짜가 어긋난다. Observability Track 자립 파이프라인의 핵심 선행 조건.

**DoD**:
- [x] Gold DB(`gold_eod_features`, `gold_macro_features`)만 읽어 `gold_market_state_similarity_feature`를 생성하는 Observability-native builder 완성
- [x] `similarity_build_dag`의 `build_market_state_features_task`가 새 경로로 교체됨
- [x] `data/strategy/` 없이 `similarity_regime` 갱신 확인
- [x] 기존 `_from_runtime()` 함수는 deprecated 표기(삭제 아님)
- [x] `pytest --gate fast -q --tb=short` 전체 회귀 없음

**Risk**: axis 모듈 입력 컬럼과 Gold DB 컬럼 불일치 → builder 내부 rename/select로 대응

**Source(anchor)**: `.agent/task/archive/P34/P34_parent_regime_pipeline_independence.md`

| Leaf | 제목 | depends_on | 상태 |
|---|---|---|---|
| P34-1 | Observability-native Regime Feature Builder 신설 | — | DONE |
| P34-2 | runtime_source + DAG 교체 | P34-1 | DONE |

**결과**
- `src/pretrend/observability/regime/regime_feature_builder.py`가 Gold DB 기반으로 market-state/rotation source를 재구성한다.
- `similarity_build_dag`는 `build_market_state_similarity_features_from_db`를 호출한다. 기존 runtime snapshot 경로는 호환용 lazy import 경로로만 유지한다.
- 운영 smoke: Airflow 컨테이너에서 `2026-05-26` 1일 재생성 → `gold_market_state_similarity_feature` 1 row, `similarity_regime` 100 row upsert. 이후 `gold_market_state_similarity_feature`, `similarity_regime`, `similarity_gold` max date 모두 `2026-05-26`.
- 검증: `conda run -n pretrend_pytest pytest --gate fast -q --tb=short` → `537 passed, 27 skipped, 12 deselected`.

---

### P35 — Similarity Replay: 유사 구간 이후 궤적 탐색

**Why now**: P34 완료로 `gold_market_state_similarity_feature` 자립 갱신이 확보되면, replay 기능의 데이터 신뢰도가 뒷받침된다. Similarity 화면이 현재 "Top-N 날짜 목록"에서 끝나 관측 스토리가 얕다는 것이 핵심 동기다.

**DoD**:
- [x] `GET /api/v1/similarity/replay` 엔드포인트 등록됨
- [x] Similarity 페이지에 "유사 구간 궤적" 탭 추가됨
- [x] 이벤트/날짜 anchor별 현재 구간 vs 과거 구간 EOD normalized trajectory 카드 렌더링, 앵커 기준선 표시
- [x] 기존 regime/gold/events 탭 회귀 없음
- [x] `pytest --gate fast -q --tb=short` 전체 회귀 없음, `npm run build` PASS

**Risk**: P34가 완료되어 최신 운영일 기준 replay smoke를 진행할 수 있다. P35에서는 replay window가 지나치게 커져 API 응답이 무거워지는 문제와 기존 `regime/gold/events` 탭 회귀를 우선 관리한다.

**Source(anchor)**: `.agent/task/archive/P35/P35_parent_similarity_replay.md`

| Leaf | 제목 | depends_on | 상태 |
|---|---|---|---|
| P35-1 | Similarity Replay API 엔드포인트 신설 | — | DONE |
| P35-2 | Similarity Replay 대시보드 UI | P35-1 | DONE |

**결과**
- `GET /api/v1/similarity/replay`가 `events/regime/gold` anchor 기준의 현재 구간 vs 과거 구간 EOD normalized trajectory를 단일 응답으로 반환한다.
- Similarity 화면 마지막 탭으로 "유사 구간 궤적"을 추가하고, `D-60~D` 기준 Top 5 Asset overlay + 선택 Asset 현재/과거 detail chart + Asset Name별 trajectory ranking을 렌더링한다.
- 운영 smoke: web proxy 기준 `2026-05-26` replay `view=events`, `view=regime` 호출 200, `current_path/historical_path/overlay_assets/asset_rankings` payload 반환.
- 검증: `conda run -n pretrend_pytest pytest tests/api/ tests/web/test_p32_dashboard_contract.py tests/web/test_p35_dashboard_contract.py -q --tb=short` → `71 passed`; `conda run -n pretrend_pytest pytest --gate fast -q --tb=short` → `549 passed, 27 skipped, 12 deselected`; `docker compose --profile web-dev run --rm web-node sh -lc "npm run build"` → PASS; `docker compose up -d --build api web` → PASS.

---

### P36 — Macro 관측 강화 (Overview UI + Reaction 관측)

**Why now**: P35 완료로 similarity replay가 추가됐다. Macro 화면은 Phase 3(P31/P32) 이후 개선되지 않아 단일 지표 조회 수준에 머물러 있다. `gold_eod_features`가 전체 ETF universe를 보유하고 있어 reaction 계산의 데이터 근거가 충분하다.

**DoD**:
- [ ] Macro 화면에 5개 고정 지표 overview 카드 그리드 표시
- [ ] 각 카드에 `selected_value`, `selected_release_date`, `delta_3m`, `zscore_12m`, `regime` 배지 표시
- [ ] `GET /api/v1/macro/reaction` 엔드포인트 등록됨
- [ ] 지표 선택 → "ETF 반응" 탭 → Top 5 순위 테이블 + normalized overlay 차트
- [ ] 예측 표현 없음 — 관측 표현만
- [ ] `pytest -q --tb=short` 전체 회귀 없음, `npm run build` PASS

**Risk**: P36-1/P36-2 병렬 실행 가능. P36-3는 두 task 완료 후 진행. `Macro.tsx` 파일이 P36-1 → P36-3 순차 수정 대상 — 동시 수정 금지.

**Source(anchor)**: `.agent/task/P36_parent_macro_observability.md`

| Leaf | 제목 | depends_on | 상태 |
|---|---|---|---|
| P36-1 | Macro Overview UI 개선 | — | TODO |
| P36-2 | Macro Reaction API 신설 | — | TODO |
| P36-3 | Macro Reaction 대시보드 UI | P36-1, P36-2 | TODO |

---

Backlog:
- P29 hotfix backlog (모두 resolved):
  - `hotfix-P29-1.A` DONE — Observability boundary cleanup, `tests/observability/test_boundary_imports.py` 추가.
  - `hotfix-P29-1.B` DONE — Strategy shim package-level exports 보호.
  - `hotfix-P29-2.A` DONE — project Airflow metadata에서 3개 Personal DAG paused 확인.
  - `follow-up-P29-1.C` DONE — `docs/testing/operational_invariant_test_contract.md §8` AST-based allowlist-aware 기준 반영 (2026-05-27).
  - `follow-up-P29-2.B` DONE — `docs/operation_guide.md` "Project Airflow CLI guard" 섹션에 project env command 추가됨 (P29 follow-up 시 완료).
- `frontend_decisions.md` → `frontend_contract.md` 승격 재평가: P31 로컬 E2E PASS, `tokens.css` 운영 1주 안정화 조건 충족 시(2026-05-28~) 승격. 승격 작업: `git mv` + Status 변경 + §1·§5 압축.
- Similarity Replay follow-up: API는 `compare_days`, `forward_days`, `top_assets`를 지원한다. 대시보드에서 사용자가 window/기간을 직접 조정하는 control은 후속 후보로 유지한다. 설계 기준은 `docs/architecture/similarity_design.md §10.2`에 기록됨.
- 외부 노출 운영 등록: Phase 3 dashboard 로컬 검증 완료 후 trigger됨. 실제 진행은 도메인/계정/토큰 결정 이후 별도 task.
- Phase 4+ 후보: ETF heatmap(Visx 검토), window-aware explainability, 외부 사용자 auth/onboarding.

---

## Completed (2026Q2~)

> Personal Track 자산의 Completed Log는 `.agent/task/archive/TASK_QUEUE_pre-2026Q2.md` 참조.

### P33 — Debug History System (문서 + Dashboard 탭)

**Why now**: P31/P32 완료 후 포트폴리오 보강 단계. 운영 incident를 `Contract → Prevention` 구조로 추적하는 체계 신설 + 대시보드 탭 추가.

**결과**: Debug History 문서 체계와 dashboard 탐색 탭을 추가했다. RUN_LOG와 이번 운영 검증에서 확인한 실제 이슈를 P-101~P-104 incident로 승격하고, P-001은 작성 예시로만 유지했다.

**Artifacts**:
- `docs/operation/debug_history.md`
- `docs/operation/incident_template.md`
- `docs/operation/incidents/P-001-example.md`
- `docs/operation/incidents/P-101-docker-credential-helper.md`
- `docs/operation/incidents/P-102-postgres-crash-recovery.md`
- `docs/operation/incidents/P-103-eod-silver-window-scan.md`
- `docs/operation/incidents/P-104-regime-snapshot-dependency.md`
- `docs/assets/screenshots/README.md`
- `apps/web/src/data/incidents.ts`
- `apps/web/src/pages/DebugHistory.tsx`
- `apps/web/src/router.tsx`, `apps/web/src/components/Sidebar.tsx`, `apps/web/src/types/screen.ts`
- `.gitignore` (`apps/web/src/data/` 추적 예외)

**Verification**:
- `docker compose --profile web-dev run --rm web-node sh -lc "npm run build"` PASS.
- `/debug-history` route, Sidebar nav, Incident Index table mirror 확인.
- `docs/README.md`에서 `debug_history.md` 링크 접근 가능.

**Risk**: P33-2 Sidebar nav 수정 시 기존 항목 깨질 가능성 → 마지막에만 추가

**Source(anchor)**: `.agent/task/archive/P33/P33_parent_debug_history.md`

| Leaf | 제목 | depends_on | 상태 |
|---|---|---|---|
| P33-1 | Debug History 문서 체계 생성 | — | DONE |
| P33-2 | Dashboard 디버그 히스토리 탭 | — | DONE |

---

### P32 — Phase 3 후속작업 (시계열 API / 404 개선 / 역사 이벤트 유사시기)

- **결과**: P31 대시보드 follow-up을 완료했다. Regime timeline placeholder를 실제 `gold_market_state_similarity_feature` 시계열 API로 교체하고, explainability cache 404에 생성 상태 맥락을 추가했으며, 역사 이벤트 기준 regime similarity를 backend/frontend에 연결했다.
- **Artifacts**:
  - `src/pretrend/api/routers/regime.py`
  - `src/pretrend/api/routers/explain.py`
  - `src/pretrend/api/routers/similarity.py`
  - `src/pretrend/api/schemas.py`
  - `src/pretrend/observability/similarity/events.py`
  - `src/pretrend/observability/explainability/event_similarity_explainer.py`
  - `src/pretrend/ops/rebuild_explainability_cache.py`
  - `migrations/versions/0005_similarity_events_explainability.py`
  - `apps/web/src/api/types.ts`, `apps/web/src/api/hooks.ts`
  - `apps/web/src/charts/RegimeTimeline.tsx`
  - `apps/web/src/pages/Regime.tsx`, `apps/web/src/pages/Similarity.tsx`, `apps/web/src/pages/Macro.tsx`, `apps/web/src/pages/Explain.tsx`, `apps/web/src/pages/_shared.tsx`
  - `apps/web/src/components/Toolbar.tsx`
  - `tests/api/test_regime_timeline.py`, `tests/api/test_similarity_events.py`, `tests/observability/explainability/test_event_similarity_explainer.py`, `tests/web/test_p32_dashboard_contract.py`
- **Verification**:
  - `docker compose --profile web-dev run --rm web-node sh -lc "npm run build"` PASS.
  - `docker compose build web` PASS.
  - `conda run -n pretrend_pytest pytest tests/models/test_explainability_cache_model.py tests/api/test_explain.py tests/api/test_similarity_events.py tests/ops/test_rebuild_explainability_cache.py tests/web/test_p32_dashboard_contract.py -q --tb=short` → `26 passed`.
  - `conda run -n pretrend_pytest pytest tests/observability/explainability/test_event_similarity_explainer.py tests/dags/test_explainability_build_dag.py -q --tb=short` → `10 passed, 2 skipped`.
  - `conda run -n pretrend_pytest pytest -q --tb=short` → `530 passed, 39 skipped, 2 warnings`.
  - 운영 DB 복구 후 `/api/v1/meta` 확인: `gold_macro_features=30,204`, `gold_eod_features=212,159`, `similarity_regime=577,066`, `similarity_gold=572,377`, 모두 max date `2026-05-20`.
  - Alembic `0005` 적용 후 `api_vscode_codex`로 `explainability_cache` 기간 row 재생성: `similarity_events`, `regime`, `macro` 포함, 2026-05-13~2026-05-20 관측일 6개.
- **Follow-up Fixes During Gate**:
  - DB write/truncate pytest가 운영 `.env`의 `pretrend_obs`를 참조하지 않도록 `isolated_test_engine()` 기준으로 보정.
  - `tests/ops/test_destructive_db_test_safety.py`를 추가해 destructive DB test가 격리 DB helper 없이 추가되면 실패하도록 고정.
  - `src/pretrend/ops/rebuild_explainability_cache.py`를 추가해 cache 소실 시 `api_vscode_codex` 기준으로 단일 날짜 또는 기간 재생성이 가능하게 구성.
  - Dashboard의 유사도 설명을 기존 날짜 Top-N 설명이 아니라 `similarity_events` 역사 이벤트 유사시기 설명으로 교체.
  - Windows에서 text bronze partition overwrite가 실패하지 않도록 `Path.replace()` 기반으로 보정.
  - Windows pytest에서 VSCode Codex health check fixture가 실행 가능한 `.cmd`를 사용하도록 보정.
- **Source(anchor)**: `.agent/task/archive/P32/P32_parent_phase3_followup.md`

### P31 — Observability Dashboard (apps/web/ + 8 screen + Recharts)

- **결과**: Phase 3 코드/UI layer를 완료했다. `apps/web/` dashboard, read-only API consumer, 한국어 UI, 8 screen, Recharts chart, Docker web runtime을 하나의 로컬 운영 표면으로 묶었다.
- **Artifacts**:
  - `apps/web/`
  - `docker/Dockerfile.web`, `docker/nginx.conf`, `docker/Dockerfile.web.dockerignore`
  - `docker-compose.yml` (`web`, `web-node`)
  - `.env.example`
  - `docs/architecture/frontend_decisions.md`
  - `docs/architecture/observability_layout.md`
  - `docs/changelog.md`
- **Verification**:
  - `docker compose --profile web-dev run --rm web-node sh -lc "npm run build"` PASS.
  - `docker compose build web` PASS.
  - `docker compose up -d web` PASS; `pretrend-web` healthy.
  - `GET /` served SPA HTML at `localhost:3000`.
  - `GET /api/v1/meta` through nginx same-origin proxy PASS.
  - 금지 prefix grep for updated web chart/page scope 0.
  - `frontend_decisions.md` contract 승격은 운영 1주 안정화 조건 미충족으로 보류.
- **Source(anchor)**: `.agent/task/archive/P31/P31_parent_observability_dashboard.md`

### P30 — Reproducible Runtime & Data Bootstrap

- **결과**: Phase 3 dashboard 진입 전 runtime 재현성 계약을 완료했다. Docker volume path, API/dev-test image 분리, restore-first/backfill-fallback, 신규 clone 검증, agent docs publication whitelist, docs marker classification을 고정했다.
- **Artifacts**:
  - `docker-compose.yml`
  - `.dockerignore`, `Dockerfile.api.dockerignore`, `Dockerfile.dev.dockerignore`
  - `Dockerfile.dev`
  - `.env.example`
  - `README.md`
  - `docs/operation/reproducible_runtime_contract.md`
  - `docs/testing/operational_invariant_test_contract.md`
  - `docs/README.md`
  - `.agent/README.md`
  - `AGENTS.md`, `CLAUDE.md`
  - `tests/ops/test_reproducible_runtime_contract.py`
- **Verification**:
  - `docker compose config --quiet` PASS.
  - `docker compose build` PASS.
  - `docker compose up -d postgres api` PASS; both services healthy.
  - `docker build -t pretrend-api-test -f Dockerfile.api .` PASS.
  - `docker build -t pretrend-dev -f Dockerfile.dev .` PASS.
  - `docker run --rm pretrend-dev pytest -q --tb=short` → `438 passed, 32 skipped`.
  - Separate DB restore check PASS and cleanup confirmed.
  - Volume mount / sensitive-file image checks PASS.
  - Agent public whitelist status PASS; excluded `.agent` files remain ignored.
  - Docs marker/status inventory PASS.
- **Source(anchor)**: `.agent/task/archive/P30/P30_parent_reproducible_runtime.md`

### P29 — Phase 2 Stage Gate (정합 검증 + 문서 정비 + 신규 architecture docs)

- **결과**: Phase 2 stage gate 종료. 코드/운영/문서 3-way 정합 검증, 신규 architecture 문서 5개, system overview entry point 재작성, pytest marker 분류, Phase 3/Cloudflare 진입 checklist를 완료했다. P29 findings는 follow-up hotfix로 보완했다.
- **Artifacts**:
  - `docs/architecture/system_map_2026q2.md`
  - `docs/architecture/runtime_flow.md`
  - `docs/architecture/boundary_contract.md`
  - `docs/api/observability_api_contract.md`
  - `docs/testing/operational_invariant_test_contract.md`
  - `docs/system_overview.md`
  - `docs/legacy/personal_track_overview.md`
  - `docs/operation_guide.md`
  - `docs/changelog.md`
  - `pyproject.toml`, `conftest.py`
- **Verification**:
  - P29-1 code audit: Alembic live `0004 (head)`, shadow DB 가역성 PASS, 6 serving model/migration/feature schema 정합 PASS.
  - P29-1 finding: broader Observability boundary FAIL (`pretrend.pipeline.backtest` / `strategy_engine` 의존) → `hotfix-P29-1.A`.
  - P29-2 operations audit: docker compose `api`/`postgres` healthy, 6 serving table row/watermark 확인, 11 logical endpoint smoke PASS, 멱등 재실행 PASS.
  - P29-3/P29-4 docs/markers: 5 신규 architecture 문서, entry point, legacy 이동, marker 6종 PASS.
  - active pytest / archive personal pytest PASS.
- **Follow-up Hotfix**:
  - Runtime Observability forbidden Personal imports removed and protected by `tests/observability/test_boundary_imports.py`.
  - Strategy shim package-level exports protected by `tests/observability/regime/test_strategy_shim_exports.py`.
  - `strategy_engine_dag`, `paper_trading_dag`, `broker_mock_trading_dag` paused in project Airflow metadata.
  - Airflow project-env guard and forbidden-term allowlist guidance documented.
- **Source(anchor)**: `.agent/task/archive/P29/P29_parent_phase2_audit.md`

### P17 — Observability Phase 0 (Foundation Setup)

- **결과**: Observability Track Phase 0 기반 구축 완료
- **Artifacts**:
  - `docker-compose.yml`, `.env.example`, `.gitignore`
  - `src/pretrend/config.py`
  - `src/pretrend/models/`
  - `alembic.ini`, `migrations/`
  - `docs/architecture/observability_layout.md`
- **Verification**:
  - `docker compose up -d postgres` PASS
  - `timescaledb` extension 확인 PASS
  - `alembic upgrade head` / `downgrade base` / 재-upgrade PASS
  - `conda run -n pytest-pretrend pytest -q --tb=short` → `833 passed, 6 skipped, 11 warnings`
- **Source(anchor)**: `.agent/task/archive/P17/P17_parent_observability_phase0.md`

### P18 — axis_features 추출 (Phase 1 첫 타깃)

- **결과**: `axis_features` 5개 파일을 `src/pretrend/observability/regime/axis/`로 이전하고 기존 `src/pretrend/pipeline/strategy_engine/axis_features/`는 re-export shim으로 변환. 테스트는 `tests/observability/regime/axis/test_axis_features.py`로 이전.
- **Artifacts**:
  - `src/pretrend/observability/regime/axis/`
  - `src/pretrend/pipeline/strategy_engine/axis_features/` shim
  - `tests/observability/regime/axis/test_axis_features.py`
  - `docs/architecture/observability_layout.md`
  - `docs/architecture/axis_horizon_dependency_contract.md`
  - `docs/changelog.md`
  - `.agent/REFACTOR_2026Q2.md`
- **Verification**:
  - 신규 import path PASS
  - 기존 import path shim PASS
  - `conda run -n pytest-pretrend pytest tests/observability/regime/axis/test_axis_features.py -v` → `23 passed`
  - `conda run -n pytest-pretrend pytest tests/pipeline/strategy_engine/test_axis_horizon_state.py -v` → `8 passed`
  - `conda run -n pytest-pretrend pytest -q --tb=short` → `833 passed, 6 skipped, 11 warnings`
  - Personal Track 동결 영역 코드 변경 0
- **Source(anchor)**: `.agent/task/archive/P18/P18_parent_axis_features_extraction.md`

### P19 — axis_horizon_state 추출 (Phase 1 두 번째 모듈)

- **결과**: `axis_horizon_state` 5개 파일을 `src/pretrend/observability/regime/horizon/`으로 이전하고 기존 `src/pretrend/pipeline/strategy_engine/axis_horizon_state/`는 re-export shim으로 변환. 테스트 4개는 `tests/observability/regime/horizon/`으로 이전.
- **Artifacts**:
  - `src/pretrend/observability/regime/horizon/`
  - `src/pretrend/pipeline/strategy_engine/axis_horizon_state/` shim
  - `tests/observability/regime/horizon/`
  - `docs/architecture/observability_layout.md`
  - `docs/architecture/axis_horizon_dependency_contract.md`
  - `docs/architecture/market_structure_{long,mid,short,composer}_contract.md`
  - `docs/changelog.md`
  - `.agent/REFACTOR_2026Q2.md`
- **Verification**:
  - 신규 import path PASS
  - 기존 import path shim PASS
  - `conda run -n pytest-pretrend pytest tests/observability/regime/horizon/ -v` → `67 passed`
  - `conda run -n pytest-pretrend pytest tests/pipeline/strategy_engine/test_composer.py tests/pipeline/strategy_engine/test_strategy_job.py -v` → `23 passed`
  - `conda run -n pytest-pretrend pytest -q --tb=short` → `833 passed, 6 skipped, 11 warnings`
  - Personal Track 동결 영역 코드 변경 0
- **Source(anchor)**: `.agent/task/archive/P19/P19_parent_axis_horizon_state_extraction.md`

### P20 — market_position 추출 (Phase 1 세 번째 모듈)

- **결과**: `market_position` 2개 파일을 `src/pretrend/observability/regime/position/`으로 이전하고 기존 `src/pretrend/pipeline/strategy_engine/market_position/`는 re-export shim으로 변환. 별도 market_position 테스트 파일은 없어 테스트 이전 leaf는 생략.
- **Artifacts**:
  - `src/pretrend/observability/regime/position/`
  - `src/pretrend/pipeline/strategy_engine/market_position/` shim
  - `docs/architecture/observability_layout.md`
  - `docs/architecture/market_structure_composer_contract.md`
  - `docs/changelog.md`
  - `.agent/REFACTOR_2026Q2.md`
- **Verification**:
  - 신규 import path PASS
  - 기존 import path shim PASS
  - `conda run -n pytest-pretrend pytest tests/pipeline/strategy_engine/test_composer.py tests/pipeline/strategy_engine/test_strategy_engine_dag_report.py tests/pipeline/strategy_engine/test_strategy_job.py -v` → `70 passed`
  - `conda run -n pytest-pretrend pytest -q --tb=short` → `833 passed, 6 skipped, 11 warnings`
  - Personal Track 동결 영역 코드 변경 0
- **Source(anchor)**: `.agent/task/archive/P20/P20_parent_market_position_extraction.md`

### P21 — group_transition 추출 (Phase 1 네 번째 모듈)

- **결과**: `group_transition` 5개 파일을 `src/pretrend/observability/regime/rotation/`으로 이전하고 기존 `src/pretrend/pipeline/strategy_engine/group_transition/`는 re-export shim으로 변환. 테스트는 `tests/observability/regime/rotation/test_group_transition_engine.py`로 이전.
- **Artifacts**:
  - `src/pretrend/observability/regime/rotation/`
  - `src/pretrend/pipeline/strategy_engine/group_transition/` shim
  - `tests/observability/regime/rotation/test_group_transition_engine.py`
  - `docs/architecture/observability_layout.md`
  - `docs/architecture/group_transition_signal_contract.md`
  - `docs/changelog.md`
  - `.agent/REFACTOR_2026Q2.md`
- **Verification**:
  - 신규 import path PASS
  - 기존 import path shim PASS
  - `conda run -n pytest-pretrend pytest tests/observability/regime/rotation/test_group_transition_engine.py -v` → `4 passed`
  - `conda run -n pytest-pretrend pytest tests/pipeline/backtest/test_runner_v31.py tests/pipeline/paper/test_execution_soft_gate.py tests/pipeline/strategy_engine/test_strategy_engine_dag_report.py tests/pipeline/strategy_engine/test_strategy_job.py -v` → `86 passed`
  - `conda run -n pytest-pretrend pytest -q --tb=short` → `833 passed, 6 skipped, 11 warnings`
  - Personal Track 동결 영역 코드 변경 0
- **Source(anchor)**: `.agent/task/archive/P21/P21_parent_group_transition_extraction.md`

### P22 — next_step 추출 + report_context_* 사전 추출 (Phase 1 마지막 모듈 / Phase 3 선행)

- **결과**: `next_step` 5개 파일을 `src/pretrend/observability/regime/transition/`으로 이전하고 기존 `src/pretrend/pipeline/strategy_engine/next_step/`는 re-export shim으로 변환. `next_step` boundary 해소를 위해 `report_context_*`와 실제 직접 의존인 `report_analyzer.py`를 `src/pretrend/observability/explainability/`로 사전 추출하고 기존 위치는 shim으로 유지.
- **Artifacts**:
  - `src/pretrend/observability/regime/transition/`
  - `src/pretrend/observability/explainability/`
  - `src/pretrend/pipeline/strategy_engine/next_step/` shim
  - `src/pretrend/pipeline/strategy_engine/report_context*.py`, `report_analyzer.py` shim
  - `tests/observability/regime/transition/`
  - `tests/observability/explainability/test_report_analyzer.py`
  - `docs/architecture/observability_layout.md`
  - `docs/architecture/next_step_signal_contract.md`
  - `docs/architecture/text_strategy_connection_contract.md`
  - `docs/architecture/track_separation.md`
  - `docs/changelog.md`
  - `.agent/REFACTOR_2026Q2.md`
- **Verification**:
  - 신규 import path PASS
  - 기존 import path shim PASS
  - Observability → `pretrend.pipeline.strategy_engine` import 0줄
  - `conda run -n pytest-pretrend pytest tests/observability/regime/transition/ tests/observability/explainability/ -v` → `26 passed`
  - `conda run -n pytest-pretrend pytest tests/pipeline/backtest/test_runner_v31.py tests/pipeline/paper/test_execution_soft_gate.py tests/pipeline/strategy_engine/test_strategy_engine_dag_report.py tests/pipeline/strategy_engine/test_strategy_job.py -v` → `86 passed`
  - `conda run -n pytest-pretrend pytest -q --tb=short` → `833 passed, 6 skipped, 11 warnings`
- **Source(anchor)**: `.agent/task/archive/P22/P22_parent_next_step_extraction.md`

### P23 — Personal Track 테스트 archive 분리

- **결과**: Personal Track frozen 테스트를 `tests/archive/personal/`로 이동하고, `pyproject.toml`에서 `tests/archive/`를 기본 pytest 수집에서 제외. `tests/test_bot/`도 Personal Track 운영 중단 범위로 보고 archive에 포함.
- **Artifacts**:
  - `tests/archive/README.md`
  - `tests/archive/personal/`
  - `pyproject.toml`
  - `tests/test_smoke.py`
  - `tests/observability/regime/position/test_market_position_smoke.py`
  - `tests/observability/explainability/test_context_smoke.py`
  - `docs/architecture/track_separation.md`
  - `docs/changelog.md`
- **Verification**:
  - default collect-only → `318 tests collected`
  - active default pytest → `315 passed, 3 skipped, 11 warnings`
  - archive manual pytest → `521 passed, 3 skipped`
  - 합산 → `836 passed, 6 skipped`
- **Source(anchor)**: `.agent/task/archive/P23/P23_parent_personal_tests_archive.md`

### P24 — Gold layer Postgres schema 도입

- **결과**: Parquet Gold SOT를 유지한 채 조회용 Postgres + TimescaleDB mirror schema를 도입. `gold_macro_features`, `gold_eod_features` 두 테이블 명세/모델/migration을 추가하고 Alembic upgrade/downgrade/re-upgrade 가역성을 검증.
- **Artifacts**:
  - `docs/architecture/gold_postgres_schema.md`
  - `src/pretrend/models/gold_macro.py`
  - `src/pretrend/models/gold_eod.py`
  - `migrations/versions/0002_gold_schema.py`
  - `tests/models/test_gold_macro_model.py`
  - `tests/models/test_gold_eod_model.py`
  - `tests/test_models_base.py`
  - `docs/architecture/observability_layout.md`
  - `docs/changelog.md`
- **Verification**:
  - P24-1 column grep: macro 13개 / EOD 35개 누락 0
  - `conda run -n pytest-pretrend pytest tests/models/ tests/test_models_base.py -v` → `13 passed`
  - `docker compose up -d postgres` PASS
  - `conda run -n pytest-pretrend alembic upgrade head` PASS
  - `conda run -n pytest-pretrend alembic downgrade 0001` PASS
  - `conda run -n pytest-pretrend alembic upgrade head` PASS
  - `conda run -n pytest-pretrend alembic current` → `0002 (head)`
  - `timescaledb_information.hypertables` → `gold_macro_features`, `gold_eod_features`
  - `conda run -n pytest-pretrend pytest -q --tb=short` → `324 passed, 3 skipped, 11 warnings`
  - `conda run -n pytest-pretrend pytest tests/archive/personal/ -q --tb=short` → `521 passed, 3 skipped`
- **Source(anchor)**: `.agent/task/archive/P24/P24_parent_gold_postgres_schema.md`

### P25 — Gold Postgres sync DAG 도입

- **결과**: Gold Parquet SOT를 Postgres mirror로 적재하는 sync 정책/runner/DAG를 도입. 워터마크 + lookback + UPSERT로 첫 backfill과 멱등 재실행을 검증.
- **Artifacts**:
  - `docs/architecture/gold_postgres_sync.md`
  - `src/pretrend/pipeline/sync/__init__.py`
  - `src/pretrend/pipeline/sync/gold_postgres.py`
  - `dags/gold_postgres_sync_dag.py`
  - `tests/pipeline/sync/test_gold_postgres.py`
  - `tests/dags/test_gold_postgres_sync_dag.py`
  - `src/pretrend/config.py`
  - `docs/architecture/observability_layout.md`
  - `docs/changelog.md`
- **Verification**:
  - P25-1 keyword/column grep PASS
  - `conda run -n pytest-pretrend pytest tests/pipeline/sync/ tests/dags/test_gold_postgres_sync_dag.py -v` → `14 passed`
  - `conda run -n airflow-pretrend python -c "from dags.gold_postgres_sync_dag import gold_postgres_sync_dag; ..."` → `gold_postgres_sync_dag 0 11 * * * ['sync_eod', 'sync_macro']`
  - `conda run -n airflow-pretrend airflow dags list --subdir dags/gold_postgres_sync_dag.py` → DAG discoverable
  - `conda run -n airflow-pretrend airflow dags test --subdir dags/gold_postgres_sync_dag.py gold_postgres_sync_dag 2026-05-13` → success
  - `conda run -n airflow-pretrend python -c "from pretrend.pipeline.sync.gold_postgres import sync_gold_macro, sync_gold_eod; ..."` first backfill → macro `26101`, EOD `179037`
  - sync 재실행 후 row count 유지: macro `26101`, EOD `179037`
  - duplicate check 0행, macro PIT violation check 0행
  - `conda run -n pytest-pretrend pytest -q --tb=short` → `338 passed, 3 skipped, 11 warnings`
  - `conda run -n pytest-pretrend pytest tests/archive/personal/ -q --tb=short` → `521 passed, 3 skipped`
- **Source(anchor)**: `.agent/task/archive/P25/P25_parent_gold_postgres_sync.md`

### P26 — observability/similarity/ 모듈 (multi-view cosine similarity)

- **결과**: `src/pretrend/observability/similarity/` 모듈과 Postgres similarity schema를 도입하고, regime view / gold view historical similarity Top-N을 사전 계산 가능하게 구성. runtime source와 historical `what_to_hold` backfill까지 연결해 canonical market-state feature table을 실제 데이터로 채움.
- **Artifacts**:
  - `docs/architecture/similarity_design.md`
  - `migrations/versions/0003_similarity_schema.py`
  - `src/pretrend/models/gold_market_state_similarity_feature.py`
  - `src/pretrend/models/similarity_regime.py`
  - `src/pretrend/models/similarity_gold.py`
  - `src/pretrend/observability/similarity/`
  - `dags/similarity_build_dag.py`
  - `tests/models/test_*similarity*.py`
  - `tests/observability/similarity/`
  - `tests/dags/test_similarity_build_dag.py`
- **Verification**:
  - `conda run -n pytest-pretrend alembic current` → `0003 (head)`
  - `gold_market_state_similarity_feature` → `5852 rows`, `2003-11-07 ~ 2026-05-12`
  - `similarity_regime` recent window → `800 rows`, `8 query dates`, bad gap/score 0
  - `what_to_hold` historical backfill → `9493 rows / 655 dates`, 시작일 `2006-02-01`
  - P26-3c idempotency rerun → generated rows 0, written partitions 0, rotation non-null `748 -> 748`
  - `conda run -n pytest-pretrend pytest tests/observability/similarity/ -v` → `12 passed, 7 skipped`
  - `conda run -n pytest-pretrend pytest -q --tb=short` → `363 passed, 19 skipped, 11 warnings`
- **Source(anchor)**: `.agent/task/archive/P26/P26_parent_observability_similarity.md`

### P27 — observability/explainability/ LLM 설명 layer

- **결과**: legacy Telegram report 코드를 `legacy_report/`로 분리하고, similarity / regime / macro 3 use case 설명 report를 Postgres cache에 사전 생성하는 LLM explainability layer를 도입.
- **Artifacts**:
  - `docs/architecture/explainability_design.md`
  - `src/pretrend/observability/explainability/legacy_report/`
  - `src/pretrend/observability/explainability/llm_client.py`
  - `src/pretrend/observability/explainability/{similarity,regime,macro}_explainer.py`
  - `src/pretrend/observability/explainability/cache.py`
  - `src/pretrend/models/explainability_cache.py`
  - `migrations/versions/0004_explainability_cache.py`
  - `dags/explainability_build_dag.py`
  - `tests/observability/explainability/`
  - `tests/dags/test_explainability_build_dag.py`
- **Verification**:
  - P27-0 legacy split regression → `tests/observability/explainability/` 6 passed, `tests/observability/regime/transition/` 21 passed
  - P27-2 Alembic upgrade/downgrade/re-upgrade → `0004 (head)`, `explainability_cache` hypertable/index 확인
  - P27-3 explainability tests → 34 passed with local Postgres, sandbox default 21 passed / 13 skipped
  - P27-4 DAG smoke → 8 passed
  - Mock provider cache integration → `macro=1`, `regime=1`, `similarity_gold=1`, `similarity_regime=1`; rerun row count unchanged
  - `conda run -n pytest-pretrend pytest -q --tb=short` → `391 passed, 32 skipped, 11 warnings`
- **Source(anchor)**: `.agent/task/archive/P27/P27_parent_observability_explainability.md`

### P28 — Observability FastAPI read-only API

- **결과**: `src/pretrend/api/`에 FastAPI read-only API를 도입하고, 11 endpoint / 12 smoke call 기준의 로컬 docker-compose 운영 경로를 구축.
- **Artifacts**:
  - `docs/architecture/api_design.md`
  - `src/pretrend/api/`
  - `tests/api/`
  - `Dockerfile.api`
  - `requirements_api.txt`
  - `.dockerignore`
  - `docker-compose.yml` (`api` 서비스)
  - `docs/operation_guide.md`
  - `docs/architecture/observability_layout.md`
  - `docs/changelog.md`
- **Verification**:
  - API tests → `38 passed`
  - `conda run -n pytest-pretrend pytest -q --tb=short` → `429 passed, 32 skipped, 11 warnings`
  - `conda run -n pytest-pretrend pytest tests/archive/personal/ -q --tb=short` → `521 passed, 3 skipped`
  - `docker compose up -d postgres api` PASS, `api` healthy
  - Postgres image pinned: `timescale/timescaledb:2.27.0-pg16`
  - 컨테이너 내부 12 smoke call PASS: 200 또는 정상 404
  - Swagger UI `/docs` 200
  - API 코드/테스트 금지어 grep 0
- **Source(anchor)**: `.agent/task/archive/P28/P28_parent_observability_api.md`

---

## Personal Track 상태 (참고)

**2026-05-12부터 운영 중단**.

- 코드 동결, 신규 기능 추가 영구 금지
- Telegram bot systemd: disable
- DAG paused:
  - `paper_trading_dag`
  - `broker_mock_trading_dag`
  - `strategy_engine_dag`
- Infrastructure DAG (`macro_pipeline_dag`, `eod_pipeline_dag`)는 운영 유지

**Personal Track 영역에 commit 발생 시**:
- `personal-frozen` scope 필수 (`fix(personal-frozen): ...`)
- 신규 기능 추가 0 — 버그 수정 / 호환성 패치만
- 강화 review: `.agent/WORKFLOW.md §6.4`

상세: `docs/architecture/track_separation.md §2.2`

---

## 다음 단계

1. Cloudflare Tunnel 운영 등록 task를 도메인/계정/토큰 준비 후 시작한다.
2. `frontend_decisions.md` → `frontend_contract.md` 승격은 P31 운영 1주 안정화 후 재평가한다.

P21은 외부 strategy_engine 의존이 없어 P18 axis_features 패턴으로 완료했다. 디렉토리 명은 `rotation`으로 확정했다.

P22는 옵션 D 결정에 따라 `next_step` 5개 파일뿐 아니라 `report_context_*`와 실제 직접 의존인 `report_analyzer.py`를 함께 다뤘다. Phase 3 전체 완료가 아니라 report 구현 사전 추출 범위다.
