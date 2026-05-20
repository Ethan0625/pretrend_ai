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

## 상태 요약 (2026-05-15)

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
| **P30 Reproducible Runtime & Data Bootstrap** | DONE | `.agent/task/P30_parent_reproducible_runtime.md` |

---

## Active Queue

No active leaf task is registered. Phase 3 사전 결정 완료 (`docs/architecture/frontend_decisions.md`, 2026-05-19). 다음 진입은 Phase 3 dashboard parent + leaf task 작성.

Backlog:
- P29 hotfix backlog: resolved after P29.
  - `hotfix-P29-1.A` Broader Observability boundary cleanup: shared snapshot IO 추출 + historical backfill helper를 runtime Observability 밖으로 이동.
  - `hotfix-P29-1.B` Strategy Engine shim package-level exports: package-level export + contract test 추가.
  - `hotfix-P29-2.A` Personal Track DAG operational state mismatch: project Airflow metadata에서 3개 Personal DAG paused 확인.
  - `follow-up-P29-1.C` Forbidden-prefix grep allowlist: testing contract에 allowlist-aware 기준 반영.
  - `follow-up-P29-2.B` Airflow CLI environment guard: operation guide에 project env command 추가.
- Phase 3 사전 결정 (resolved 2026-05-19): `docs/architecture/frontend_decisions.md` 신설. `apps/web/` + Recharts 기본 + 한국어 UI + single trade_date explainability 확정. 대시보드 검증 후 `frontend_contract.md`로 승격 예정.
- Phase 3 dashboard parent + leaf task 작성: design_sample (`.agent/design_sample/`) + frontend_decisions.md를 reference로, P28 11 endpoint를 consumer로 사용. 예상 leaf 7개 (scaffolding / layout / screens / charts / API client / docker integration / docs).
- 외부 노출 운영 등록: Phase 3 dashboard 로컬 검증 완료 후 trigger. 도메인/계정/토큰 의존.
- Phase 3 후반 결정 (Recharts vs Visx): ETF heatmap / similarity replay 구현 시점에 Recharts 한계 검증 후 Visx 도입 여부 결정.

---

## Completed (2026Q2~)

> Personal Track 자산의 Completed Log는 `.agent/task/archive/TASK_QUEUE_pre-2026Q2.md` 참조.

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
- **Source(anchor)**: `.agent/task/P30_parent_reproducible_runtime.md`

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

1. Phase 3 React dashboard task 후보 검토.
2. 외부 노출 운영 등록은 Phase 3 dashboard 로컬 검증 이후 별도 task로 진행한다.

P21은 외부 strategy_engine 의존이 없어 P18 axis_features 패턴으로 완료했다. 디렉토리 명은 `rotation`으로 확정했다.

P22는 옵션 D 결정에 따라 `next_step` 5개 파일뿐 아니라 `report_context_*`와 실제 직접 의존인 `report_analyzer.py`를 함께 다뤘다. Phase 3 전체 완료가 아니라 report 구현 사전 추출 범위다.
