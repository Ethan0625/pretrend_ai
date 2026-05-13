# Changelog

## 현재 유효 규칙 (As-Is)
- 프로젝트 방향 / 트랙 경계 SOT: `docs/architecture/track_separation.md`
- 운영/작업 규칙 SOT: `.agent/WORKFLOW.md`, `.agent/CHANGE_GATES.md`
- 운영 실행 가이드 SOT: `docs/operation_guide.md`
- Infrastructure / 계약 SOT:
  - `docs/architecture/*_contract.md`
  - `docs/strategy_engine_design.md`는 계약/불변식 참조용으로 유지
- 상태 해석:
  - Observability Track + Infrastructure가 현재 메인 운영 범위다.
  - Personal Track(Strategy/Backtest/Paper/Broker)은 동결 + 운영 중단 상태이며, 아래 과거 섹션은 legacy 기록으로 보존한다.

> 참고: changelog 과거 섹션은 작성 시점 원문을 보존한다.

## v2026.05.13 — P25 완료: Gold Postgres sync DAG 도입

### feat(observability): Parquet Gold to Postgres mirror sync 추가
- `docs/architecture/gold_postgres_sync.md` 신설: 워터마크, lookback, UPSERT, DAG 트리거 정책 SOT
- sync runner 추가: `sync_gold_macro`, `sync_gold_eod`
- Airflow DAG `gold_postgres_sync_dag` 추가: 11:00 KST 독립 스케줄, `sync_macro` / `sync_eod` 병렬 task
- sync 정책: macro 35일 lookback, EOD 0일 lookback, 워터마크 NULL 시 전체 backfill, UPSERT 멱등
- 통합 검증: 첫 backfill macro 26,101행 / EOD 179,037행, 재실행 후 row count 변동 0

## v2026.05.13 — P24 완료: Gold Postgres schema 도입

### feat(observability): Gold-only Postgres mirror schema 추가
- `docs/architecture/gold_postgres_schema.md` 신설: `gold_macro_features`, `gold_eod_features` 컬럼/PK/nullability/hypertable/index 명세
- SQLAlchemy 모델 2개 추가: `GoldMacroFeature`, `GoldEodFeature`
- Alembic revision `0002` 추가: 두 Gold 테이블, TimescaleDB hypertable, BRIN/B-tree index 생성
- Macro는 Parquet contract와 맞춰 lineage 컬럼을 추가하지 않고, EOD lineage(`run_id_gold`, `ingestion_ts_gold`)만 mirror
- 데이터 적재/sync DAG는 P25 범위로 분리

## v2026.05.13 — P23 완료: Personal Track 테스트 archive 분리

### test(archive): Personal Track 테스트를 default pytest에서 분리
- `pyproject.toml`에 `testpaths = ["tests"]`, `norecursedirs += ["archive"]`를 추가해 `tests/archive/`를 기본 pytest 수집에서 제외
- `tests/archive/personal/` 보관소 신설
- Backtest / Paper / Broker / Personal Strategy Engine / Personal DAG / Telegram bot 테스트를 archive로 이동
- `tests/test_bot/`도 Personal Track 운영 중단 범위로 판단해 `tests/archive/personal/test_bot/`으로 이동
- active smoke 보강:
  - `tests/test_smoke.py`
  - `tests/observability/regime/position/test_market_position_smoke.py`
  - `tests/observability/explainability/test_context_smoke.py`
- 검증:
  - active default pytest → `315 passed, 3 skipped, 11 warnings`
  - archive manual pytest → `521 passed, 3 skipped`
  - 합산 → `836 passed, 6 skipped` (P22 baseline 833 passed + 신규 smoke 3건)

## v2026.05.13 — P22 완료: next_step 추출 + report_context 사전 추출

### refactor(observability/regime/transition): next_step을 strategy_engine에서 추출
- 5개 파일(`schema`, `engine`, `io`, `history_io`, `__init__`)을 `src/pretrend/observability/regime/transition/`으로 이전
- 기존 `src/pretrend/pipeline/strategy_engine/next_step/`는 re-export shim으로 변환해 backward compat 유지
- `engine.py`의 report 렌더링 의존은 신규 `pretrend.observability.explainability` 경로로 갱신
- 테스트 4개를 `tests/observability/regime/transition/`으로 이전

### refactor(observability/explainability): report_context 계열을 사전 추출
- `report_context.py`, `report_context_schema.py`, `report_context_localization.py`, `report_context_interpretation.py`, `report_context_formatter.py`를 `src/pretrend/observability/explainability/`로 이전
- 실제 의존성 확인 결과 `report_analyzer.py`도 `report_context.py`의 직접 의존이어서 함께 `src/pretrend/observability/explainability/analyzer.py`로 이전
- 기존 `src/pretrend/pipeline/strategy_engine/report_context*.py`, `report_analyzer.py`는 re-export shim으로 유지
- `test_strategy_engine_dag_report.py`의 monkeypatch target을 신규 explainability 경로로 갱신
- `test_report_analyzer.py`를 `tests/observability/explainability/`로 이전
- 신규 위치 테스트 `26 passed`, report DAG 테스트 `47 passed` 확인
- Observability 코드의 `pretrend.pipeline.strategy_engine` import 0줄 확인

## v2026.05.13 — P21 완료: group_transition 추출 (Phase 1 네 번째 모듈)

### refactor(observability/regime/rotation): group_transition을 strategy_engine에서 추출
- 5개 파일(`schema`, `engine`, `io`, `history_io`, `__init__`)을 `src/pretrend/observability/regime/rotation/`으로 이전
- 외부 strategy_engine 의존성 없음 → import 갱신 0
- 디렉토리 명 변경: 코드 모듈은 `group_transition`, 신규 위치는 `rotation`. 코드 내 심볼 명은 그대로 유지
- 기존 `src/pretrend/pipeline/strategy_engine/group_transition/`는 re-export shim으로 변환
- 외부 소비자(`strategy_job.py`, `backtest/runner.py`, `paper/{execution,io}.py`, `strategy_engine/report_context*.py`, 관련 테스트) 수정 0줄
- 테스트 `test_group_transition_engine.py`를 `tests/observability/regime/rotation/`으로 이전
- 외부 소비자 테스트 `86 passed`, group_transition 테스트 `4 passed` 확인
- 전체 회귀 `833 passed, 6 skipped, 11 warnings` 확인

## v2026.05.13 — P20 완료: market_position 추출 (Phase 1 세 번째 모듈)

### refactor(observability/regime/position): market_position을 strategy_engine에서 추출
- 2개 파일(`schema`, `engine`)을 `src/pretrend/observability/regime/position/`으로 이전
- `engine.py` 1줄 import 갱신: `..axis_horizon_state.schema` → `..horizon.schema`
- 기존 `src/pretrend/pipeline/strategy_engine/market_position/`는 re-export shim으로 변환
- 외부 소비자(`strategy_job.py`, `next_step/engine.py`, `policy_selector/engine.py`, `report_context_interpretation.py`, 관련 테스트) 수정 0줄
- 별도 market_position 테스트 파일 없음 → 테스트 이전 leaf 생략
- 외부 소비자 테스트 `70 passed`, 전체 회귀 `833 passed, 6 skipped, 11 warnings` 확인

## v2026.05.13 — P19 완료: axis_horizon_state 추출 (Phase 1 두 번째 모듈)

### refactor(observability/regime/horizon): axis_horizon_state를 strategy_engine에서 추출
- 5개 파일(`schema`, `long_engine`, `mid_engine`, `short_engine`, `builder`)을 `src/pretrend/observability/regime/horizon/`으로 이전
- `builder.py` 1줄 import 갱신: `..axis_features.schema` → `pretrend.observability.regime.axis.schema`
- 기존 `src/pretrend/pipeline/strategy_engine/axis_horizon_state/`는 re-export shim으로 변환
- Personal Track 소비자(`strategy_job.py`, `backtest/*`, `research/*`, `market_position/engine.py`, `next_step/engine.py`) 수정 0줄
- 테스트 4개를 `tests/observability/regime/horizon/`으로 이전
- `test_composer.py`, `test_strategy_job.py`는 shim 통해 그대로 동작
- 전체 회귀 `833 passed, 6 skipped, 11 warnings` 확인

## v2026.05.13 — P18 완료: axis_features 추출 (Phase 1 첫 타깃)

### refactor(observability/regime/axis): axis_features를 strategy_engine에서 추출
- 5개 axis 파일(`schema`, `macro_policy`, `price_volatility`, `flow_structure`, `sentiment`)을 `src/pretrend/observability/regime/axis/`로 이전
- 기존 `src/pretrend/pipeline/strategy_engine/axis_features/`는 re-export shim으로 변환해 backward compat 유지
- Personal Track 소비자(`strategy_job.py`, `axis_horizon_state/builder.py`) 수정 0줄
- 테스트를 `tests/observability/regime/axis/test_axis_features.py`로 이전
- 전체 회귀 `833 passed, 6 skipped, 11 warnings` 확인

## v2026.05.12 — 2026Q2 방향 재정의: Observability Track 본진화

### docs(direction): 프로젝트 기준점 재설정
- 프로젝트를 `Market Structure Observability Runtime`으로 재정의
- Two-Track 분리 확정:
  - Observability Track: 메인, 신규 작업 본진
  - Personal Track: 동결 + 운영 중단
- Cloud roadmap 확정:
  - Phase 0~1: 로컬 유지
  - Phase 2: Cloudflare Tunnel
  - Phase 4 이후: 필요 시 AWS/Hetzner 재검토

### ops(boundary): 현재 운영 범위 재해석
- 운영 유지:
  - Infrastructure (`macro`, `eod`, `calendar`)
  - Text observability
- 운영 중단:
  - `strategy_engine_dag`
  - `paper_trading_dag`
  - `broker_mock_trading_dag`
  - Telegram bot orchestration

### docs(legacy): 과거 기록 보존 원칙
- 2026-05-12 이전 changelog 항목은 작성 시점 원문을 보존한다.
- 단, Personal Track 관련 항목은 현재 운영 규칙이 아니라 legacy reference로 해석한다.

### docs(problem-definition): 프로젝트 문제 정의 + 전환 이유 명시화
- README, project_summary, DIRECTION, track_separation 4개 문서에 동일한 문제 정의 + 전환 이유 텍스트 동기화
  - "거시경제 흐름이 중요하다고 하지만, 거시 이벤트와 시장 구조 변화 연결을 반복 확인할 수 있는 개인용 도구가 적음"
  - "예측에서 시장 구조 관측으로 전환, 공개 운영 가능한 데이터 시스템으로 재설계하고 있음"

### docs(track-classification): docs/architecture/* 헤더 분류 표시 일괄 추가
- 16개 문서에 트랙 분류 헤더(`🔒 Frozen` / `🔄 Observability 자료` / `⚠️ Mixed`)를 일관된 패턴으로 추가
- 진짜 Frozen (4): `allocation_engine_contract`, `paper_execution_ledger_contract`, `paper_trading_alert_contract`, `policy_config_contract`
- Mixed (2): `text_strategy_connection_contract` (일부 규칙 Phase 3 차용), `universe_contract` (ETF SOT는 공유, picking은 frozen)
- Observability 재해석 (11): `market_structure_*` (4), `axis_horizon_dependency_contract`, `threshold_policy`, `next_step_signal_contract`, `group_transition_signal_contract`, `walk_forward_validation_contract`, `text_observability_contract`, `strategy_engine_design`, `strategy_architecture`
- 원칙: "전략" 영역 전체를 frozen 처리하지 않고, 시장 관측 영역과 매매 의사결정 영역을 세분화

### refactor(task-queue): TASK_QUEUE.md 재구성 + legacy archive
- 기존 ~2000줄 TASK_QUEUE.md → `.agent/task/archive/TASK_QUEUE_pre-2026Q2.md` 이동
- 새 TASK_QUEUE.md는 P17 (Observability Phase 0) 중심으로 ~120줄 재작성
- 신규 작업자/Codex 진입 컨텍스트 부담 12배 감소

### refactor(workflow): commit scope 표준 도입
- `.agent/WORKFLOW.md §6.2`에 Track scope 표준 추가
  - `observability` — 신규 작업 본진
  - `infra` — Infrastructure (Bronze/Silver/Gold, Macro/EOD)
  - `personal-frozen` — Personal Track unavoidable fix (극히 드물게)
- `§6.4`에 `personal-frozen` scope 등장 시 강화 규칙 추가 (변경 이유 명시, 신규 기능 0)

### feat(task-p17): Observability Phase 0 task 문서 6개 작성
- `P17_parent_observability_phase0.md` — parent task (DoD, 그룹, 실행 순서)
- `P17-1_docker_compose_postgres.md` — Postgres+TimescaleDB Docker Compose
- `P17-2_config_module_setup.md` — `pretrend.config` pydantic-settings
- `P17-3_models_package_init.md` — `pretrend.models` SQLAlchemy + Pydantic Base
- `P17-4_alembic_initial_setup.md` — Alembic baseline + TimescaleDB extension
- `P17-5_observability_layout_doc.md` — 디렉토리 레이아웃 매트릭스 문서

### docs(operation-guide): Observability 운영 명령 + DAG paused 안내
- `operation_guide.md`에 Phase 0 Docker Compose / Alembic / Config·Models 검증 명령 추가
- Phase 2~3 예정 명령 (FastAPI, Cloudflare Tunnel) 안내 추가
- Airflow DAG paused 처리 명령 (`paper_trading_dag`, `broker_mock_trading_dag`, `strategy_engine_dag`) 명시

### docs(environment): 신규 인프라 의존성 명시
- `environment.md §7.5` 신설 — Postgres+TimescaleDB Docker, 신규 Python 의존성(pydantic-settings, sqlalchemy, alembic, psycopg2-binary, asyncpg, fastapi, uvicorn) 표
- 환경 변수 `.env.example` 항목 명시 (DATABASE_URL, DATABASE_URL_ASYNC 등)

### docs(architecture): Observability Track 아키텍처 섹션 추가
- `architecture.md §6` 신설 — 신규 컴포넌트 디렉토리 트리 + 데이터 흐름 + Phase 0~4 로드맵
- `§7 결론` 갱신 — production-grade runtime ownership 목표 명시

### docs(milestones): Personal Track legacy 분리 + Observability 로드맵 추가
- `milestones.md` 상단에 Observability Track 로드맵 표(P17~P20 가칭) 추가
- 기존 M1~M6 Personal Track 마일스톤은 legacy 보존 표시

## v2026.03.25d — P11 완료: Telegram 리포트 구조 개편

> 해석 앵커(2026-03-30): 이 섹션의 `report`, `AI 해석`, `report analyzer`는 현재 기준으로 Telegram `analyzer_report` 축을 뜻한다. `review_packet -> audit_queue -> auditor` 감리 결과는 별도 `audit_report`, `_do_review_and_report()` 계열 완료 보고는 `task_review_report`로 분리해 읽는다.

### feat(report): Signal / AI / Result 보고 흐름 재정의
- `dags/strategy_engine_dag.py`
  - Signal report와 AI 해석을 분리 2메시지로 고정 발송하지 않고, `main + support` 구조의 1~2 메시지 흐름으로 통합
  - AI 해석은 본문 내 `핵심 판단 해석` 섹션으로 편입
- `src/pretrend/pipeline/strategy_engine/report_delivery.py`
  - Telegram 보고 구조 분리용 순수 helper 추가

### feat(strategy): report analyzer session 우선 경로 전환
- `src/pretrend/pipeline/strategy_engine/report_analyzer.py`
  - transitional `analyzer` 세션 경로 추가
- `src/pretrend/pipeline/strategy_engine/report_context.py`
  - `generate_llm_analysis()`를 analyzer-first, direct provider fallback 구조로 전환
- note:
  - `role + workspace` 물리 정규화는 아직 하지 않음
  - `analyzer`는 현재 phase에서 report 전용 세션 역할로만 해석

### feat(report): PAPER_RESULT compact 정책 적용
- `src/pretrend/pipeline/paper/report.py`
  - `PAPER_RESULT`를 본문 우선 + compact 실행 블록 구조로 재배치
  - `PnL / NAV / 포지션 변화 / 핵심 리스크`는 본문 유지
  - 브로커 인증/체결/실행 식별/그룹 게이트/체결 세부는 하단 compact block으로 이동

### feat(bot): team lead bot append-only streaming 정리
- `scripts/telegram_claude_bot.py`
  - placeholder send + `editMessageText`/delete 기반 응답 경로 제거
  - `stream-json` 기반으로 중간 문장과 최종 문장을 `sendMessage`로 누적 발송하도록 정리
- `src/pretrend/pipeline/notify/telegram_sender.py`
  - 기존 완성본 1회 발송 경로 유지

### test
- `tests/dags/test_strategy_engine_dag_report.py`
- `tests/pipeline/strategy_engine/test_report_analyzer.py`
- `tests/pipeline/strategy_engine/test_strategy_engine_dag_report.py`
- `tests/pipeline/backtest/test_paper_trading_report.py`
- `tests/test_bot/test_telegram_claude_bot.py`
- 검증 결과:
  - `conda run -n pytest-pretrend pytest tests/test_bot/test_telegram_claude_bot.py -q` → `13 passed`
  - `conda run -n pytest-pretrend pytest tests/test_bot/ -q --tb=short` → `81 passed`
  - `conda run -n pytest-pretrend pytest --tb=no -q` → `783 passed, 6 skipped, 11 warnings`

## v2026.03.12d — Report LLM: Ollama → Gemini 2.5 Flash 전환

### feat(strategy): Report LLM provider Gemini 전환
- `src/pretrend/pipeline/strategy_engine/report_context.py`
  - `_call_gemini()` 추가 (`google-genai` SDK v1.66.0 사용)
  - `generate_llm_analysis()` 재작성:
    - `REPORT_LLM_PROVIDER=gemini`(기본): Gemini 시도 → retry 3회(backoff 1s/2s/4s) → Ollama fallback
    - `REPORT_LLM_PROVIDER=ollama`: 기존 동작 유지
  - fail-open 유지 (모든 경로 실패 시 None 반환)

### env
- `.env` 추가:
  - `REPORT_LLM_PROVIDER=gemini`
  - `REPORT_LLM_MODEL=gemini-2.5-flash`
  - `REPORT_LLM_FALLBACK_ENABLED=1`
  - `REPORT_LLM_RETRY=3`

### deps
- `google-genai` 설치 완료 (pytest-pretrend / airflow-pretrend / pretrend-dev)
- `google-generativeai` (deprecated) 대신 `google.genai` 신규 SDK 사용

### test
- `test_generate_llm_analysis_fail_open_on_error` — `REPORT_LLM_PROVIDER=ollama` 명시
- `test_generate_llm_analysis_returns_string_on_success` — `REPORT_LLM_PROVIDER=ollama` 명시
- `test_generate_llm_analysis_gemini_success` 신규
- `test_generate_llm_analysis_gemini_fallback_to_ollama` 신규
- 검증: `44 passed` / 전체 `685 passed, 6 skipped`

---

## v2026.03.12c — P5-2d 완료: SKEW Gold feature 구현

### feat(data): `skew_gold` macro feature 추가
- `src/pretrend/pipeline/features/skew_gold.py`
  - 입력: `data/gold/eod/eod_features/symbol=^SKEW/`
  - 출력:
    - `trade_date`
    - `skew_close`
    - `skew_zscore_252`
    - `skew_extreme_flag`
    - `run_id`
    - `ingestion_ts`

### storage
- 저장 경로:
  - `data/gold/macro/skew/put_call/date=YYYY-MM-DD/skew_YYYYMMDD.parquet`
- 저장 정책:
  - 날짜 파티션 overwrite
  - stale `_tmp_run=*` 디렉터리 정리 후 재실행

### quality
- 전체 구간 생성 결과:
  - `5519 rows`
  - `2004-01-02 ~ 2026-03-11`
  - `skew_extreme_flag non-zero: 5.00%`

### test
- `tests/pipeline/features/test_skew_gold.py` 신규
- 검증 결과:
  - `conda run -n pytest-pretrend pytest tests/pipeline/features/test_skew_gold.py -v` → `4 passed`
  - `conda run -n pytest-pretrend pytest --tb=no -q` → `689 passed, 6 skipped, 11 warnings`

## v2026.03.12b — P5-2c 완료: ^SKEW EOD observability 편입 + backfill

### feat(data): `^SKEW` observability 편입
- `src/pretrend/pipeline/config/eod_observability.py`
  - `OBSERVABILITY_SET_V1`에 `^SKEW` 추가
  - 분류:
    - `asset_group=VOLATILITY_INDEX`
    - `asset_name=CBOE_SKEW_INDEX`
    - `asset_subtype=SKEW`
- 총 관측 수:
  - `39 ETFs + 2 volatility indices` (`^VIX`, `^SKEW`)

### docs(contract): observability contract에 `^SKEW` 반영
- `docs/architecture/eod_observability_contract.md`
  - Base EOD Observability Set 표에 `^SKEW` 추가
  - rationale: `꼬리위험/OTM put 수요 센서`

### test
- `tests/pipeline/test_eod_observability_contract.py`
  - 총 개수 `41` 검증
  - `^SKEW` 라벨/그룹 검증 추가
- 검증 결과:
  - `conda run -n pytest-pretrend pytest tests/pipeline/test_eod_observability_contract.py -v` → `11 passed`

### backfill
- 실행:
  - `conda run -n pytest-pretrend python -m pretrend.pipeline.eod_job --start 2004-01-02 --end 2026-03-12 --symbols "^SKEW"`
- 결과:
  - `data/gold/eod/eod_features/symbol=^SKEW/` 생성
  - `267 parquet files`
  - `5519 rows`
  - `2004-01-02 ~ 2026-03-11`

### note
- `^SKEW`는 `P5-2d`에서 `skew_extreme_flag` macro feature의 입력으로 사용된다.

## v2026.03.12b — P5-2 방향 전환: CBOE Put/Call → SKEW

### decision: CBOE Put/Call 수집 중단 및 ^SKEW 전환

**배경**
- P5-2a/2b에서 CBOE Put/Call Bronze→Silver→Gold 파이프라인을 구축 완료
- P5-2c backfill 실행 시 CBOE CDN(`cdn.cboe.com`) CloudFront IP 수준 403 Forbidden 차단 확인
- User-Agent/Referer 헤더 추가 및 `curl` 직접 요청도 동일하게 차단됨
- 유료 대안(Polygon, Tradier, ORATS) 비용 과다($29~$300+/월) → 채택 불가

**결정**
- CBOE Put/Call 수집 포기, ^SKEW(CBOE Skew Index, Yahoo Finance)로 전환
- ^SKEW는 OTM put 수요(꼬리 위험 헤지) 측정 목적이 P/C ratio와 동일하며 무료
- EOD 파이프라인 재사용 가능 (^VIX 편입 패턴 동일)

**변경 내용**
- 삭제: `src/pretrend/pipeline/ingest/cboe.py`
- 삭제: `src/pretrend/pipeline/features/cboe_silver.py`
- 삭제: `src/pretrend/pipeline/features/cboe_gold.py`
- 삭제: `tests/pipeline/ingest/test_cboe.py`
- 삭제: `tests/pipeline/features/test_cboe_silver_gold.py`
- 수정: `dags/macro_pipeline_dag.py` — cboe import 및 `cboe_ingest_task` 제거
- 수정: `docs/architecture/macro_pipeline_scope.md` — CBOE 내용 제거, SKEW→EOD 파이프라인 명시
- 아카이브: `.agent/task/archive/P5-2/` — CBOE 관련 task 문서 전량 이동

**후속 작업**
- P5-2c: ^SKEW EOD 편입 + backfill
- P5-2d: skew_gold feature 구현 (skew_extreme_flag)
- P5-2e: Short Engine v1.3 SKEW 통합

### test
- 검증 결과: `conda run -n pytest-pretrend pytest --tb=no -q` → `683 passed, 6 skipped`

---

## v2026.03.12a — P5-2b 완료: CBOE Put/Call Silver/Gold feature 추가

### feat(data): Put/Call Silver feature 추가
- `src/pretrend/pipeline/features/cboe_silver.py`
  - Bronze raw를 SPY 거래일 기준으로 left join
  - `equity_pc_ratio` outlier(` < 0.1` 또는 `> 3.0`)는 `NaN` 처리
  - Silver year partition 저장:
    - `data/silver/macro/cboe/put_call/year=YYYY/cboe_put_call_YYYY.parquet`

### feat(data): Put/Call Gold feature 추가
- `src/pretrend/pipeline/features/cboe_gold.py`
  - forward-fill된 `equity_pc_ratio`, `total_pc_ratio`
  - `equity_pc_ma5`, `equity_pc_ma20`
  - `equity_pc_zscore_20d`, `total_pc_zscore_20d`
  - `equity_pc_extreme_high`, `equity_pc_extreme_low`, `put_call_extreme_flag`
  - Gold year partition 저장:
    - `data/gold/macro/cboe/put_call/year=YYYY/cboe_put_call_gold_YYYY.parquet`

### feat(pipeline): Bronze → Silver → Gold 독립 runner 연결
- `run_cboe_put_call_pipeline()` 추가
- 기존 `macro_job`/FRED path는 수정하지 않고, Put/Call feature 경로를 별도 독립 runner로 연결

### test
- `tests/pipeline/features/test_cboe_silver_gold.py` 신규
  - Silver 날짜 정합
  - 이상치 NaN 처리
  - Gold forward-fill
  - zscore 정확성
  - extreme flag 경계값
  - temp 경로 pipeline write 검증
- 검증 결과:
  - `conda run -n pytest-pretrend pytest tests/pipeline/features/test_cboe_silver_gold.py -v` → `7 passed`
  - `conda run -n pytest-pretrend pytest --tb=no -q` → `693 passed, 6 skipped`

## v2026.03.11g — P5-2a 완료: CBOE Put/Call Bronze ingest + macro pipeline 편입

### feat(data): CBOE Put/Call Bronze ingest 모듈 추가
- `src/pretrend/pipeline/ingest/cboe.py`
  - CBOE 연도별 CSV(`options_stats_{YYYY}.csv`) 다운로드
  - 표준 컬럼 정규화:
    - `date`
    - `equity_pc_ratio`
    - `total_pc_ratio`
    - `index_pc_ratio`
  - Bronze 파티션 저장:
    - `data/bronze/macro/cboe/put_call/date=YYYY-MM-DD/cboe_put_call_YYYYMMDD.parquet`

### feat(dag): `macro_pipeline_dag`에 `cboe_ingest_task` 병렬 추가
- `dags/macro_pipeline_dag.py`
  - 기존 `run_macro_job_task`는 그대로 유지
  - 신규 `cboe_ingest_task`는 FRED task와 순서 의존성 없이 병렬 실행
  - CBOE 수집 실패 시 warning dict 반환으로 fail-open 유지

### docs: `macro_pipeline_scope.md` 신규 작성
- `docs/architecture/macro_pipeline_scope.md`
  - FRED 경제/정책 신호와 CBOE Put/Call 시장심리 신호를 동일 DAG에 편입한 이유 명시
  - `macro_pipeline_dag` 범위 확장임을 문서화

### test
- `tests/pipeline/ingest/test_cboe.py` 신규
  - CSV 파싱
  - Bronze 파티션 쓰기
  - 날짜 범위 필터
- 검증 결과:
  - `conda run -n pytest-pretrend pytest tests/pipeline/ingest/test_cboe.py -v` → `3 passed`
  - `conda run -n airflow-pretrend python -c "from dags.macro_pipeline_dag import macro_pipeline_dag; print('OK')"` → `OK`
  - `conda run -n pytest-pretrend pytest --tb=no -q` → `686 passed, 6 skipped`

## v2026.03.11f — P5-1 완료: VIX 수집 → Short Engine v1.2 → Backtest 검증

### feat(data): ^VIX EOD 수집 + 전체 구간 backfill (P5-1a)
- `eod_observability.py`에 `^VIX` 추가 (`VOLATILITY_INDEX` / `CBOE_VOLATILITY_INDEX` / `IMPLIED_VOL`)
- `data/gold/eod/eod_features/symbol=^VIX/` 생성 (2004-01-02 ~ 2026-03-10, 5,581 rows)

### research: VIX step 분석 리포트 생성 (P5-1b)
- 6개 VIX step(LOW/NORMAL/ELEVATED/HIGH/STRESS/EXTREME) × 시장 반응 분석
- 기존 Short Engine PANIC 신호와의 교차 확인: PANIC 발생 시 평균 VIX = 43.45 (EXTREME 구간)
- GFC(49.68), COVID(76.45), Rate Hike 2022(34.02) 이벤트 교차 확인
- PANIC 임계값 결정: **VIX > 35 (EXTREME 구간)**, RELIEF 조건 추가 유보
- 산출물: `result/research/vix_step_analysis_20260311.md`

### feat(strategy): Short Engine v1.2 — vix_extreme 5번째 신호 추가 (P5-1c)
- `src/pretrend/pipeline/strategy_engine/axis_horizon_state/short_engine.py`
  - `_VIX_EXTREME_THRESHOLD = 35.0` 상수 추가
  - `compute_short_state(..., vix_close=None)` 파라미터 확장
  - Secondary PANIC 보조 신호 4개 → 5개 (`vix_extreme` 추가), `>= 2` 조건 유지
  - `vix_close=None` fallback: `vix_extreme=False` (fail-open, 기존 v1.1 동작 유지)
  - 진단 필드에 `vix_extreme`, `vix_close` 추가
- `src/pretrend/pipeline/strategy_engine/axis_horizon_state/builder.py`
  - Gold EOD `^VIX` `adj_close` → `vix_close`로 전달

### verify(backtest): Short Engine v1.1 vs v1.2 전체 지표 비교 (P5-1d)
- 비교 구간: 2006-01-03 ~ 2024-06-03, v2 preset
- 결과:
  | 지표 | v1.1 | v1.2 (VIX) | delta |
  |---|---|---|---|
  | XIRR | +7.25% | +7.42% | +0.18%p ↑ |
  | DCA Return | +105.84% | +109.72% | +3.88%p ↑ |
  | MDD | -15.65% | -16.21% | -0.56%p ↓ |
  | Sharpe | 1.68 | 1.68 | 동일 |
  | Calmar | 1.96 | 1.90 | -0.06 ↓ |
- 이벤트 선행성: Rate Hike 2022에서 PANIC 58일 선행 감지 (2022-05-05 → 2022-03-08)
- GFC/COVID: 첫 PANIC 날짜 변화 없음 (기존 신호가 이미 충분히 감지)
- 채택 결론: **조건부 채택** — XIRR·DCA 개선, Rate Hike 선행 효과. MDD 소폭 악화는 Put/Call 수집 후 재평가(P5-2e) 예정
- 산출물: `result/backtest_compare/vix_engine_v11_vs_v12_20260311.md`

### test
- 전체 pytest: `683 passed, 6 skipped`

## v2026.03.11b — P4-8 SCHD floor 정책을 SIM/Mock 실행 경로로 확장

### feat(paper): SIM 실행 경로에 `schd_min_weight=0.20` 적용
- `src/pretrend/pipeline/paper/execution.py`
  - `simulate_paper_execution(..., schd_min_weight=0.0)` 추가
  - SCHD 매도 시 `sim_nav * schd_min_weight` 이하로 내려가는 매도 수량을 차단
- `dags/paper_trading_dag.py`
  - `schd_sell_locked=True` 기반 lock 정책을 중단하고
  - `schd_sell_locked=False`, `schd_min_weight=0.20`으로 전환

### feat(broker): Mock planner에 `schd_min_weight=0.20` 적용
- `src/pretrend/pipeline/broker/execution_planner.py`
  - `build_broker_target_orders(..., schd_min_weight=0.0)` 추가
  - BUY는 `target_usd >= broker_nav_usd * schd_min_weight` 보장
  - SELL은 SCHD floor 초과분만 허용
- `dags/broker_mock_trading_dag.py`
  - 화요일 BUY, 금요일 staged sell 모두 `lock_sell_symbols=["SCHD"]`를 제거하고
  - `lock_sell_symbols=[]`, `schd_min_weight=0.20` 전달

### ops: broker mock 자동 스케줄 활성화를 위한 env 추가
- `.env`, `.env.airflow`에 `BROKER_MOCK_AUTO_SCHEDULE_ENABLED=1` 추가
- `broker_mock_trading_dag.py`의 크론은 기존 구현 유지:
  - `"40 9 * * 1-5"` (ET 기준 09:40)

### test
- 추가/확장 검증:
  - `tests/pipeline/paper/test_execution_soft_gate.py`
  - `tests/pipeline/broker/test_execution_planner.py`
  - `tests/dags/test_paper_trading_dag.py`
  - `tests/dags/test_broker_mock_trading_dag.py`
- 결과:
  - leaf 범위 테스트 `48 passed, 3 skipped`
  - `tests/dags/` `26 passed, 3 skipped`

### 운영 주의
- 코드와 env 반영은 완료됐지만, Airflow scheduler 재시작은 `sudo` 비밀번호 입력이 필요한 운영 단계다.
- 따라서 실제 자동 스케줄 활성은 scheduler 재시작 이후 확인해야 한다.

## v2026.03.11a — HYG/LQD EOD 역사 데이터 backfill + credit_stress v3 재실행

### fix(data): HYG/LQD bronze→silver→gold EOD 역사 backfill
- HYG/LQD가 `OBSERVABILITY_SET_V1`에 포함되어 있었으나 초기 전체 backfill 시 수집이 누락되어 bronze가 2026-02 이후만 존재
- `eod_job` 으로 2006-01-03 ~ 2026-03-10 전 구간 재수집
  - HYG: bronze 2007-04-11 ~ 2026-03-10 (상장일 기준), silver/gold 동일 범위
  - LQD: bronze 2006-01-03 ~ 2026-03-10, silver/gold 동일 범위

### fix(backtest): `credit_stress` 실데이터 기반 재검증 (v3)
- HYG/LQD backfill 완료 후 `define_slice_masks()`의 `credit_spread_20d` 조건이 정상 작동 확인
  - `credit_spread_20d.notna().any() = True` → SPY vol 대체 분기 진입하지 않음
  - 기존 임계값 `< -0.03` 그대로 사용
- 슬라이스 분석 v3 재실행 결과:
  - 산출물: `result/backtest_compare/slice_analysis/long_20060103-20240603_v341_vs_floor20_v3.md`
  - `credit_stress n_windows = 38`, obs_days = 260 (2007-07-25 ~ 2023-04-05)
  - v3.4.1: `nav_return +0.53%`, `mdd -1.82%`, `post_20d +2.98%`, `post_60d +7.74%`
  - v3.4.1-schd-floor-20: `nav_return +0.42%`, `mdd -1.27%`, `post_20d +2.42%`, `post_60d +6.35%`
  - delta(floor-lock): `nav -0.10%`, `MDD +0.55%`, `post_20d -0.56%`, `post_60d -1.39%`

### 해석
- 신용 경색 구간(HYG-LQD spread < -3%)에서 floor 전략의 MDD 방어 효과 +0.55%p가 8개 슬라이스 중 최대
- lock 전략이 nav_return 및 사후 회복(post_20d/60d)에서 우세 → SCHD 고비중이 신용 경색 이후 반등에 유리
- v2(SPY vol 대체) 대비 v3(실데이터)는 n_windows 7→38로 통계적 신뢰도 대폭 향상

## v2026.03.10j — P4-7 credit_stress 슬라이스 보정

### fix(backtest): `credit_stress` 데이터 부재 fallback 추가
- `src/pretrend/pipeline/backtest/slice_analysis.py`
  - `load_gold_eod_slice_features()`가 `ret_20d`와 함께 `vol_20d`도 로드
  - `credit_spread_20d`가 실질적으로 부재하면(`HYG/LQD` 장기 데이터 없음) `credit_stress`를 `SPY vol_20d > 0.025`로 대체
  - 다른 7개 슬라이스 정의는 유지
- `tests/pipeline/backtest/test_slice_analysis.py`
  - `test_define_slices_credit_stress_mask`를 fallback 경로 검증으로 갱신

### 진단 결과
- 장기 구간(2006-01-03 ~ 2024-06-03)에서 `HYG/LQD` gold EOD는 실질적으로 비어 있었다.
  - 실제 parquet는 `2026-02`, `2026-03` 2개 파티션만 존재
  - `ret_20d`도 null
- 따라서 기존 `credit_spread_20d < -0.03` 정의는 표본 0개를 만들었고, leaf 문서 기준 `Case C`를 채택했다.

### 재실행 결과
- 산출물:
  - `result/backtest_compare/slice_analysis/long_20060103-20240603_v341_vs_floor20_v2.md`
- `credit_stress` 구간: `n_windows = 7`, 날짜 범위 `2008-09-29 ~ 2020-04-29`
- 핵심 비교:
  - `v3.4.1`: `nav_return +2.40%`, `mdd -5.94%`, `post_20d +0.75%`
  - `v3.4.1-schd-floor-20`: `nav_return +3.35%`, `mdd -2.82%`, `post_20d +3.42%`

### 주의사항
- 현재 `credit_stress`는 HYG/LQD credit spread가 아니라 `SPY vol_20d` 기반 stress proxy다.
- 향후 HYG/LQD 장기 backfill이 완료되면 원래 정의 복구 여부를 다시 검토해야 한다.

## v2026.03.10i — P4-6 조건부 슬라이스 분석 추가

### feat(backtest): `daily_log.schd_weight` 추가
- `src/pretrend/pipeline/backtest/runner.py`
  - `daily_log`에 `schd_weight` 컬럼 추가
  - 정의: 해당 거래일 `SCHD 평가금액 / NAV`
  - `SCHD` 미보유 시 `0.0`

### feat(backtest): 조건부 슬라이스 분석 모듈 추가
- `src/pretrend/pipeline/backtest/slice_analysis.py`
  - 8개 시장 슬라이스 정의:
    - `oil_shock`
    - `rate_shock`
    - `credit_stress`
    - `concentration_extreme`
    - `defensive_stress`
    - `transition_risk_high`
    - `oil_rate_shock`
    - `concentration_transition`
  - `min_days=3` 연속 구간 window 추출
  - 전략 비교표 / 차이표 / 샘플 수 체크표 markdown 생성
- `tests/pipeline/backtest/test_slice_analysis.py`
  - 슬라이스 정의/윈도우 추출/지표 계산/표 구조 검증 추가
- `tests/pipeline/backtest/test_runner.py`
  - `schd_weight` 회귀 검증 2건 추가

### 분석 결과 (장기 구간: 2006-01-03 ~ 2024-06-03)
- 산출물:
  - `result/backtest_compare/slice_analysis/long_20060103-20240603_v341_vs_floor20.md`
- 핵심 해석:
  - `defensive_stress`, `transition_risk_high`에서는 `v3.4.1-schd-floor-20`이 평균 MDD를 개선하면서 `nav_return`은 동등~소폭 우세
  - `concentration_extreme`, `concentration_transition`에서는 floor가 방어는 개선하지만 `nav_return`은 lock 대비 소폭 열세
  - `credit_stress`는 표본 0개, `oil_rate_shock`는 표본 3개로 결론 보류(`*`)

## v2026.03.10h — P4-5b backtest SCHD floor 파라미터 추가

### feat(backtest): `v3.4.1-schd-floor-20` preset 추가 — SCHD 최소 비중 floor 정책
- `src/pretrend/pipeline/backtest/config.py`
  - `BacktestConfig`에 `schd_min_weight: float = 0.0` 추가 (기본 0.0 = 현행 lock 동작)
  - 기존 preset(`v3.4.1`, `v3.4.1-sim`)에 `schd_sell_locked: bool = True` 명시 (하위호환)
  - `v3.4.1-schd-floor-20` preset 추가 (`schd_min_weight=0.20`, `schd_sell_locked=False`)
- `src/pretrend/pipeline/backtest/rebalancer.py`
  - `compute_schd_min_hold_value()` 추가 — SCHD 현재가 × floor 수량 계산
- `src/pretrend/pipeline/backtest/portfolio.py`
  - `rebalance_to_weights(..., min_hold_values={})` 추가 — floor 이하 매도 차단/캡
- `src/pretrend/pipeline/backtest/runner.py`
  - monthly rebalance / staged sell 경로에 SCHD floor 적용
- `src/pretrend/pipeline/backtest/allocation.py`
  - `v3.4.1-schd-floor-20` dispatch registry 추가

### test(backtest): SCHD floor 로직 검증
- `tests/pipeline/backtest/test_rebalancer.py` — floor 계산 + 매도 캡 로직 테스트
- `tests/pipeline/backtest/test_allocation_v3.py` — dispatch 경로 검증

### 비교 결과 (2006-01-03 ~ 2024-06-03)
- `v3.4.1` (SCHD lock): XIRR `+8.85%`, MDD `-24.79%`, Sharpe `1.63`, 평균 SCHD 비중 `68.35%`
- `v3.4.1-schd-floor-20` (SCHD floor 20%): XIRR `+6.59%`, MDD `-14.43%`, Sharpe `1.71`, 평균 SCHD 비중 `7.93%`
- 차이 (`floor - lock`): XIRR `-2.25%p`, MDD `+10.36%p` 개선, Sharpe `+0.07`

### 운영 해석
- SCHD floor 정책은 방어지표(MDD -10.36%p 개선, Sharpe +0.07) 우세지만 수익지표(XIRR -2.25%p) 악화
- 전체 장기 비교만으로는 정책 결정 불충분 → P4-6 조건부 슬라이스 분석으로 국면별 비교 예정

### 주의사항
- 전체 pytest: 2 failed (기존 문서 smoke 실패 — P4-5b 범위 외, 영향 없음)
  - `test_universe_stock_extension_section_exists`
  - `test_execution_research_grain_isolation_defined`

## v2026.03.10g — P4-5a backtest SIM 방식 preset 추가

### feat(backtest): `v3.4.1-sim` preset 추가
- `src/pretrend/pipeline/backtest/config.py`
  - `BacktestPreset`, `BacktestConfig`에 `monthly_rebalance: bool = True` 추가
  - 신규 preset `v3.4.1-sim` 추가 (`monthly_rebalance=False`)
- `src/pretrend/pipeline/backtest/runner.py`
  - 월 첫 거래일 로직을 분리:
    - DCA(`monthly_addition`)는 항상 수행
    - 전면 리밸런싱은 `monthly_rebalance=True`일 때만 수행
- `src/pretrend/pipeline/backtest/allocation.py`
  - `v3.4.1-sim`을 allocation dispatch registry에 연결

### test(backtest): SIM 방식 회귀 검증 추가
- `tests/pipeline/backtest/test_runner.py`
  - `monthly_rebalance=False` 시 월 첫 거래일 전면 리밸런싱 미발생 + DCA 유지 검증
  - `monthly_rebalance=True` 기본 동작 유지 검증
- `tests/pipeline/backtest/test_allocation_v3.py`
  - `v3.4.1-sim` dispatch가 `compute_allocation_v3` 경로를 타는지 검증

### 비교 결과 (2006-01-03 ~ 2024-06-03)
- `v3.4.1`: XIRR `+7.33%`, MDD `-16.11%`, Sharpe `1.69`
- `v3.4.1-sim`: XIRR `+6.92%`, MDD `-26.88%`, Sharpe `1.67`
- 차이 (`sim - base`):
  - XIRR `-0.41%p`
  - MDD `-10.77%p`
  - Sharpe `-0.02`

### 운영 해석
- SIM 방식(monthly_rebalance=False)은 월간 전면 리밸런싱을 제거해 거래 수가 줄지만, 장기 구간에서 최대낙폭이 크게 악화됐다.
- 따라서 P4-5 상위 판단 기준상 "SIM 방식 성과 ≪ 월간 리밸런싱 성과"에 해당하며, SIM 경로의 월간 리밸런싱 추가 여부를 검토할 정량 근거가 확보됐다.

## v2026.03.10f — P4-4 broker_mock 실행 규칙 정합

### feat(broker-dag): broker_mock에 SIM 동일 요일 규칙 적용
- `dags/broker_mock_trading_dag.py`
  - ET 기준 weekday 분기 추가
    - 월요일: 평가-only, 주문 없음
    - 화요일: INCREASE 경로에서 `allow_sell=False`
    - 수/목: HOLD
    - 금요일: DECREASE 경로에서 staged sell 실행
  - `lock_sell_symbols=["SCHD"]`를 planner에 전달해 SCHD 매도 금지 적용

### feat(broker-dag): staged sell JSON 영속화 추가
- `dags/broker_mock_trading_dag.py`
  - `data/paper/broker_staged_sell/staged_sell_state.json` 저장/로드/삭제 helper 추가
  - 금요일 DECREASE는 50% → 30% → 20% 트랜치로 나눠 실행
  - 월요일 신호 반전(`action != DECREASE`) 시 staged sell 상태를 삭제
  - JSON 파싱 실패는 fail-open(주문 없이 경고)으로 처리

### feat(broker-dag): Level 2 가드레일을 broker_mock INCREASE 경로에 적용
- `dags/broker_mock_trading_dag.py`
  - broker bootstrap 이력에서 peak NAV를 집계
  - `NAV / total_invested_capital < 0.85` 또는 `peak_dd < -0.20`이면 화요일 INCREASE 차단
  - DECREASE는 가드레일 발동 중에도 허용

### 운영 관측 변화
- broker_mock는 이제 SIM과 같은 주간 실행 규칙을 따른다.
- 장중 수동/자동 실행 시:
  - 월요일에는 주문이 발생하지 않는다.
  - 화요일에는 매수만 허용된다.
  - 금요일 DECREASE는 staged sell 상태를 이어받아 순차 매도한다.
- Telegram/운영 로그에서 Level 2 가드레일 경고가 broker_mock에도 나타날 수 있다.

## v2026.03.10c — P4-3 운영 문서 정합 부분 갱신

### docs(operation): broker_mock 실행 경로를 P4-2 이후 구조로 정렬
- `docs/operation_guide.md`
  - `broker_mock_trading_dag` 설명을 `SIM execution_ledger` 입력 기반에서
    `strategy stages(exposure, what_to_hold, next_step) + broker state` 직접 로드 기반으로 교체
  - 선행 조건을 `paper_trading_dag` 완료가 아니라 `strategy_engine_dag` 산출물 존재 기준으로 수정

### docs(operation): SIM / broker_mock 실행 모델 차이 명시
- `docs/operation_guide.md`
  - 초기 자금, DCA, 가격 소스, 요일 규칙, 분할 매도, SCHD 매도 금지, Level 2 가드레일의
    SIM vs broker_mock 차이를 표로 정리
  - P4-4 구현 전 broker_mock의 미정합 항목을 운영 문서에서 명시

### docs(operation): Level 2 운영 경계 절차를 contract §10 기준으로 정합화
- `docs/operation_guide.md`
  - 구 기준 `NAV < 초기자금의 70%`, `PANIC 5연속 hard stop` 제거
  - 계약 기준으로 교체:
    - `NAV / total_invested_capital < 0.85`
    - `ATH 대비 낙폭 < -0.20`
    - `PANIC streak >= 5`는 경고만
  - 발동 시 `INCREASE` 차단 / `DECREASE` 허용 / DCA 유지 / `guardrail_paused=True` / Telegram risk warning 명시

### docs(context): STABLE_CONTEXT.md §5 broker_mock 설명 갱신
- `.agent/STABLE_CONTEXT.md`
  - `broker_mock_trading_dag` 설명을 SIM execution_ledger 기반에서 strategy stages 직접 읽기 기반으로 교체 (P4-2 이후 구조 반영)
  - SIM과 broker_mock의 초기 자금 / DCA / 가격 소스 / 요일 규칙 / 분할 매도 / SCHD 매도 금지 / Level 2 가드레일 차이 요약 추가 (P4-4 구현 전 gap 명시)

## v2026.03.10d — P4-4a execution_planner API 확장 (allow_sell / lock_sell_symbols)

### feat(broker): build_broker_target_orders() 에 allow_sell, lock_sell_symbols 파라미터 추가
- `src/pretrend/pipeline/broker/execution_planner.py`
  - `allow_sell: bool = True` 파라미터 추가 — `False` 시 반환 DataFrame에서 action=="SELL" 행 전체 제거
  - `lock_sell_symbols: Sequence[str] = ()` 파라미터 추가 — 지정 심볼의 SELL 행만 선택적으로 제거
  - `next_invested_ratio <= 0.0`인 TARGET_ZERO 경로에도 동일 필터 적용
  - 기본값 `allow_sell=True`, `lock_sell_symbols=()` — 기존 호출자 영향 없음 (backward compat 유지)
- `tests/pipeline/broker/test_execution_planner.py`
  - 신규 테스트 4개 추가:
    - `test_allow_sell_false_no_sell_orders`
    - `test_allow_sell_true_default_behavior`
    - `test_lock_sell_symbols_excludes_schd`
    - `test_lock_sell_symbols_target_zero_excludes_locked`

### 운영 관측 변화
- P4-4b에서 broker_mock_trading_dag가 `allow_sell=False`(화요일), `lock_sell_symbols=["SCHD"]`를 전달하는 API가 준비됨
- 기존 DAG 호출 코드는 파라미터 추가 없이 기존과 동일하게 동작

## v2026.03.10b — P4-2 Broker 독립 실행 계획 (SIM 의존 제거)

### feat(broker): Broker 실행 플래너 — strategy stages 기반 독립 주문 계획
- `src/pretrend/pipeline/broker/execution_planner.py` (신규)
  - `build_broker_target_orders()`: strategy `exposure` + `what_to_hold` + broker NAV/positions/live_prices → broker-scale delta order DataFrame
  - Core 비중: SPY 30%, SCHD 50%, IAU 20% (전 국면 불변)
  - Tactical 슬롯: RISK_ON_BIAS=그룹당 2, NEUTRAL_BIAS=1, RISK_OFF_BIAS=0
  - missing live price → crash 없이 해당 심볼 skip
  - action="HOLD" → 빈 DataFrame

### refactor(broker-dag): broker_mock_trading_dag SIM execution_ledger 의존 제거
- `dags/broker_mock_trading_dag.py`
  - `load_sim_ledger_task`: SIM ledger 로드 제거 → strategy `exposure` 최신 trade_date 기준 실행 여부 판단
  - `execute_broker_orders_task`: strategy stages(`exposure`, `what_to_hold`, `next_step_signal`) + broker state로 직접 주문 계획 생성
  - `qty_scale_factor` 계산 블록 제거 (임시 해결책 삭제)
  - Telegram `virtual_fills`: SIM ledger 행 → `broker_fills` parquet 기반 실체결 내역으로 교체

### 운영 관측 변화
- 기존: broker_mock_trading_dag가 SIM execution_ledger를 입력으로 받아 qty_scale_factor로 수량 스케일
- 변경: strategy stages + broker 실시간 NAV/positions/live price를 직접 참조하여 broker-scale 수량 계산
- Telegram "모의계좌 체결 요약": SIM 계획 내역(BUY/SELL 달러 금액) → 실제 broker 체결 내역(심볼 수량 @ 가격) 형식으로 변경
- paper_trading_dag(SIM)와 broker_mock_trading_dag는 완전 독립 실행 (SIM 데이터 의존 없음)

## v2026.03.10a — P4-1 hotfix: 취소 오경보 수정 + SIM→broker qty 스케일

### fix(broker): cancel 실패 후 FILLED 재확인 — "취소 실패" 오경보 억제
- `src/pretrend/pipeline/broker/order_manager.py`
  - `check_and_cancel_unfilled()`: cancel 실패 시 `get_order_status()` 재조회 추가
    - 재조회 결과가 `FILLED/PARTIAL_FILLED`이면 `cancel_status="ALREADY_FILLED"`, warning은 `"이미 체결됨 확인"`으로 격하
    - `"취소 실패"` warning은 재조회 후에도 FILLED 미확인 시에만 발송
  - 배경: KIS VTS fill inquiry 즉시 빈 응답 → `ACCEPTED` 오판 → cancel 시도 → cancel 실패 → 오경보 체인
  - 한계: VTS 처리 지연 시 재조회도 `ACCEPTED` 반환 가능 — 이 경우 warning은 정상적으로 유지됨

### feat(broker): SIM 소수 shares → broker 계좌 규모 비례 스케일 (qty_scale_factor)
- `src/pretrend/pipeline/broker/order_manager.py`
  - `execute_from_ledger_rows()`에 `qty_scale_factor: float = 1.0` 파라미터 추가
  - `qty = max(0, round(raw_shares * qty_scale_factor))` — BUY/SELL 공통 적용
  - 기존 `int(shares)` 절사: SIM 소수 shares(예: SPY=0.183, IAU=0.871)가 모두 0으로 소멸
- `dags/broker_mock_trading_dag.py`
  - `qty_scale_factor = max(1.0, broker_budget_usd / sim_buy_total_usd)` 계산 후 전달
  - `broker_budget_usd = broker_nav_usd * PAPER_MAX_INVESTED_RATIO`
  - 실제 투자 한도는 `execute_from_ledger_rows()` 내부 `remaining_budget_usd`(기존 보유량 차감 후)가 cap

### 운영 관측 변화
- 기존: SIM ledger에 소수 shares인 종목들(SPY, IAU, USO 등)이 broker 주문 미발생
- 변경: broker 계좌 규모에 비례하여 모든 종목이 정수 수량으로 주문됨
- MOCK Telegram `"취소 실패"` 오경보가 FILLED 확인 시 `"이미 체결됨 확인"`으로 대체됨

## v2026.03.09g — P4-1a broker fills actual_filled_qty 반영

### feat(broker): fill inquiry 기반 실체결 수량 저장
- `src/pretrend/pipeline/broker/order_manager.py`
  - `check_and_cancel_unfilled()` 반환을 3-tuple로 고정:
    - `cancelled_df`
    - `fills_df_updated`
    - `warnings`
  - `fills_df_updated["actual_filled_qty"]` 컬럼 추가
  - `FILLED/PARTIAL_FILLED` 주문은 `_inquire_algo_ccnl()`의 `FT_CCLD_QTY` 합산값을 반영
  - `ACCEPTED -> cancel` 주문은 `actual_filled_qty=0.0`
  - fill inquiry가 비어 있으면 `actual_filled_qty=None` + warning 유지

### feat(broker-dag): broker fills parquet에 actual_filled_qty 포함
- `dags/broker_mock_trading_dag.py`
  - `check_and_cancel_unfilled(..., fills_df=fills_df, ...)` 호출로 갱신된 fills dataframe을 저장

### 운영 관측 변화
- `data/paper/MOCK/broker_fills/` parquet에 `actual_filled_qty` 컬럼이 추가될 수 있음
- 기존 `filled_qty`는 요청 수량이고, `actual_filled_qty`가 실체결 수량 정본 역할을 맡음

## v2026.03.09e — P3-5d broker mock financial metrics 근사 반영

### feat(broker-dag): MOCK Telegram PnL/원금 근사치 반영
- `dags/broker_mock_trading_dag.py`
  - `build_broker_result_payload_task`에 전일 `broker_bootstrap` 스냅샷 기반 `daily_pnl` 근사 계산 추가
  - `PAPER_INITIAL_CAPITAL_KRW + 월별 DCA` 기준 `cumulative_pnl`, `total_invested_capital` 근사 계산 추가
  - `broker_positions`가 비어 있으면 `포지션 없음(당일 미체결 가능성)` 문구를 position summary에 고정
  - 전일 스냅샷 부재 시 `daily_pnl=0.0` 근사치와 warning을 함께 기록

### feat(report): MOCK 전용 `(근사)` 라벨 명시
- `src/pretrend/pipeline/paper/report.py`
  - `execution_mode=MOCK`이고 값이 존재할 때:
    - `당일(근사)`
    - `누적(근사)`
    - `총투입원금(근사)`
  - SIM 렌더링은 변경하지 않음

### 운영 관측 변화
- MOCK Telegram에서 기존 `집계 데이터 없음` 대신 근사치가 우선 노출될 수 있음
- 포지션 미집계 상태는 단순 공백이 아니라 `포지션 없음(당일 미체결 가능성)`으로 표시됨
- 근사치임을 명시적으로 노출하여 broker snapshot 기반 계산임을 구분함

## v2026.03.09c — P3-5 broker mock 안정화: fill/cancel 버그 수정 + 미체결 취소 루프

### fix(broker): _place_order rt_cd 미검출 버그 수정
- `kis_mock.py` — `_place_order()` 내 `_raise_if_kis_error()` 누락 수정
  - KIS VTS HTTP 200 응답에서 `rt_cd ≠ 0` (예: 장마감) 시 `RuntimeError` 발생 (`execute_from_ledger_rows`에서 warn 처리)
  - 기존: `output.ODNO` 미수신 → `uuid.uuid4().hex[:12]` fallback → 유효하지 않은 ODNO로 inquire-algo-ccnl 500 체인 발생
  - 변경: `ODNO` 없을 때 `FAILED-{8자리hex}` prefix 사용 (명시적 실패 표시)
- `kis_mock.py` — `_inquire_algo_ccnl()` KIS 500 응답 graceful 처리 (`[]` 반환, `ACCEPTED` fallback)
- `order_manager.py` — `FAILED-` prefix order_id는 fill 상태 조회 없이 skip + warn

### feat(broker): 미체결 취소 루프 구현
- `order_manager.py` — `check_and_cancel_unfilled()` 추가
  - 대기 후 `ACCEPTED` → `cancel_order()` 실행, `PARTIAL_FILLED` → warn only
  - 대기 시간: `BROKER_FILL_WAIT_SEC` 환경변수 (기본값 `30`)
- `kis_mock.py` — `cancel_order()` KIS VTS 취소 API 연동 (`VTTT1004U` / `TTTT1004U`)

### 신규 환경변수
| 변수명 | 기본값 | 설명 |
|--------|--------|------|
| `BROKER_FILL_WAIT_SEC` | `30` | 미체결 취소 전 대기 시간(초) — `broker_mock_trading_dag` |

### 운영 관측 변화
- `data/paper/MOCK/broker_orders/` parquet의 `order_id` 컬럼에 `FAILED-XXXXXXXX` 형태 값이 기록될 수 있음 (KIS 장외 실행, API 오류 등)
- `FAILED-` prefix order는 fill check, cancel 없이 warn으로 처리되므로 DAG 실행은 계속됨

---

## v2026.03.09d — P3-5c broker mock market-hours gate

### feat(broker-dag): 미국 정규장 외 시간 broker mock 실행 skip
- `dags/broker_mock_trading_dag.py`
  - `load_sim_ledger_task` 앞단에 ET 기준 장 시간 게이트 추가
  - 평일 `09:30~16:00` 외 시간대와 주말은 `status="skipped"`, `reason="장외 시간"` 반환
  - `BROKER_SKIP_MARKET_HOURS_CHECK=1` 설정 시 테스트/수동 검증용 우회 허용
- 기존 `execute_broker_orders_task`의 `status != "ok"` skip 경로를 그대로 재사용하여 회귀를 피함

### test(broker-dag): 장중/장외/주말/우회 케이스 고정
- `tests/dags/test_broker_mock_trading_dag.py`
  - 장중 통과
  - 장전 skip
  - 주말 skip
  - env 우회 허용

## v2026.03.06a — P3-5a 선행 고정: Paper SIM/MOCK 분리 경계 문서화

### docs(contract): PAPER_RESULT 식별축 계약 추가
- `docs/architecture/paper_trading_alert_contract.md`
  - `execution_mode`, `capital_source`, `broker_source`, `account_id`, `nav_source` 필드 정의
  - SIM/MOCK 동시 운영 시 mode 식별축 필수 invariant 추가
  - renderer payload-only 원칙 명시

### docs(contract): Paper ledger key에 mode 축 추가
- `docs/architecture/paper_execution_ledger_contract.md`
  - `execution_ledger`, `positions_daily`, `portfolio_daily`에 `execution_mode` 컬럼 정의
  - portfolio/ledger에 source 메타(`capital_source`, `broker_source`, `account_id`, `nav_source`) 정의
  - Grain/Key를 mode 포함 형태로 고정해 동시 저장 충돌 방지 규칙 추가

### docs(operation): 운영 가이드 분리 원칙 반영
- `docs/operation_guide.md`
  - SIM/MOCK 동시 실행 + `PAPER_TELEGRAM_MODE` 분기 정책 명시
  - 식별 필드(`execution_mode`, `capital_source`, `broker_source`, `nav_source`) 운영 표기 규칙 추가
  - 환율 정책을 KIS 우선 + 내부 fallback(1300)으로 정리 (`PAPER_FX_USDKRW` 의존 문구 제거)

## v2026.03.05b — KIS+COD 1차/2차 운영 경로 정합화

### feat(broker): KIS 모드별 자격증명 우선순위 + 토큰 갱신 메타 추가
- `KIS_MOCK_*` / `KIS_LIVE_*` 우선, `KIS_APP_*` fallback으로 로딩 규칙 확장
- 토큰 만료 1시간 기준 55분 선제 갱신 정책 반영
- 401/403 응답 시 토큰 재발급 후 1회 재시도 경로 추가

### feat(paper): bootstrap/auth/fills/probe/candidate 저장 확장
- `paper_trading_dag`에서 아래 산출물 저장 추가
  - `data/paper/broker_bootstrap/decision_date=...`
  - `data/paper/broker_auth/decision_date=...`
  - `data/paper/broker_fills/decision_date=...`
  - `data/paper/market_probe/decision_date=...`
  - `data/paper/candidate_report/decision_date=...`
- COD 입력(`data/reference/kis_cod/*.COD`)을 파싱해:
  - `data/reference/kis_cod_parsed/decision_date=...`
  - `data/reference/kis_cod_etf/decision_date=...`
  - `data/reference/kis_cod_quality/decision_date=.../quality_*.json`

### feat(fx): KIS 환율(`fx_usdkrw`) 우선 적용 + daily 저장
- `KISMockAdapter.get_balance()`가 응답 payload에서 환율 키(`*exrt*`)를 추출하도록 확장
- `paper_trading_dag`에서 `data/paper/fx_daily/decision_date=...` 저장 추가
- KRW→USD 환산은 KIS 환율 우선, 결측 시 `PAPER_FX_USDKRW` fallback으로 동작

### test(broker): config/COD/order 경로 테스트 확장
- 신규:
  - `tests/pipeline/broker/test_kis_config.py`
  - `tests/pipeline/broker/test_cod_reference.py`
- 확장:
  - `tests/pipeline/broker/test_order_manager.py`
  - `tests/pipeline/broker/test_kis_mock_adapter.py`

## v2026.03.05a — P3-5 1차: Paper broker(KIS mock) 실행 경로 추가

### feat(broker): broker 모듈 스캐폴딩 + KIS mock 어댑터 추가
- 신규 모듈:
  - `src/pretrend/pipeline/broker/base.py`
  - `src/pretrend/pipeline/broker/kis_config.py`
  - `src/pretrend/pipeline/broker/kis_mock.py`
  - `src/pretrend/pipeline/broker/order_manager.py`
- 기본 동작은 `KIS_DRY_RUN=true` 기준으로 안전 실행되며, 실 API 장애 시 fail-open 경로를 유지

### feat(dag): `paper_trading_dag`에 브로커 주문/리컨실 task 추가
- 신규 task:
  - `execute_broker_orders` (옵션, `PAPER_BROKER_ENABLED=1`일 때만 실행)
  - `reconciliation` 저장 연동(`data/paper/reconciliation/decision_date=...`)
- 브로커 실패 시 paper 시뮬레이션/Telegram은 계속 진행(fail-open), 경고만 payload에 포함

### test(broker): 브로커 단위 테스트 추가
- 신규:
  - `tests/pipeline/broker/test_kis_mock_adapter.py`
  - `tests/pipeline/broker/test_order_manager.py`
  - `tests/pipeline/broker/test_paper_broker_e2e.py`
- 검증:
  - `conda run -n pytest-pretrend pytest tests/pipeline/broker/ -q` 통과
  - `conda run -n pytest-pretrend pytest tests/pipeline/paper/ -q` 회귀 통과

## v2026.03.04e — P3-6 prep: observer-only 용어/운영 경계 정리

### refactor(text-terms): `llm_feature` vs `interpretation_summary` 구분 고정
- `llm_feature`는 text-only LLM 산출물 묶음으로 유지
- `llm_summary`는 `llm_feature` 내부의 문서 요약 필드로 한정
- `interpretation_summary`는 signal snapshot + text snapshot 결합 해석문으로 고정

### docs(text): observer-only 경계 영구화
- `README.md`, `docs/operation_guide.md`, `.agent/*` 기준 문구를 영구 observer-only 원칙으로 정리
- `text_observability_contract.md §14`는 Gate H 임시 조건 대신 현행 운영 경계 기준으로 갱신

## v2026.03.04d — P3-3 AB 판정: Text overlay 운영 승격 보류

### result(backtest): `v2` vs `v2_text` 1차 비교 완료
- 비교 구간: `2006-01-03 ~ 2024-06-03`
- 산출물:
  - `result/backtest_compare/p3_3/v2/*`
  - `result/backtest_compare/p3_3/v2_text/*`
  - `result/backtest_compare/p3_3/compare_v2_v2_text_20260304.csv`

### 비교 결과
| Metric | v2 | v2_text | Delta |
| --- | --- | --- | --- |
| XIRR | `+7.74%` | `+7.33%` | `-0.41%p` |
| MDD | `-15.65%` | `-21.92%` | `-6.27%p` |
| Sharpe | `1.69` | `1.64` | `-0.047` |
| Trade Count | `5093` | `5180` | `+87` |

### 판정
- 구현은 완료
- 운영 승격은 보류

근거:
- `docs/architecture/text_strategy_connection_contract.md §9.4` 채택 기준 중 `MDD 악화 > 3%p`를 위반
- 따라서 Text는 현재 `observer-only`를 유지하고, `v2_text`는 실험 preset으로만 남긴다.

## v2026.03.04c — P3-3 implementation: Text→Strategy overlay 연결

### feat(strategy): Gold Text loader + text overlay snapshot 추가
- `src/pretrend/pipeline/strategy_engine/io.py`에 `load_gold_text()` 추가
- rule-based Gold와 Gold LLM을 병합 로드하고, 빈 입력은 fail-open 빈 DataFrame으로 반환
- `text_features/aggregator.py`, `text_features/signal.py` 추가
- `text_overlay_signal` snapshot을 `data/strategy/text_overlay_signal/decision_date=...`에 저장

### feat(strategy): policy_selection / Telegram / v2_text 연결
- `policy_selection`에 nullable text overlay 컬럼 추가
- `strategy_job.py`가 `text_overlay_signal -> policy_selection` 경로로 overlay를 통합
- Telegram SIGNAL의 `시장 근거` 섹션에 text 정보 1~2줄 추가
- backtest preset `v2_text` 추가: `v2 + text_signal_state`에 따른 `+/-0.05` soft adjustment

### test(strategy): text overlay 단위/회귀 테스트 추가
- 신규:
  - `tests/pipeline/strategy_engine/test_text_features.py`
- 확장:
  - `tests/pipeline/strategy_engine/test_strategy_job.py`
  - `tests/pipeline/strategy_engine/test_strategy_engine_dag_report.py`
  - `tests/pipeline/backtest/test_allocation_v3.py`

## v2026.03.04b — P3 design: Text→Strategy 연결 설계 확정

### docs(text-strategy): Overlay Signal 연결 방식 확정
- `docs/architecture/text_strategy_connection_contract.md` 신규 추가
- 3개 후보(Auxiliary / 5th Axis / Overlay) 비교 후 `Overlay Signal` 방식을 확정
- 연결 위치:
  - `Gold Text -> text_overlay_signal -> policy_selection`
- 기존 4축 / AHS / `run_universe` / `risk_gate` 의미는 유지

### docs(strategy): SECTION J 설계 고정
- `docs/strategy_engine_design.md` SECTION J에 P3 설계 확정 문구 추가
- Text는 hard gate를 대체하지 않고, `target_ratio`를 1 step(`+/-0.05`)만 soft adjustment 하도록 원칙 고정

### note(text-strategy): Gate H 이후 구현
- P3-3 구현 전제:
  - `text_pipeline_dag` 30거래일 연속 운영
  - rule-based 3종 `coverage_ratio` 중앙값 > `0.5`
  - AB backtest 비교 프로토콜 확정

## v2026.03.04a — P1 text: SEC Gold LLM 백필 완료 + SEC 페이지네이션 보강

### feat(text-backfill): SEC 8-K Gold LLM v2 백필 완료
- `gold_llm_backfill.py --source sec_edgar`로 SEC 2006~2026 Gold LLM 백필 완료
- 최종 집계:
  - `rows=40044`
  - `doc_ids=10011`
  - `prompt_version=text_annotation_v2`
- 품질 분포:
  - `llm_topics` 비율 95.4%
  - `llm_tags` 비율 6.3%

### feat(text-sec): SEC submissions 페이지네이션 지원
- `src/pretrend/pipeline/text/adapters/sec_edgar.py`가 `filings.recent`뿐 아니라 `filings.files`도 순회하도록 확장
- `date-range outside page` skip 최적화와 pagination fetch failure skip 로직 추가
- 공개 인터페이스(`fetch`, `source_name`)와 rate-limit(`0.11s delay`)는 유지

### test(text-sec): SEC adapter 페이지네이션 테스트 추가
- `tests/pipeline/text/test_sec_edgar_adapter.py` 신규 추가
- 검증 항목:
  - recent only
  - recent + paginated file
  - pagination file fetch failure skip
  - date-range outside skip
  - old filing from pagination included

### note(text-sec): live SEC 수동 검증
- mock/unit 수준 검증은 완료
- live SEC 수동 검증은 현재 환경 DNS 제한으로 별도 네트워크 가능한 환경에서 재확인 필요

## v2026.03.03b — P1 text: LLM Observer 활성화 + 백필 경로 확장

### feat(text-dag): `text_pipeline_dag` 추가
- `dags/text_pipeline_dag.py` 신규 추가
- `bronze(sec+fed) -> silver -> gold` 3단계 체인을 Airflow DAG로 고정

### feat(text-llm): Gold LLM Observer v1 구현
- `src/pretrend/pipeline/text/gold_llm_build.py` 추가
- Ollama 로컬(`llama3.1:latest`) 기반 `gold.text_llm_features` 저장 경로 구현
- fail-open 원칙 유지:
  - Ollama 미실행/응답 오류 시 rule-based Gold는 그대로 동작
  - LLM 산출물만 skip

### fix(text-silver): `has_html_markup` 판정 완화
- `silver_build.py`의 `has_html_markup` 검사를 Bronze `body`가 아닌 Silver `clean_text` 기준으로 변경
- HTML 원문이더라도 정제가 정상 완료된 문서는 `quality_flags="ok"`로 처리

### feat(text-backfill): SEC Index / FOMC Archive 백필 경로 추가
- `sec_edgar_index.py`, `fed_fomc_archive.py`, `backfill.py` 추가
- Bronze 백필 source:
  - `sec_index`
  - `fomc_archive`
- 실데이터 검증:
  - `data/bronze/text/sec_index`: `2006-12-31 ~ 2024-06-03`
  - `data/bronze/text/fomc_archive`: `2006-12-31 ~ 2024-06-03`
  - `data/gold/text/text_daily_features`: `2006-01-01 ~ 2026-02-20`

### test(text): LLM / fail-open / backfill 커버리지 확장
- `tests/pipeline/text/test_text_llm.py` 추가
- `tests/pipeline/text/test_text_backfill.py` 추가
- `tests/pipeline/text/test_text_failopen.py`에 LLM 장애 시나리오 추가
- 전체 회귀:
  - `526 passed, 4 skipped`

## v2026.03.03a — P1 paper: Level 2 guardrail 코드 구현

### feat(paper): Level 2 guardrail 상태 추적 및 매수 차단
- `simulate_paper_execution()` 반환값을 `ledger, positions, portfolio, guardrail_status`로 확장
- `portfolio_daily`에 아래 컬럼 추가:
  - `guardrail_paused`
  - `guardrail_nav_breach`
  - `guardrail_peak_dd_breach`
  - `guardrail_panic_streak`
  - `peak_nav`

### rules(paper): 실증 기반 임계값 적용
- 발동:
  - `NAV / total_invested_capital < 0.85`
  - `peak drawdown < -20%`
- 복귀:
  - `NAV / total_invested_capital >= 0.90`
  - `drawdown >= -15%`
- `PANIC streak >= 5`는 경고 전용으로 유지

### feat(alert): PAPER_RESULT risk warning 연동
- `dags/paper_trading_dag.py`에서 guardrail 메타를 Telegram warning으로 연결
- `🚨 Level 2 가드레일 발동` / `⚠️ PANIC n거래일 연속` 문구 노출

### test(paper): guardrail 회귀 검증 추가
- NAV breach / peak DD breach / auto resume / panic warning 시나리오 추가
- 관련 테스트:
  - `tests/pipeline/paper/test_execution_soft_gate.py`
  - `tests/pipeline/backtest/test_paper_execution_nav.py`
  - `tests/pipeline/backtest/test_paper_execution_positions.py`
  - `tests/pipeline/backtest/test_paper_execution_ledger.py`

## v2026.02.28a — P1 fix: paper 원자쓰기·커버리지·계약 앵커 일괄 반영 (commit ce965c3)

### fix(paper/io): INV-IDEMP-01 atomic write 복구
- `save_decision_partition()`에 `_tmp_{uuid}` 경유 + `Path.replace()` / `shutil.move()` fallback 적용
- 프로세스 중단 시 최종 파티션에 부분 파일 잔존 불가 보장

### test(paper): io/report 단위 테스트 신규 추가
- `tests/pipeline/paper/test_paper_io.py` 추가 (3건):
  - 원자쓰기 경로 검증 / 빈 입력 None 반환 / 파티션 경로 구조 검증
- `tests/pipeline/paper/test_paper_report.py` 추가 (4건):
  - 필수 필드 검증 / 최소 payload 생성 / 누락 필드 예외 / enum 케이스

### docs(group-transition): pos_ratio 임계값 계약 앵커
- `docs/architecture/group_transition_signal_contract.md §6`에 수치 기준 명시:
  - STRONG: `pos_ratio >= 0.5`, WEAK: `pos_ratio < 0.4`, UNKNOWN: `rs_values < 2`
- `tests/pipeline/strategy_engine/test_group_transition_engine.py`에 경계/fallback 테스트 2건 추가

### docs(paper-ledger): Level 2 운영 가드레일 신설
- `docs/architecture/paper_execution_ledger_contract.md`에 `§10 Level 2 운영 가드레일` 추가
- 중단 조건(NAV < initial_capital × 0.70) / 수동 승인 지점 / 복귀 조건 / 기록 의무 고정

## v2026.02.27d — P2-1 Universe-Stock(U0~U3) 계약 초안 정합화

### docs(universe): Research 확장 포트 명문화
- `docs/architecture/universe_contract.md`에 `§8 Universe-Stock(U0~U3) Extension Port (Research)` 추가
- 단계별 산출물 초안 명시:
  - `U0 macro_signal_event`
  - `U1 theme_priority_snapshot`
  - `U2 theme_stock_candidates`
  - `U3 stock_universe_snapshot`

### gateA(sync): Execution/Research key 격리 규칙 고정
- `Universe-ETF(Execution)` key(`rebalance_date, symbol`)와
  `Universe-Stock(Research)` key(`as_of_date` 기반)를 분리 명시
- 동일 테이블/파티션 공유 금지 원칙 문서화

### test(smoke): 계약 구조 검증 추가
- `tests/pipeline/strategy_engine/test_universe_stock_contract_smoke.py` 추가
- 계약 섹션 존재(U0~U3) + 그레인 분리 문구 존재 여부를 smoke 수준으로 검증

## v2026.02.27e — P2-2 Text v1+ 확장 체크리스트 정합화

### docs(text-contract): Gate D 체크리스트 추가
- `docs/architecture/text_observability_contract.md`에 `§12 v1+ 확장 체크리스트 (Gate D)` 추가
- 포함 항목:
  - External API: rate-limit/재시도, ToS/라이선스, secret 관리
  - fail-open: Text 결측 시 Strategy 3-state 독립 동작 보장
  - 운영 준비: 비용 상한/장애 fallback/changelog-operation_guide 동기화

### test(text-failopen): 혼합 소스 장애 지속성 검증
- `tests/pipeline/text/test_text_failopen.py`에 mixed source 시나리오 추가:
  - 한 소스(fetch 예외) 실패
  - 다른 소스(1건 반환) 성공
  - 파이프라인이 중단되지 않고 결과를 분리 보고하는지 확인

## v2026.02.27f — P2-3 LLM 해석 레이어 경계/폴백 고정

### docs(strategy/ops): LLM 적용 범위 제한 명시
- `strategy_engine_design.md` SECTION J Invariants에 아래 원칙 추가:
  - LLM은 문장 요약/해석 전용
  - 신호 판정/게이트/allocation 입력은 비LLM 규칙 경로 유지
  - LLM 장애 시 결정론 문구로 fallback
- `operation_guide.md`에 운영 정책 추가:
  - LLM 실패 시 DAG 성공 유지
  - 비용 상한 env(`PRETREND_LLM_DAILY_BUDGET_USD`) 관리

### test(fallback): 해석 문구 선택 fallback 경로 추가
- `report_context.py`에 `select_interpretation_text()` 추가
  - 유효 LLM 문구가 있으면 사용
  - 없으면 결정론 문구로 즉시 fallback
- `test_strategy_engine_dag_report.py`에 fallback 테스트 1건 추가

## v2026.02.27c — P1-1 지평별 bias 분화 품질 개선 (Gate A/B 반영)

### feat(next-step): horizon 분화 로직 강화
- `next_step` 지평별 계산에 임계/리스크/상태연령 보정 추가:
  - horizon threshold: 5D/10D/20D/60D/120D = `0.35/0.30/0.25/0.20/0.15`
  - hazard penalty (`hazard>=0.95`): `-0.10/-0.10/-0.08/-0.05/-0.05`
  - state-age damping (`age<3`): 5/10D long 기여 50% 감쇠, 60/120D short 기여 50% 감쇠
- `bias_20d` 실행축(state machine)과 하드게이트 semantics는 유지

### feat(next-step): 진단 컬럼 3종 추가(nullable)
- `horizon_bias_diversity_count`
- `horizon_bias_diversity_ratio_60d`
- `horizon_conf_spread`

### gate(compat/repro): 리스크 A/B 방어 규칙 적용
- Gate A(호환성): 기존 컬럼/타입/의미 변경 없이 nullable 컬럼만 추가
- Gate B(재현성): `horizon_bias_diversity_ratio_60d`는 row 시점 기준 과거 60개 row만 사용(look-ahead 금지)

### feat(signal): 다음 스텝 가설 출력 압축
- SIGNAL `다음 스텝 가설`을 `10D 상세 + 나머지 지평 요약 + 분화도 진단 1줄`로 고정
- snapshot 결측 시 `UNKNOWN/N/A` fail-open 유지

## v2026.02.27b — v3.4.2a 체류 규칙 완화 실험

### feat(next-step): v3.4.2a 실험 포트 메타 추가
- snapshot nullable 필드 확장:
  - `bias_candidate_20d`
  - `cooldown_compressed_flag`, `cooldown_compressed_reason`
  - `hard_gate_exit_assist_flag`, `hard_gate_exit_assist_reason`
- 의미:
  - 체류 완화 후보를 next_step에서 기록하고, 실제 적용은 소비자(backtest/paper preset=`v3.4.2a`)에서 수행

### feat(backtest/paper): `v3.4.2a` preset 추가
- `PRESET_REGISTRY`/`ALLOCATION_REGISTRY`에 `v3.4.2a` 등록
- 적용 규칙(soft-only):
  - `cooldown_compressed_flag=true` + `bias_state_source=HOLD_COOLDOWN`이면 `bias_candidate_20d` 적용
  - `hard_gate_exit_assist_flag=true` + `bias=RISK_OFF_BIAS`이면 `NEUTRAL_BIAS` 1단 완화
- 하드게이트 우선(`run_universe`, `risk_gate`) 불변 유지

### feat(paper-result): 체류 완화 메타 노출 확장
- PAPER_RESULT 게이트/강도 섹션에 아래 항목 추가(있을 때만):
  - `Cooldown 압축`
  - `Hard-gate Exit Assist`

### docs(sync)
- `next_step_signal_contract.md`: v3.4.2a 확장 포트/DoD/Change History 반영
- `allocation_engine_contract.md`: v3.4.2a 규칙/DoD/Change History 반영
- `paper_execution_ledger_contract.md`: v3.4.2a 체류 완화 규칙/DoD 반영
- `operation_guide.md`, `README.md`: `--preset v3.4.2a` 설명 추가

### backtest(compare): v3.4.1/v3.4.2-phase/v3.4.2a 재검증
- 실행 전 `strategy_job --date 2026-02-25`로 `next_step_signal` 재생성(신규 메타 필드 반영) 후 비교 재실행.
- 저장:
  - `result/backtest_compare/compare_v341_v342phase_v342a_20260227.csv`
  - `result/backtest_compare/diag_switch_cooldown_20260227.csv`
  - `result/backtest_compare/diag_switch_fwd_returns_20260227.csv`
  - `result/backtest_compare/diag_drawdown_source_mix_20260227.csv`
  - `result/backtest_compare/diag_cooldown_compression_20260227.csv`
- 핵심 결과:
  - `v3.4.2a`는 장기/최근 모두 `v3.4.2-phase`와 성과 동일(액션 변화 미발생)
  - 운영 기준은 `v3.4.1` 유지

## v2026.02.27 — Phase-aware Bias 상태머신 도입 (v3.4.2-phase)

### feat(next-step): `bias_20d` phase-aware state machine 적용
- baseline 규칙 고정:
  - `EXPANSION/LATE_CYCLE/UNKNOWN -> NEUTRAL_BIAS`
  - `RECOVERY -> RISK_ON_BIAS` (회복기 참여 강화)
  - `SLOWDOWN/RECESSION -> RISK_OFF_BIAS`
- overlay 점수:
  - `mid=RISK_ON:+2`, `mid=RISK_OFF:-2`
  - `short=RELIEF:+1`, `short=PANIC:-2`
  - `hazard_10d>=0.95:-1` (결측은 0, fail-open)
- weekly cadence + 안정화:
  - 월요일만 판정, 비월요일 hold
  - hysteresis(진입 `>=+2`/`<=-2`, 해제 `<=0`/`>=0`)
  - cooldown 5거래일
- 하드게이트 우선:
  - `run_universe=false`면 실행 관점 `RISK_OFF_BIAS` 우선

### feat(schema/message): 상태머신 메타 4개 필드 추가
- next_step snapshot 확장(nullable):
  - `bias_state_source`
  - `bias_switch_flag`
  - `bias_switch_reason`
  - `bias_cooldown_left`
- SIGNAL/PAPER 메시지에 bias state 라인 추가:
  - `source/switch/reason/cooldown`

### feat(backtest): 실험 preset `v3.4.2-phase` 추가
- `PRESET_REGISTRY` 및 `ALLOCATION_REGISTRY`에 `v3.4.2-phase` 등록
- runner 모드 플래그:
  - phase-aware bias는 `next_step` snapshot에서 소비
  - runner 내부 monthly/shock/hazard 오버레이는 비활성화
  - group gate는 유지

### test(sync)
- `test_next_step_engine.py`: RECOVERY baseline, weekly hold, hard gate 우선 검증 추가
- `test_strategy_engine_dag_report.py`: bias state 라인 렌더/결측 fallback 검증 추가
- `test_paper_trading_report.py`: PAPER 메시지 bias state 라인 검증 추가
- `test_allocation_v3.py`: `v3.4.2-phase` dispatch 경로 검증 추가

## v2026.02.26 — 계약/정합성/운영 안정화 배치 (P0-2~P0-5)

### P0-2: backtest/report.py 원자 쓰기(임시 스테이징) 적용
- `save_result()`를 임시 디렉토리(`{stem}_tmp_{run_id}`)에 먼저 기록 후 최종 경로로 이동하도록 변경
- registry append는 아티팩트 이동 완료 후 실행되도록 순서 보정

### P0-3: paper 경계 명문화 + SIGNAL 8섹션 운영 문서화
- `paper_trading_alert_contract.md`에 canonical 구현 경로(`pipeline.paper.execution`) 명시
- `backtest/paper_execution.py` shim 경계 유지 + 운영 가이드에 SIGNAL 8섹션 구조 반영

### P0-4: Walk-forward Tier-1 임계값 유효화
- `walk_forward` 기준을 `Sharpe >= 0.30`, `MDD >= -0.30`으로 보정(기존 0.0/ -0.35 대비 변별력 강화)
- 계약 문서에 임계값 수치 앵커를 동기화

### P0-5: EOD Observability 정합화 + BOND 풀 확장
- Observability universe에 `HYG/LQD/SHY/TIP`를 추가해 BOND 전술 풀 정합화
- 코드 주석/계약 테이블/테스트 수량 검증을 동일 기준으로 정렬

## v2026.02.26c — 전이예측 지평 재정의 (거래일 5축 통일)

### feat(next-step): 지평 체계 `5/10/20/60/120D`로 통일
- 혼합 표기(`1M/3M`) 대신 거래일 기반 지평으로 통일
- 신규 필드:
  - `bias_5d/10d/20d/60d/120d`
  - `confidence_5d/10d/20d/60d/120d`
  - `sojourn_prob_60d/120d`
  - `transition_hazard_60d/120d`
  - `transition_expected_5d/10d/20d/60d/120d`
- Breaking:
  - `bias_1m/3m`, `confidence_1m/3m`, `transition_expected` 제거
  - 실행/소비 경로는 `bias_20d` 단일 기준으로 통일

### feat(signal/paper/backtest): 소비 키 `20D bias` 우선화
- backtest/paper soft gate 입력을 `bias_20d` 우선으로 변경
- `bias_1m` fallback alias 제거
- SIGNAL `다음 스텝 가설`은 5축(5/10/20/60/120D) bias/hazard/expected 동시 출력

### feat(migration): next_step 지평 마이그레이션 스크립트 추가
- `scripts/migrate_next_step_horizons.py`
  - `--dry-run`: 변경 대상/컬럼 계획 출력
  - `--apply`: `1m->20d`, `3m->60d`, `transition_expected->transition_expected_20d` 매핑 후 구 컬럼 제거

### docs(sync)
- 계약/운영 문서에서 지평 표기를 `5/10/20/60/120D`로 통일

## v2026.02.26b — v3.4.1 회복기 재진입 강화 실험

### feat(backtest/paper): v3.4.1 preset 추가
- `PRESET_V3_4_1` 등록 (`v3.4 + recovery-aware re-entry gate`)
- allocation registry에 `v3.4.1 -> compute_allocation_v3` 연결
- v3.4.1은 v3.1/v3.2/v3.3/v3.4 체인을 유지한 상태에서 group gate만 강화

### feat(gate): WEAK>=2 진입 + 재진입 조건 고정
- 축소 진입: `group_state_now=WEAK` 그룹 수가 2개 이상일 때만 발동
- 축소 해제(재진입): 아래 중 하나 충족 시 복원
  - `short_signal=RELIEF` 2거래일 연속
  - `mid_regime=RISK_ON`
- 재진입 전까지 축소 상태 유지(soft gate 상태 유지)
- group_transition 결측 시 fail-open(`group_gate_source=MISSING`, v3.3 경로 유지)

### test(sync): v3.4.1 단위/회귀 검증 추가
- backtest: mode flags, WEAK>=2 진입, RELIEF streak 재진입 검증
- paper: v3.4.1 group gate helper(WEAK=1 미발동, MID=RISK_ON 재진입) 검증
- allocation: `v3.4.1` dispatch 경로 검증

### docs(sync)
- `allocation_engine_contract.md`: v3.4.1 규칙/DoD/이력 반영
- `paper_execution_ledger_contract.md`: 재진입 규칙 반영
- `operation_guide.md`, `README.md`: `--preset v3.4.1` 실행/설명 추가

### backtest(compare): v3.3/v3.4/v3.4.1 2구간 비교 저장
- 저장 경로:
  - `result/backtest_compare/long_20060103-20240603/*`
  - `result/backtest_compare/recent_20250101-20260101/*`
  - `result/backtest_compare/compare_v33_v34_v341_2windows_20260226.csv`
- 핵심 결과:

| Window | Preset | CAGR | MDD | Sharpe | XIRR | Trades |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 2006-01~2024-06 | v3.3 | 30.93% | -14.56% | 1.69 | 7.54% | 5,323 |
| 2006-01~2024-06 | v3.4 | 30.59% | -19.10% | 1.68 | 7.10% | 4,380 |
| 2006-01~2024-06 | v3.4.1 | 31.16% | -15.46% | 1.71 | 7.85% | 5,030 |
| 2025-01~2026-01 | v3.3 | 390.02% | -6.30% | 3.34 | 21.43% | 282 |
| 2025-01~2026-01 | v3.4 | 409.42% | -6.26% | 3.43 | 29.04% | 261 |
| 2025-01~2026-01 | v3.4.1 | 392.49% | -6.30% | 3.36 | 22.39% | 278 |

## v2026.02.26 — Tactical Asset Group 전이예측(v3.4) 도입

### feat(strategy): group_transition_signal 스냅샷/히스토리 추가
- 신규 모듈 추가:
  - `strategy_engine/group_transition/schema.py`
  - `strategy_engine/group_transition/engine.py`
  - `strategy_engine/group_transition/io.py`
  - `strategy_engine/group_transition/history_io.py`
- `strategy_job.py`에 그룹 전이 생성/저장 단계 추가:
  - snapshot: `data/strategy/group_transition_signal/decision_date=...`
  - history: `data/strategy/group_transition_history/year=.../month=...`
- grain/key:
  - snapshot `(trade_date, asset_group)`
  - history `(trade_date, asset_group, decision_date_ref)`

### feat(signal): Telegram에 `전술 그룹 다음 스텝` 섹션 추가
- `strategy_engine_dag` SIGNAL 메시지에 그룹별 10D 요약 노출:
  - `STATE_NOW -> EXPECTED_10D`
  - `group_transition_hazard_10d`
- 결측 시 fail-open 문구 고정:
  - `전술 그룹 전이 데이터 없음 (UNKNOWN/N/A)`

### feat(paper/backtest): v3.4 group transition soft gate 연결
- `PRESET_V3_4` 추가 (`v3.3 + group transition gate`)
- backtest runner:
  - WEAK 그룹 tactical 축소(그룹 제외 + slots/weight 완화)
  - 결측 시 fail-open(v3.3 경로 유지)
- paper execution:
  - predictor soft gate 이후 group transition gate 적용
- PAPER_RESULT:
  - `전술 적용 근거` 섹션 추가 (`적용 그룹/축소 그룹/게이트 소스`)

### docs(contracts/ops): SOT 동기화
- 신규 계약: `docs/architecture/group_transition_signal_contract.md`
- 기존 계약/운영 문서 동기화:
  - `next_step_signal_contract.md` (scope 분리)
  - `allocation_engine_contract.md` (v3.4 규칙/DoD)
  - `paper_execution_ledger_contract.md` (group transition 입력)
  - `operation_guide.md`, `README.md`

## v2026.02.25c — Telegram next-step 단일소스 통일 + hazard 가시화

### feat(signal): next_step fallback 재계산 제거
- `strategy_engine_dag`의 `다음 스텝 가설` 섹션을 snapshot 단일소스로 통일
- `next_step_signal` 결측 시 `_build_next_step_lines` 재계산 대신 `UNKNOWN/N/A` fail-open 렌더링
- warning 로그 추가:
  - decision_date 기준 next_step snapshot 부재 시 1회 경고

### feat(signal): 5/10/20D transition_hazard + transition_expected 표시
- SIGNAL 메시지에 아래 라인 추가:
  - `⏱ 5D/10D/20D 전환위험`
  - `🔭 예상 전이`
- 값은 `next_step_signal` 컬럼(`transition_hazard_*`, `transition_expected`) 직접 소비

### feat(paper): PAPER_RESULT 게이트/강도 설명 필드 확장
- paper payload optional 필드 추가:
  - `effective_bias`, `bias_source`, `override_reason`
  - `hard_gate_run_universe`, `hard_gate_risk_gate`
  - `effective_max_tactical_slots`, `effective_tactical_weight`, `hazard_10d`
- PAPER_RESULT 메시지에 `게이트/강도` 섹션 추가
- 표시 계층과 계산 계층 분리 유지(계산 규칙은 execution contract 참조)

### fix(paper): KRW 운영조건의 USD 과대집행 수정
- paper execution 입력(`초기자금 1,000,000원`, `월 DCA 300,000원`)을 USD 가격계산에 직접 사용하던 문제 수정
- `PAPER_FX_USDKRW`(기본 1300) 기준으로 KRW→USD 환산 후 체결 계산하도록 변경
- PAPER_RESULT 메시지 `운영 조건`에 환산 환율 라인 추가

### ux(signal/paper): 예상 전이 가독성 + paper 시작일 표시
- SIGNAL `예상 전이`를 `RECESSION_NEUTRAL_RELIEF` 원문 대신
  `장기/중기/단기` 3축 설명형으로 렌더링
- PAPER_RESULT `운영 조건`에 `Paper 시작일(PAPER_START_DATE)` 표시 추가

## v2026.02.25b — 재현성 저장 체계 고도화 (Feature Snapshot + Result Registry)

### feat(strategy): next_step_history 저장 계층 추가
- `next_step_history` 증분/전체 저장 I/O 추가
  - 경로: `data/strategy/next_step_history/year=YYYY/month=MM/*.parquet`
  - key: `(trade_date, decision_date_ref)`
- Strategy DAG에 `build_next_step_history_incremental` 태스크 추가
  - history 저장 실패는 fail-open(경고 로그, SIGNAL 전송 유지)

### feat(backtest/paper): 결과 아티팩트 표준화 + registry(parquet partition) 추가
- `save_result()` 표준 산출물 확장:
  - `*_daily_nav.parquet`, `*_summary_metrics.{parquet,json}`, `*_diagnostics.parquet`, `*_final_positions.parquet`
  - 기존 `*_metrics.json` 유지(하위호환)
- `save_walk_forward()` 및 paper payload 저장 시 registry entry를 append
  - 저장 경로: `PRETREND_RESULT_ROOT/backtest/registry/pipeline=*/run_date=*/registry.parquet`
  - 중복키 방지: `(pipeline, preset, start_date, end_date, decision_date_ref, code_version)`

### feat(paper): next_step 조회를 snapshot+history 결합 로더로 통일
- `paper_trading_dag`에서 `next_step_signal` 단독 로드 대신 runtime 결합 로더 사용
- 결측 시 fail-open 경로 유지(기존 soft gate fallback)

### docs(sync)
- 계약/운영 문서에 저장본 우선 소비 + fallback 규칙 명시
- walk-forward 계약에 `hazard_non_null_ratio` 및 저장 비교 검증 항목 추가

### tune(v3.3): hazard threshold 기본값 상향
- `PRETREND_HAZARD_THRESHOLD_10D` 기본값을 `0.35 -> 0.95`로 상향
- 의도: hazard 포화 구간에서 v3.3 억제 게이트가 실제로 작동하도록 운영 기본값 보정
- 환경변수로 즉시 override 가능(`PRETREND_HAZARD_THRESHOLD_10D=<value>`)

### docs(sync): 백테스트 아티팩트 저장/검증 절차 명시
- `BacktestRunner().run()` 단독 호출은 저장 아티팩트를 생성하지 않음을 운영 가이드에 명시
- `save_result()` 표준 산출물(9종)과 registry 경로를 고정 문서화
- 기간 포함 권장 저장 경로 추가:
  - `result/backtest_compare/<window>_<YYYYMMDD-YYYYMMDD>/<preset>/`

## v2026.02.25 — Paper Trading Telegram 분리 전송 (SIGNAL/PAPER_RESULT)

### feat(strategy/backtest/paper): 전이예측 운용 게이트 승격 + v3 연계
- `next_step_signal`를 운용 게이트 입력으로 승격
  - `strategy_job.py`에 `next_step_signal` snapshot 저장 단계 추가
  - 저장 경로: `data/strategy/next_step_signal/decision_date=...`
- `paper` 모듈 분리:
  - `src/pretrend/pipeline/paper/execution.py`
  - `src/pretrend/pipeline/paper/report.py`
  - `src/pretrend/pipeline/paper/io.py`
  - 기존 `backtest/paper_*` 경로는 backward-compat shim으로 유지
- `paper_trading_dag.py`가 `next_step_signal`을 입력으로 받아 soft gate 적용
  - `RISK_ON_BIAS`: tactical 기본 강도
  - `NEUTRAL_BIAS`: tactical 완화
  - `RISK_OFF_BIAS`: tactical 축소/코어 우선
  - 하드 게이트(`run_universe`, `risk_gate`) 우선
- `Backtest Allocation v3` 추가
  - `PRESET_V3` 등록
  - `compute_allocation_v3()` 구현 (`f(long_phase, mid_regime, next_step_bias_1m)`)
  - `runner.py`가 `next_step_signal snapshot`을 policy row에 부착해 v3 입력으로 사용
- `walk_forward.py`가 v3에서 `next_step_signal` 진단 컬럼을 우선 사용하도록 확장

### docs(contracts): 전이예측 기능축 SOT 고정
- `next_step_signal_contract.md`: 운용 게이트 입력 지위 + soft gate 규칙 명시
- `paper_execution_ledger_contract.md`: next_step 입력/우선순위(하드게이트 우선) 명시
- `allocation_engine_contract.md`: v3 포트(`f(long, mid, next_step_bias_1m)`) 추가
- `walk_forward_validation_contract.md`: v3 입력 소스 `next_step_signal snapshot` 고정

### docs(architecture): Paper Trading 계약 분리 (Alert / Execution Ledger)
- `docs/architecture/paper_trading_alert_contract.md` 신규 추가
  - 동일 Telegram 채널에서 `SIGNAL`/`PAPER_RESULT`를 `message_type`으로 분리
  - `paper_trading_dag`는 일 1회 EOD 전송으로 고정
  - Telegram 전송 실패 정책을 fail-open으로 고정
- `docs/architecture/paper_execution_ledger_contract.md` 신규 추가
  - EOD 가상 체결 원장(`execution_ledger`) + 포지션(`positions_daily`) + NAV(`portfolio_daily`) 계약 정의
  - 운영 조건 고정: 초기자금 1,000,000원, 월 DCA 300,000원, 화요일 매수/금요일 분할매도, SCHD 매도 금지

### feat(dag): `paper_trading_dag` 신규 추가 + `strategy_engine_dag` 메타필드 보강
- `dags/paper_trading_dag.py` 신규
  - `build_paper_result_payload` → `send_paper_result_telegram` 2-task 구조
  - payload 공통 필드 고정: `message_type`, `source_job`, `decision_date`, `simulation_date`
  - PAPER_RESULT 섹션 고정: 가상 체결 요약 / PnL 요약 / 포지션 변화 / 리스크 경고(있을 때만)
- `dags/strategy_engine_dag.py`
  - SIGNAL 메시지에도 공통 메타필드(`message_type=SIGNAL`, `source_job`, 날짜 필드) 추가
  - Telegram 전송 경로를 fail-open 공통 유틸로 전환
  - `paper_trading_dag` 입력 정리: 최신 decision_date 기준 dedupe + `PAPER_START_DATE`(기본 2026-01-01) 이후 구간만 누적 실행

### feat(notify/paper): 공통 전송 유틸 + PAPER_RESULT 렌더러/실행 레이어 추가
- `src/pretrend/pipeline/notify/telegram_sender.py` 추가
  - `send_telegram_fail_open()` 공통 유틸 제공
- `src/pretrend/pipeline/paper/report.py` 추가
  - PAPER_RESULT payload 생성/검증/메시지 포맷팅 함수 제공 (NAV/상위보유 포함)
- `src/pretrend/pipeline/paper/execution.py` 추가
  - EOD 가상 체결 시뮬레이션, NAV/PNL 계산, 포지션 상세 산출
  - tactical universe 반영(`policy_selection` + `what_to_hold`) 및 `SCHD` 매도 금지 적용
- `src/pretrend/pipeline/paper/io.py` 추가
  - strategy snapshot dedupe 로드 + paper 파티션 저장 공통화
- 호환성:
  - `src/pretrend/pipeline/backtest/paper_execution.py`, `paper_trading_report.py`는 shim으로 유지

### test: PAPER_RESULT 포맷/전송 정책 테스트 추가
- `tests/pipeline/backtest/test_paper_trading_report.py` 신규
  - 필수 필드 검증, 포맷 섹션/결측 fallback 검증
- `tests/pipeline/backtest/test_paper_execution_nav.py` 신규
- `tests/pipeline/backtest/test_paper_execution_ledger.py` 신규
- `tests/pipeline/backtest/test_paper_execution_positions.py` 신규
- `tests/dags/test_telegram_send_policy.py` 신규
  - 토큰 미설정/전송 예외 시 fail-open 검증
- `tests/dags/test_paper_trading_dag.py` 신규

### docs(operation/readme): 운영 가이드 동기화
- `docs/operation_guide.md` DAG 스케줄 표에 `paper_trading_dag` 추가
- Telegram `message_type` 구분 및 fail-open 정책 명시
- `README.md` Airflow DAG 목록/특징 섹션 업데이트

### feat(backtest): v3.1 정식화 + v3.2(shock override) 추가
- `v3.1`:
  - v3 규칙 + monthly bias lock(동일 월 고정, 월 변경 시 갱신)
- `v3.2`:
  - v3.1 기본을 유지하면서 shock override 추가
  - 트리거:
    - `short_signal=PANIC` 2거래일 연속 → `RISK_OFF_BIAS`
    - `mid_regime=RISK_OFF` 3거래일 연속 → `NEUTRAL_BIAS`
  - cooldown: override 발동 후 5거래일 재전환 금지
  - 하드 게이트 우선(`run_universe`, `risk_gate`) 원칙 유지

### docs(contracts): v3.1/v3.2 반영
- `docs/architecture/allocation_engine_contract.md`
  - mode 규칙에 v3.1/v3.2 추가
  - DoD 확장: `AE-v3.1`, `AE-v3.2`
- `docs/architecture/next_step_signal_contract.md`
  - `Hypothesis (v3.2 Extension)` 섹션 추가
  - 확장 필드(nullable): `bias_effective`, `bias_override_flag`, `bias_override_reason`

### backtest 비교 결과 (실측, DCA $300/월)

#### 장기 구간 (2006-01-03 ~ 2024-06-03)
| preset | NAV | CAGR | MDD | Sharpe | XIRR | Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| v2 | 138,532.13 | 0.307059 | -0.156492 | 1.677539 | 0.072464 | 5028 |
| v3 | 151,934.26 | 0.313630 | -0.149914 | 1.743245 | 0.081184 | 5216 |
| v3.1 | 146,203.78 | 0.310890 | -0.128940 | 1.718228 | 0.077565 | 5427 |
| v3.2 | 141,938.90 | 0.308784 | -0.145575 | 1.684377 | 0.074767 | 5317 |

#### 최근 구간 (2025-01-01 ~ 2026-01-01)
| preset | NAV | CAGR | MDD | Sharpe | XIRR | Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| v2 | 4,854.81 | 3.902588 | -0.063001 | 3.345189 | 0.215203 | 276 |
| v3 | 4,782.57 | 3.829188 | -0.081856 | 3.280359 | 0.186665 | 291 |
| v3.1 | 4,788.91 | 3.835629 | -0.081859 | 3.291050 | 0.189163 | 282 |
| v3.2 | 4,852.43 | 3.900169 | -0.062999 | 3.344024 | 0.214260 | 282 |

### 진단 지표 (최근 구간)
- `RISK_OFF_BIAS` 이후 SPY 평균 선행수익:
  - +5d: `+1.0764%` (n=60)
  - +10d: `+1.9300%` (n=60)
  - +20d: `+2.4388%` (n=60)
- v3.2 override 빈도(2025-01-01~2026-01-01):
  - override days: `17 / 250`
  - reason 분해: `PANIC=0`, `RISK_OFF=17`
- v3.2 일수익률(override vs non-override):
  - override days mean: `0.4454%` (n=17)
  - non-override days mean: `0.6972%` (n=233)

### feat(strategy/backtest): v3.3 Duration/Transition MVP (규칙 기반, 5/10/20d)
- `next_step_signal` 확장 필드 추가(nullable):
  - `state_age_days`
  - `sojourn_prob_5d/10d/20d`
  - `transition_hazard_5d/10d/20d`
  - `transition_expected`
- `v3.3` preset 추가:
  - v3.2 shock override 유지
  - `transition_hazard_10d` 임계치 기반 hazard-aware override 게이트 추가
  - hazard 결측 시 fail-open으로 v3.2 경로 유지
- `walk_forward` Tier-2 진단 확장:
  - `diag_calibration_error` (간이 Brier)
  - `diag_hazard_bucket_monotonicity` (high-low 단조성)

### docs(contracts): v3.3 가설 확장
- `next_step_signal_contract.md`
  - `Hypothesis (v3.3 Duration/Transition MVP)` 섹션 추가
  - duration/transition 확장 포트 및 fail-open 원칙 명시
- `allocation_engine_contract.md`
  - v3.3 hazard-aware override 가설 규칙 추가
  - `AE-v3.3-hypothesis` DoD 추가
- `walk_forward_validation_contract.md`
  - Tier-2 hazard 품질 KPI 추가

### v3.3 성과 비교 (실측, DCA $300/월)
| Window | v3.2 NAV | v3.3 NAV | v3.2 CAGR | v3.3 CAGR | v3.2 MDD | v3.3 MDD | v3.2 Sharpe | v3.3 Sharpe |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2006-01-03 ~ 2024-06-03 | 141,938.90 | 141,938.90 | 0.308784 | 0.308784 | -0.145575 | -0.145575 | 1.684377 | 1.684377 |
| 2025-01-01 ~ 2026-01-01 | 4,852.43 | 4,852.43 | 3.900169 | 3.900169 | -0.062999 | -0.062999 | 3.344024 | 3.344024 |

판단:
- 현재 snapshot에서 `transition_hazard_10d` 결측 구간이 많아 v3.3이 fail-open(v3.2 동일 경로)으로 동작했다.
- 운영 채택은 유지(`v3.2`), `v3.3`은 shadow/진단 모드로 축적 후 재평가한다.

## v2026.02.24 — 전이예측 계약 보강 (Tier-1 성과 + Tier-2 12셀 진단)

### docs(architecture): 전이예측/검증 계약 신규 추가
- `docs/architecture/next_step_signal_contract.md` 신규 추가
  - 3-state(long/mid/short) 기반 다음 스텝 가설(1m/3m) 출력 계약 정의
  - 4축 근거 서술 필드(`매크로/가격/수급/심리`) 고정
  - 12셀(4x3)을 실행 신호가 아닌 **진단 KPI 계층**으로 명시
- `docs/architecture/walk_forward_validation_contract.md` 신규 추가
  - Tier-1(성과 KPI) + Tier-2(진단 KPI) 이중 검증 구조 정의
  - 상태 전이 규칙 고정:
    - Tier-1 통과 + Tier-2 경고 없음 → `PASS`
    - Tier-1 통과 + Tier-2 경고 있음 → `PASS_WITH_WARNING`
    - Tier-1 실패 → `FAIL`

### feat(strategy_engine): Telegram 보고에 다음 스텝/진단 섹션 추가
- `report_context.py`
  - `build_next_step_lines()` 추가 (1M/3M 결정론 가설)
  - `build_diagnostic_lines()` 추가 (12셀 품질/coverage 요약)
- `dags/strategy_engine_dag.py`
  - 기존 `시장 컨텍스트` + `시장 근거` 유지
  - `다음 스텝 가설`, `진단 요약` 섹션 추가

### feat(backtest): Walk-forward 이중 검증 출력 확장
- `walk_forward.py`
  - 진단 컬럼 추가: `diag_12slot_coverage`, `diag_unknown_ratio`, `diag_axis_consistency`
  - 상태 컬럼 추가: `tier1_pass`, `tier2_warning`, `validation_status`
  - 진단 결측 시 fail-open (`tier2_warning=False`) 처리
- `report.py`
  - `validation_status` 존재 시 요약 테이블/카운트 출력

### test: 계약/전이 규칙 회귀 테스트 추가
- `tests/pipeline/strategy_engine/test_next_step_signal.py` 신규
  - 4축 근거 문구 생성/결측 fail-open/next-step bias 검증
- `tests/pipeline/strategy_engine/test_strategy_engine_dag_report.py` 확장
  - 1M/3M 가설 라인, 12셀 진단 라인 출력 검증
- `tests/pipeline/backtest/test_walk_forward.py` 확장
  - `PASS_WITH_WARNING`, `FAIL`, 진단 결측 fallback 검증

## v2026.02.23 — Telegram 보고 포맷 고도화 (컨텍스트 3줄 + 근거 4축)

### feat(strategy_engine): AHS detail_json 저장 추가
- `axis_horizon_state` 스키마에 아래 컬럼 추가:
  - `long_detail_json`
  - `mid_detail_json`
  - `short_detail_json`
- Long/Mid/Short 엔진에서 상태 판정 근거를 JSON 문자열로 저장
  - Long: `regime_mode`, `regime_votes`, `delta_6m_z_mean`, `z_threshold`, fallback 여부
  - Mid: `price_signal`, `macro_signal`, `breadth_signal`, `majority_source`, `breadth_spread`
  - Short: primary/secondary 판정, confirmation count/list, `smallcap_stress` 등
- 하위 호환: 과거 스냅샷(신규 컬럼 없음)은 DAG fallback 문구로 안전 처리

### feat(dag): Telegram 메시지 `시장 컨텍스트 + 시장 근거` 포맷 확장
- 기존 `시장` 상태 표시를 `시장 컨텍스트` 섹션으로 정리:
  - 장기/중기/단기 3줄 + 요약 설명 문장
- 신규 `시장 근거` 섹션 추가(항상 4줄):
  - `매크로,정책`
  - `가격`
  - `수급/구조`
  - `심리`
- detail JSON 누락/파싱 실패 시 기본 문구 고정:
  - `영향 근거 없음`
- LLM 호출 없이 결정론적 템플릿으로 렌더링

### test: AHS detail 및 Telegram 포맷 회귀 테스트 추가
- `tests/pipeline/strategy_engine/test_axis_horizon_state.py`
  - detail_json 컬럼 존재/JSON 유효성 검증
- `tests/pipeline/strategy_engine/test_mid_engine.py`
  - mid detail에 signal source/value 반영 검증
- `tests/pipeline/strategy_engine/test_short_engine.py`
  - short detail에 confirmation/smallcap 필드 반영 검증
- `tests/pipeline/strategy_engine/test_strategy_engine_dag_report.py`
  - 컨텍스트 3축 표시 검증
  - 근거 4축 fallback(`영향 근거 없음`) 검증

### docs/telegram: 용어 혼동 제거 표기 정비
- Telegram 컨텍스트 문구를 아래 별칭으로 통일:
  - `중기 성향` (`mid_regime`)
  - `단기 공황 여부` (`is_panic = not risk_gate`)
  - `전술 실행` (`run_universe`: 허용/제한)
- 내부 스키마/로직(`risk_gate`, `run_universe`, `mid_regime`)은 그대로 유지
- 목적: 상태 라벨과 실행 스위치의 의미를 분리해 사용자 해석 혼동 최소화

## v2026.02.22c — Mid Engine v1.1 spread 버그 수정 + Short Engine 보강

### fix(strategy_engine): Mid Engine breadth 부호 반전 버그 수정 (v1.1)
- 원인: `breadth_iwm_spy_ratio = iwm_ret_20d / spy_ret_20d`는 `spy_ret_20d < 0` 구간에서 부호/해석 반전 발생
  - 예: `SPY=-5%`, `IWM=-3%` → ratio=0.6 (기존 로직은 `RISK_OFF` 오판정)
- 수정:
  - `flow_structure.py`: `_compute_breadth_ratio()` → `_compute_breadth_spread()`
  - 계산식: `breadth_iwm_spy_spread = iwm_ret_20d - spy_ret_20d`
  - `schema.py`: `FLOW_OPTIONAL_COLUMNS` 컬럼명 갱신
  - `mid_engine.py`: ratio 임계값(`>1.0/<0.8`) 제거, spread 임계값(`>+0.005/<-0.005`) 적용
- 효과:
  - spread 표준편차(`0.028`) 기준 약 `0.18σ` 노이즈 필터 구간 확보
  - `NEUTRAL` 구간 약 `15.3%` 확보

### feat(strategy_engine): Short Engine secondary PANIC 신호 확장
- `short_engine.py`에 `smallcap_stress` 신호 추가:
  - 조건: `iwm_spy_vol_spread > 0.005`
  - 의미: 소형주 변동성 스트레스 감지
- secondary PANIC 확인 규칙:
  - 기존 3신호(`vol_spike`, `wide_intraday`, `flight_to_safety`)
  - 변경 4신호 + `2개 이상` 충족 시 PANIC 확인

### test(strategy_engine): Mid/Short 회귀 테스트 추가
- `tests/pipeline/strategy_engine/test_mid_engine.py`
  - MM4 fixture: ratio → spread 값 반영
  - MM5 신규 3건: ratio 부호 반전 케이스를 spread 방식으로 교정 검증
- `tests/pipeline/strategy_engine/test_short_engine.py`
  - MSH7 신규 2건: `smallcap_stress` 경계값(`>0.005`, `<=0.005`) 검증
- `tests/pipeline/strategy_engine/test_axis_features.py`
  - breadth 컬럼/메서드명 변경 반영(2곳)

### 성과 비교 (v2 preset, 2006-01 ~ 2024-06, DCA $300/월)

| 엔진 | XIRR | MDD | Sharpe |
| --- | --- | --- | --- |
| v0 | +8.00% | -15.71% | 1.69 |
| v1 | +6.94% | -17.74% | 1.65 |
| v1.1 | +7.25% | -15.65% | 1.68 |

- v1.1 결과: `XIRR +0.31%p` 회복, `MDD -15.65%`로 v0 대비 소폭 개선, Sharpe 1.68
- 전체 테스트: `389 passed, 1 skipped`

---

## v2026.02.22b — Strategy Engine Allocation v1/v2 업그레이드

### feat(strategy_engine): Allocation v1/v2 모드 추가

`allocation/engine.py`:
- `_ALLOCATION_V1_MAP`: `long_phase` → 목표 비율 (EXPANSION=0.60, RECESSION=0.10, SLOWDOWN=0.20, UNKNOWN=0.40 등)
- `_ALLOCATION_V2_MAP`: `(long_phase, mid_regime)` → 목표 비율 (6×4 = 24 셀, 4단계 fallback)
- `_apply_delta()`: v1/v2 공통 gradual movement 헬퍼. PANIC(risk_gate=False)이어도 INCREASE 허용(저점매수)
- `_compute_allocation_v1()`, `_compute_allocation_v2()`: phase/regime 기반 target-seeking
- `build_allocation(allocation_mode="v0")`: `"v0"|"v1"|"v2"` dispatch 지원. 미등록 mode → v0 fallback

`strategy_job.py`:
- `StrategyJobRunner(allocation_mode="v0")` 필드 추가
- CLI `--allocation-mode v0|v1|v2` 인자 추가

**v0 vs v1/v2 PANIC 동작 차이:**
- v0: risk_gate=False → INCREASE 차단 (범위유지 보수적)
- v1/v2: risk_gate=False → INCREASE 허용 (target-seeking 저점매수)

### test(strategy_engine): Allocation v1/v2 테스트 추가 (+19건)
- `TestAllocationV1`: EXPANSION(+), RECESSION(-), SLOWDOWN(-), at_target, run_universe gate, risk_gate PANIC, unknown fallback, adj_limit 경계
- `TestAllocationV2`: LATE_CYCLE+RISK_OFF(-), EXPANSION+RISK_ON(+), RECESSION+RISK_OFF(-), UNKNOWN+UNKNOWN(HOLD), fallback chain, PANIC/run_universe gate
- `TestAllocationModeDispatch`: default=v0, unknown mode fallback
- 전체 테스트: `373 passed, 1 skipped`

### docs(strategy_engine): K4/K5/K7/K9 갱신
- K4: 373 passed, SE 소계 140
- K5: Allocation v1/v2 수정 이력 추가
- K7: v1/v2 CLI 예시 추가
- K9: SE v1/v2 지원 완료 표 갱신

---

## v2026.02.22 — 문서 정합성 수정 및 Backtest Sell 실행 로직 안정화

### fix(docs): strategy_engine_design.md CORE 정의 수정 (TLT→SCHD)
- `§D1-1` CORE 목록을 `(SPY, TLT, IAU)` → `(SPY, SCHD, IAU)`로 정정
  - `TLT`는 BOND tactical로 이동 — RECESSION/SLOWDOWN 구간에서 RS 기반 자동 선정
  - `SCHD`는 2011-10-24 이전 데이터 없음 → Universe Engine이 `gold_eod` 미존재 심볼을 자동 제외하므로 별도 처리 불필요
- `§D1-1` 관련 `docs/architecture/universe_contract.md` CORE 정의 동기화

### feat(docs): K8 성과 지표 DCA 기준으로 교체 (v2026.02.22 기준)
- 기존 CAGR/MDD/Sharpe 단순 테이블 → DCA 총수익/XIRR/MDD/Sharpe/Calmar 확장 테이블

| 지표 | v0 | v1 | v2 | SPY B&H |
| --- | --- | --- | --- | --- |
| DCA 총수익 | +46.9% | +60.0% | +122.9% | - |
| XIRR (DCA) | +3.97% | +4.81% | +8.00% | +10.13% |
| MDD | -11.18% | -20.19% | -15.71% | -55.19% |
| Sharpe | 1.76 | 1.60 | 1.69 | - |
| Calmar | 2.53 | 1.43 | 1.99 | - |

### feat(docs): K9 Backtest Allocation 아키텍처 vs Strategy Engine 신규 섹션
- Allocation 버전 차이 명시 (SE=RC_V0_DEFAULT 단일 / Backtest=v0/v1/v2 프리셋)
- Sell Advisor advisory 역할 명시:
  - `sell_budget_ratio` / `sell_priority_list`는 권고 출력
  - 실제 매도 실행은 `_execute_sell_tranche()`의 target_weights 기반 로직
  - Sell Planner → Sell Advisor 명칭 변경 완료 (P3 이행)

### fix(backtest): Sell 실행 전략 확정 — target_weights 기반 (phase-based 실험 후 복원)
- PHASE_SELL_MODE (phase별 rs_priority/비례 혼합) 실험 후 제거
  - Full rs_priority: v0 +15.4%, v2 +102.6%
  - Phase-based 혼합: v0 +15.4~15.8%, v2 +96.2~97.8%
  - Pure 비례: v0 +15.8%, v2 +92.8%
  - **target_weights (복원)**: v0 +46.9%, v1 +60.0%, v2 +122.9%
- target_weights 방식이 단순 비례/rs_priority 대비 v2 기준 +20~30%p 우수
  - 이유: 매도와 동시에 내부 비중 정상화 (과매수 포지션 선제 정리)
- `config.py` PHASE_SELL_MODE 상수 제거, `runner.py` StagedSellPlan 단순화

### K4 테스트 현황 갱신
- 전체: `305 passed` → `354 passed, 1 skipped`
- Strategy Engine: 121건 / Backtest Engine: 62건

---

## v2026.02.21b — Backtest Runner 실행 규칙 정합화 및 리포트 지표 확장

### fix(backtest): 실행 스케줄/리스크 게이트/유니버스 참조 경로 정합화
- `runner.py` 실행 규칙을 주간 단위로 명시하고 코드/동작을 정합화:
  - 월요일: 전 거래일(T-1) 신호 평가
  - 화요일: `INCREASE` 실행(현금 배포 매수)
  - 금요일: `DECREASE` 단계 매도 실행(`50% → 30% → 20%`, 3주)
- `risk_gate=false(PANIC)` 처리 변경:
  - `INCREASE`는 허용(저점 매수)
  - `DECREASE` 신규 생성 차단 + 진행 중 트랜치 동결
- `what_to_hold` snapshot 직접 의존 대신 `gold_eod`(`ret_20d`, `asset_group`) 기반 inline Universe 계산 경로 유지
- 월 첫 거래일 DCA 자금 투입(`monthly_addition`) 및 벤치마크(SPY) 동일 규칙 적용

### feat(backtest): DCA/XIRR 및 최종 포지션 리포트 확장
- `BacktestConfig`/`BacktestPreset`에 `monthly_addition` 필드 추가
- `metrics.py`에 `compute_xirr()` 추가, `compute_metrics()`에 아래 지표 확장:
  - `dca_return`, `xirr`, `total_capital_injected`
- `BacktestResult` 확장:
  - `total_capital_injected`, `cash_flows`, `bm_cash_flows`
  - `final_positions`, `final_benchmark_positions`
- `report.py` 출력 확장:
  - 전략 vs SPY 병렬 성과표
  - DCA/IRR 지표 표기
  - 최종 보유 포지션 테이블 출력

### fix(backtest): 보조 로직 정합화
- `rebalancer.py` 전술 비중 차감 로직 개선:
  - 단일 core 차감 방식 → core 전체 비례 차감(기존 core 비율 유지)
  - 최소 core 비중 제약(`0.05`) 기반 슬롯 축소 처리
- pre-SCHD 기본 구성 변경:
  - `SPY 80 / IAU 20` → `DVY 25 / VIG 25 / SPY 30 / IAU 20`
  - SCHD 출시 후 DVY/VIG→SCHD 단계 전환 로직 반영
- `portfolio.py`:
  - `add_cash()` 추가(DCA 투입)
  - snapshot에 `avg_cost` 포함

### 테스트 영향
- backtest 관련 테스트 기대값/시나리오를 신규 규칙에 맞게 갱신
  - `tests/pipeline/backtest/test_runner.py`
  - `tests/pipeline/backtest/test_rebalancer.py`
  - `tests/pipeline/backtest/test_allocation.py`

---

## v2026.02.21 — Universe Engine v1 + Strategy/Backtest Universe 경로 수정

### feat(universe): Phase-based eligible pool + mid_regime Top-N
- Universe Engine v1 구현: 단순 `is_candidate=True` 방식에서 `phase eligible pool + mid_regime Top-N` 구조로 전환
- Phase 제외 규칙:
  - `RECESSION`: `{USO, UNG}`
  - `SLOWDOWN`: `{UNG}`
  - `LATE_CYCLE`: `{}` (전체 허용, live RS 위임)
  - `EXPANSION`: `{UNG}`
  - `RECOVERY`: `{USO, UNG, XLE}`
  - `UNKNOWN`: `{}` (fail-open)
- `mid_regime` Top-N:
  - `RISK_OFF=5`, `NEUTRAL=7`, `RISK_ON=9`, `UNKNOWN=7`
- 상대강도 정의: `relative_strength = ret_20d(symbol) - ret_20d(SPY)`
- CORE(`SPY`, `TLT`, `IAU`)는 phase 필터 및 Top-N과 무관하게 항상 `is_candidate=true`
- 테스트: `tests/pipeline/strategy_engine/test_universe.py` UV1~UV6, 총 15건 통과

### fix(strategy/backtest): what_to_hold 누적 버그 및 snapshot 의존 경로 수정
- `strategy_job.py` 수정:
  - 기존 `build_universe(df_ps, df_gold_eod)` 호출이 전 기간 `policy_selection`을 전달해 `what_to_hold` snapshot 누적 발생
  - 수정: `decision_date` 하루치(`df_ps_today`)만 `build_universe` 입력으로 전달
- `backtest/runner.py` 수정:
  - 누적 가능성이 있는 `what_to_hold` snapshot 로드 제거
  - `_load_gold_eod_features()` 추가
  - `_compute_universe_inline()` 추가
  - 리밸런싱 시점별 inline Universe 계산으로 전환
- 성과(2006-01-03 ~ 2024-06-03, `z_threshold=0.3`):

| 지표 | v0 | v1 | v2 | SPY B&H |
| --- | --- | --- | --- | --- |
| CAGR | +5.98% | +3.51% | +3.99% | +10.13% |
| MDD | -28.51% | -26.51% | -19.75% | -55.19% |
| Sharpe | 0.68 | 0.51 | 0.62 | - |

- 테스트: 전체 `346 passed, 1 skipped`

---

## v2026.02.20 — Text Data Pipeline 설계 확정 + Universe 이원화 문서 정합화

### 변경 요약
- **Text 수집 전략 v1 확정**: Tiered Hybrid ($0 시작, T+1 배치). 소스: SEC EDGAR + Fed/FOMC (FMP News는 유료 전환 보류)
- **text_observability_contract.md 보강**: Bronze 멱등키 `(source, source_doc_id)` + `source_doc_id`/`ingested_at`/`raw_payload_hash` 신규 필드, Silver LLM → Reserved(v1+) + v0 필수 필드(asset_scope/quality_flags/clean_text), Gold long 포맷 전환 + 초기 3개 feature (`macro_hawkish_score`/`filing_risk_burst`/`policy_uncertainty_idx`), Fail-open 정책 + 품질 KPI 섹션 추가
- **strategy_engine_design.md SECTION J 업데이트**: 텍스트 보조 feature 역할 명시, Gold long format 스키마 확정, fail-open 원칙
- **data_ingest_datasources.md 보강**: 텍스트 소스 섹션 신규 추가 (SEC EDGAR, Fed/FOMC, FMP 보류)
- **Universe 이원화 문서 정합화 (Codex 완료)**: `universe_design.md` → `Universe-ETF Design`으로 개명 + `Universe-Stock(U0~U3)` 참조 명시, `milestones.md`/`data_ingest_datasources.md`/`README.md` 전반 용어 통일

### 소스 접근 가능 여부 확인 결과
| 소스 | 상태 | 비고 |
| --- | --- | --- |
| SEC EDGAR (data.sec.gov) | ✅ 사용 가능 | User-Agent 필수, 10 req/sec 상한 |
| Fed/FOMC RSS | ✅ 사용 가능 | `federalreserve.gov/feeds/press_all.xml` 실시간 확인 |
| FMP News | ❌ 무료 불가 | 무료 플랜 뉴스 미지원. Starter $22/월 이상 필요 |

---

## v2026.02.21 — Walk-Forward 분석 + Phase 분포 모니터링 + threshold 가변화 설계

### 변경 요약
- **Walk-Forward 기간별 성과 분석** (`walk_forward.py`) 신규: threshold=0.3 운영 안정성 검증 도구
- **Phase 분포 모니터링** (`compute_phase_distribution()`, `print_phase_distribution()`) 추가: 연/반기/분기별 LATE_CYCLE%, S+R% 추적
- **`_utils.py`** 신규: `load_strategy_snapshot()` 공통 유틸 (runner.py + walk_forward.py 공유)
- **가변 threshold 설계 문서** (`docs/architecture/threshold_policy_v2.md`): 이산 상태 {0.0, 0.3}, 트리거, cooldown=6개월 명시
- **Universe 용어 이원화 기준 도입**: `Universe-ETF(Execution Universe)` / `Universe-Stock(U0~U3)`로 구분
- **과거 changelog 원문 보존 원칙**: 과거 섹션은 용어 치환 없이 유지, 최신 섹션에서 해석 기준만 명시
- **문서 정합화**: README 실행/검증 섹션, Strategy Engine SOT 구현 현황, Long contract 입력 계약(indicator_id N/권장) 동기화
- 신규 테스트 13건 추가, 전체 `305 passed, 1 skipped`

### Universe 용어 기준 (문서 해석 규칙)
- `Universe-ETF (Execution Universe)`: 현재 Strategy Engine에서 실제 운용 중인 ETF 후보 선별 모듈
- `Universe-Stock (Research Universe, U0~U3)`: Macro→Theme→Stock 로드맵 파이프라인
- 과거 changelog 항목의 `Universe` 표현은 작성 시점의 원문으로 보존한다.

### Walk-Forward (`pipeline/backtest/walk_forward.py`)

**목적**: 동일 snapshot(2024-06-03) 기반 기간별 성과 일관성 검증.

> **주의**: 동일 snapshot 재사용으로 look-ahead bias가 존재할 수 있음.

**주요 구성**:
```
WalkForwardConfig: preset, windows, window_years=4, step_years=2, full_start, full_end
WalkForwardRunner.run() → DataFrame (고정 스키마)
  컬럼: window_start, window_end, cagr, total_return, max_drawdown,
        sharpe_ratio, benchmark_cagr, excess_cagr, preset, generated_at
```

**저장 산출물** (`report.py:save_walk_forward()`):
- `data/backtest/reports/walk_forward/walk_forward_{preset}_{ts}.parquet`
- `data/backtest/reports/walk_forward/walk_forward_{preset}_{ts}_summary.json`

**CLI**:
```bash
python -m pretrend.pipeline.backtest.walk_forward \
    --preset v2 --window-years 4 --step-years 2 [--save]
```

### Phase 분포 모니터링 (`metrics.py`, `report.py`)

```python
compute_phase_distribution(policy_df, group_by="year"|"half"|"quarter")
# 반환: period, LATE_CYCLE_pct, SLOWDOWN_pct, RECESSION_pct,
#       EXPANSION_pct, RECOVERY_pct, UNKNOWN_pct, SR_combined_pct

print_phase_distribution(policy_df, group_by="year")
# 경고 기준: LATE_CYCLE% > 60% (L), S+R% > 50% (H), S+R% < 15% (l)
```

### `_utils.py` 공통 유틸화

`runner.py:_load_snapshot()` → `pipeline/backtest/_utils.py:load_strategy_snapshot()` 추출.
승격 정책: 여러 pipeline에서 재사용 확인 시 `src/pretrend/utils/`로 이전.

### 가변 threshold 설계 (`docs/architecture/threshold_policy_v2.md`)

- threshold ∈ {0.0, 0.3} 이산 전환
- 트리거: rolling 12개월 LATE_CYCLE% > 60% → 0.3→0.0 / S+R% < 15% → 0.0→0.3
- Cooldown: 최소 6개월
- **코드 미구현** — 운영 검증 후 필요 조건 충족 시 착수

### Walk-Forward 실증 검증 결과 (v2, 4년 창, 2년 슬라이드, 2006~2024.6)

> look-ahead bias 존재 (동일 snapshot 재사용). 목적: 국면별 전략 행동 일관성 파악.

**9개 창 성과**:
| Window | CAGR | Total | MDD | Sharpe | Exc.CAGR |
|--------|------|-------|-----|--------|----------|
| 2006-01 ~ 2010-01 | +2.05% | +8.4% | -15.79% | 0.34 | +3.17% |
| 2008-01 ~ 2012-01 | +0.76% | +3.1% | -15.39% | 0.13 | +1.77% |
| 2010-01 ~ 2014-01 | +5.63% | +24.5% | -9.50% | 0.76 | -9.43% |
| 2012-01 ~ 2016-01 | +4.92% | +21.1% | -4.96% | 0.90 | -9.89% |
| 2014-01 ~ 2018-01 | +5.14% | +22.2% | -6.01% | 1.08 | -7.38% |
| 2016-01 ~ 2020-01 | +5.32% | +23.0% | -6.36% | 1.13 | -9.45% |
| 2018-01 ~ 2022-01 | +6.41% | +28.2% | -12.44% | 0.88 | -10.89% |
| 2020-01 ~ 2024-01 | +4.18% | +17.8% | -17.65% | 0.49 | -7.37% |
| 2022-01 ~ 2024-06 | +1.49% | +3.6% | -8.66% | 0.28 | -4.22% |
| **평균** | **+3.99%** | **+16.9%** | **-10.75%** | **0.67** | **-5.96%** |

**해석**:
- **최적 구간 (2012~2020)**: CAGR 4~5%, MDD -5~-6%, Sharpe 0.76~1.13 — 전략이 가장 안정적으로 작동
- **취약 구간**: GFC 직격(2008~2012, CAGR +0.76%), 금리인상기(2022~2024.6, CAGR +1.49%) — 설계 한계 내 허용 범위
- **Excess CAGR 마이너스**: SPY B&H 대비 언더퍼폼이나, MDD를 평균 -10.75%로 억제한 대가

### Phase 분포 실증 결과 (policy_selection, 2006~2024 연도별)

**경고 발생 연도**:
| 연도 | LATE% | S+R% | 경고 | 해석 |
|------|-------|------|------|------|
| 2007 | 61.5% | 13.8% | Ll | LATE_CYCLE 과다 + S+R 과소 |
| 2008 | 80.5% | 6.3% | Ll | 금융위기 전야 미감지 |
| 2010 | 18.0% | 60.5% | H | GFC 이후 과도 방어 |
| 2016 | 71.7% | 0.0% | Ll | LATE_CYCLE 고착 |
| 2018 | 77.4% | 22.6% | L | LATE_CYCLE 과다 |
| 2019 | 20.3% | 64.0% | H | 침체 과잉 감지 |
| 2021 | 64.4% | 0.0% | Ll | 금리인상 전야 미감지 |
| **2022** | **96.9%** | **2.7%** | **Ll** | **threshold 억제 극단 — 금리인상 최고조** |
| 2023 | 22.7% | 71.5% | H | SLOWDOWN 과다 |
| 2024 | 6.3% | 54.9% | H | SLOWDOWN 지속 |

**가변화 조건 사후 검토**:
- `threshold_policy_v2.md` 필요 조건 "Ll 연속 2년": **2021~2022에 사후 발생**
- 현재(2023~2024)는 H 구간으로 전환 → threshold 가변화 필요성 없음, 0.3 고정 유지 적절

### 신규 테스트 (13건)
**`tests/pipeline/backtest/test_walk_forward.py` — 9건**
- `TestGenerateWindows`: 창 생성 범위·캡핑·명시적 기간 검증 (3건)
- `TestWalkForwardRunnerRun`: 스키마·행 수·빈 window 검증 (3건)
- `TestSaveWalkForward`: parquet+json 생성·컬럼·키 검증 (3건)

**`tests/pipeline/backtest/test_metrics.py` — 4건**
- `TestComputePhaseDistribution`: 연도별 집계·SR_combined·빈 DF·half 집계 (4건)

---

## v2026.02.20 — _get_signal_row 버그 수정 + z-score threshold=0.3 채택

### 변경 요약
- **버그 수정**: `runner.py:_get_signal_row` 다중 decision_date 스냅샷 혼합 → 비결정적 선택 문제 해결
- **버그 수정**: `runner.py:_load_snapshot` Hive 파티션에서 `decision_date` 컬럼 복원
- **Long Engine v1 threshold=0.3 채택**: `_classify_long_phase(threshold=0.3)` → SLOWDOWN+RECESSION 37.7% → 27.0%
- `_classify_long_phase`/`build_long_phase`/`build_axis_horizon_state`/`strategy_job` CLI에 `z_threshold` 파라미터 추가
- 신규 테스트 7건 추가, 전체 `291 passed, 1 skipped`

### 핵심 버그 수정: `pipeline/backtest/runner.py`

**문제**: `_load_snapshot()`이 모든 decision_date parquet를 concat → 동일 trade_date에 여러 스냅샷이 존재할 때 `iloc[0]`이 비결정적. 과거 결과(v0 +4.51% CAGR)는 GFC 스냅샷(2009-03-09)과 2024-06-03 스냅샷이 혼합된 결과였음.

**수정**:
```
1. _load_snapshot(): Hive 파티션 경로에서 decision_date 추출 → date 타입으로 컬럼 추가
2. _get_signal_row(): 최신 decision_date 우선 선택 → source_run_id desc 동률 타이브레이커
```

**수정 후 실제 베이스라인** (threshold=0.0, 스냅샷 혼합 없음):
| 지표 | v0 | v1 | v2 |
|------|-----|-----|-----|
| Total Return | +43.4% | +93.5% | +101.6% |
| CAGR | +1.98% | +3.65% | +3.88% |
| MDD | -6.70% | -21.51% | -15.13% |
| Sharpe | 0.73 | 0.57 | 0.65 |

### z-score threshold=0.3 채택

**Phase 분포 변화** (2006-2026 전체 Gold Macro 기준):
| phase | threshold=0.0 | threshold=0.3 |
|-------|---------------|---------------|
| LATE_CYCLE | 37.7% | **45.1%** |
| SLOWDOWN | 22.9% | 15.5% |
| RECESSION | 14.8% | 11.8% |
| RECOVERY | 5.7% | 8.7% |
| SLOWDOWN+RECESSION 합계 | 37.7% | **27.3%** |

**백테스트 성과 비교** (threshold=0.0 → 0.3):
| 지표 | v0 (0.0) | v0 (0.3) | v2 (0.0) | v2 (0.3) |
|------|---------|---------|---------|---------|
| Total Return | +43.4% | +46.0% | +101.6% | **+118.3%** |
| CAGR | +1.98% | +2.08% | +3.88% | **+4.33%** |
| MDD | -6.70% | -7.23% | -15.13% | -15.79% |
| Sharpe | 0.73 | 0.72 | 0.65 | **0.68** |

**채택 근거**: v2에서 CAGR +0.45%p, Sharpe +0.03 개선. MDD 소폭 악화(-0.66%p)는 허용 범위.

**2024-06-03 스냅샷 재생성** (threshold=0.3 기준):
- LATE_CYCLE: 45.8%, SLOWDOWN: 14.6%, RECESSION: 12.4% — S+R 합계 27.0%

### 신규 테스트 7건
**`tests/pipeline/backtest/test_runner.py` — _get_signal_row 결정론성 (3건)**
- `TestGetSignalRowDeterminism::test_latest_decision_date_wins`: 최신 decision_date 행 선택
- `TestGetSignalRowDeterminism::test_string_decision_date_compared_correctly`: date 변환 후 비교
- `TestGetSignalRowDeterminism::test_source_run_id_tiebreaker`: source_run_id desc 동률 정렬

**`tests/pipeline/strategy_engine/test_long_engine.py` — threshold 파라미터 (4건)**
- `TestLongPhaseThreshold::test_threshold_zero_default`: default threshold=0.0 동작
- `TestLongPhaseThreshold::test_threshold_03_borderline_is_late_cycle`: z=-0.1 → LATE_CYCLE
- `TestLongPhaseThreshold::test_threshold_03_clearly_negative_is_slowdown`: z=-0.5 → SLOWDOWN
- `TestLongPhaseThreshold::test_threshold_03_easing_borderline`: z=-0.1, easing → RECOVERY

### 추가 완료 (동일 세션)
- market_structure_long_contract.md 개정: v1 rolling z-score 로직, z_threshold=0.3, §6 Invariants 상세화
- indicator_id 입력 계약은 2026-02-21에 fail-open 정책 정합화(N/권장)로 보정
- `BacktestResult.metrics` 필드 추가 (total_return 포함 전 지표 programmatic 접근)
- `save_result()` → `{stem}_metrics.json` 저장 추가

---

## v2026.02.19b — Long Engine v1 (delta_6m 지표별 rolling z-score 정규화)

### 변경 요약
- `long_engine.py`: `delta_6m_mean` (이질적 지표 혼합 평균) → 지표별 rolling z-score 평균으로 교체
- LATE_CYCLE 지배 비율 **59.7% → 41.3%** (-18.4%p) 감소 달성
- 신규 테스트 4건 추가, 전체 `284 passed, 1 skipped`

### 핵심 변경: `pipeline/strategy_engine/axis_horizon_state/long_engine.py`

**문제**: `delta_6m_mean` = CPI(수 단위) + UNRATE(0.x 단위) 혼합 평균 → CPI 스케일 압도 → tightening 기간 거의 전부 LATE_CYCLE (59.7%)

**해결**: 지표별 rolling z-score 정규화 (단위 불변)
```
1. (indicator_id, trade_date) 중복 제거: keep="last"
2. 지표별 rolling z-score: window=252, min_periods=60
3. NaN fallback: z-score 미계산 시 raw delta_6m 부호(sign) 사용
4. indicator_id 컬럼 없으면 regime 단독 판정 (fail-open)
```

**LATE_CYCLE 비율 변화** (2006-2024, decision_date=2024-06-03 기준):
| phase | 변경 전 (v0 엔진) | 변경 후 (v1 엔진) |
|-------|---------|---------|
| LATE_CYCLE | 59.7% | **39.7%** |
| SLOWDOWN | ~1% | 20.7% |
| RECESSION | ~5% | 15.4% |
| EXPANSION | ~15% | 15.5% |

**백테스트 성과 (2006~2024)**:
| 지표 | v0 | v1 | v2 |
|------|-----|-----|-----|
| CAGR | +4.51% | +3.53% | +3.99% |
| MDD | -15.66% | -24.64% | -16.26% |
| Sharpe | 0.72 | 0.53 | 0.66 |
| GFC MDD | -9.31% | -17.45% | -10.74% |
| COVID MDD | -15.66% | -11.81% | -11.73% |
| Rate Hike MDD | -11.92% | -11.40% | -9.42% |

구 long_engine v0 대비: v0 CAGR 거의 유지(4.59%→4.51%), v2 CAGR 소폭 하락(5.21%→3.99%)

### 신규 테스트 4건 (`tests/pipeline/strategy_engine/test_long_engine.py`)
- `TestLongPhaseV1Normalization::test_unit_invariance`: CPI/UNRATE 스케일 차이에서도 유효한 ENUM 결과
- `TestLongPhaseV1Normalization::test_nan_fallback_early_period`: 초기구간 NaN → sign fallback 적용 확인
- `TestLongPhaseV1Normalization::test_missing_indicator_id_fallback`: indicator_id 없으면 regime-only (LATE_CYCLE)
- `TestLongPhaseV1Normalization::test_duplicate_indicator_trade_date`: 중복 keep="last" 후 1행 결과

### 미수정 (다음 세션)
- z-score 임계값 조정 (0.0 → 0.3 등): SLOWDOWN/RECESSION 과다 여부 검증 후 결정
- market_structure_long_contract.md 개정: 임계값 확정 후 진행

---

## v2026.02.19 — Allocation v2 (2D lookup) + 아키텍처 리팩토링

### 변경 요약
- Allocation 전략을 `pipeline/backtest/allocation.py`로 분리, 버전별 함수 + `ALLOCATION_REGISTRY` + `dispatch_allocation()` 레지스트리 패턴 도입
- `PRESET_V2` 추가: `target = f(long_phase, mid_regime)` 2D 룩업 — LATE_CYCLE 과도 비율을 allocation 레이어에서 mid_regime으로 분화
- v1 `run_universe=false` 미체크 버그 수정 (INCREASE 차단 누락)
- 신규 테스트 23건 추가, 전체 `280 passed, 1 skipped`

### 핵심 변경

**1) `pipeline/backtest/allocation.py` (신규)**
- `compute_allocation_v0()`: 기존 range-maintenance 로직 위임
- `compute_allocation_v1()`: f(long_phase) target-seeking + `run_universe` 체크 버그 수정
- `compute_allocation_v2()`: f(long_phase, mid_regime) 2D lookup, 4단계 fallback
- `ALLOCATION_REGISTRY`, `dispatch_allocation()`: preset_name 기반 dispatch

**2) `pipeline/backtest/config.py`**
- `BacktestPreset.target_ratio_map_v2: Optional[Dict[Tuple[str,str], float]]` 필드 추가
- `PRESET_V2` 정의 및 `PRESET_REGISTRY["v2"]` 등록
- `BacktestConfig.target_ratio_map_v2` 필드 + `__post_init__` 키/값 검증 + `from_preset()` defaults

**3) `pipeline/backtest/runner.py`**
- `_compute_dynamic_allocation()`: `dispatch_allocation()` 단순 위임으로 교체
- 기존 `_target_seeking_allocation()` inline 메서드 제거

### v2 Target Ratio 2D 테이블
| long_phase \ mid_regime | RISK_ON | NEUTRAL | RISK_OFF | UNKNOWN |
|---|---|---|---|---|
| EXPANSION | 0.80 | 0.70 | 0.55 | 0.65 |
| LATE_CYCLE | 0.60 | 0.45 | **0.30** | 0.45 |
| SLOWDOWN | 0.35 | 0.25 | 0.15 | 0.25 |
| RECOVERY | 0.70 | 0.60 | 0.45 | 0.60 |
| RECESSION | 0.20 | 0.10 | 0.05 | 0.10 |
| UNKNOWN | 0.50 | 0.40 | 0.30 | 0.40 |

핵심: LATE_CYCLE + RISK_OFF = 0.30 (v1의 0.60에서 절반 — 하방 방어 강화)

### 미수정 (다음 세션)
- `long_engine.py` delta_6m 임계값 정밀화: delta_6m_mean이 이질적 지표 혼합 평균이므로 정규화 전략 확립 후 진행

---

## v2026.02.14 — Backtest Engine v0+v1 구현 반영 및 문서 동기화

### 변경 요약
- Strategy Engine 출력 기반 포트폴리오 시뮬레이션 모듈(Backtest Engine)을 구현하고 문서에 반영
- `v0(range-maintenance)` + `v1(target-seeking)` allocation preset을 `BacktestPreset`/`PRESET_REGISTRY`로 고정
- 2006-01-03 ~ 2024-06-03 구간 백테스트 CLI 실행 경로 및 tactical rotation 규칙을 운영 문서에 반영
- Backtest 전용 테스트 62건 포함, 전체 프로젝트 테스트 결과 `256 passed, 1 skipped`로 갱신

---

### 1) Backtest Engine 모듈 추가 (`src/pretrend/pipeline/backtest/`)
- `config.py`
  - `BacktestPreset(frozen)`, `PRESET_REGISTRY(v0/v1)`, `BacktestConfig.from_preset()` 구현
- `portfolio.py`
  - `Portfolio(Position, Trade)` 및 `buy/sell/rebalance_to_weights` 구현
- `rebalancer.py`
  - `compute_target_weights`, `is_rebalance_day`, tactical rotation(`config.tactical_groups`) 구현
- `runner.py`
  - `BacktestRunner` E2E 시뮬레이션
  - `_compute_dynamic_allocation(v0/v1)`, `_target_seeking_allocation` 분기 구현
- `metrics.py`
  - `CAGR`, `MDD`, `Sharpe`, `Sortino`, `Calmar`, 벤치마크 비교 지표 구현
- `report.py`
  - 콘솔 리포트(전체 + GFC/COVID/Rate Hike/Recovery 2023 구간) 구현

---

### 2) Preset 시스템 고정
- `PRESET_V0`
  - range-maintenance (`[0.10, 0.60]`), tactical=`SECTOR`
- `PRESET_V1`
  - target-seeking(phase별 목표 비율), tactical=`SECTOR`
- `PRESET_REGISTRY`
  - `{\"v0\": PRESET_V0, \"v1\": PRESET_V1}`
- `BacktestConfig.from_preset(\"v1\", start_date=..., end_date=..., **overrides)` 지원
- CLI override
  - `--preset v0|v1`
  - `--tactical SECTOR COMMODITY`

---

### 3) v1 Allocation 규칙 반영
- `long_phase -> target ratio`
  - `EXPANSION=0.60`, `RECOVERY=0.60`, `LATE_CYCLE=0.60`, `SLOWDOWN=0.20`, `RECESSION=0.10`, `UNKNOWN=0.40`
- `adjustment_limit=0.10` (월간 최대 10%p), `step_size=0.05` 양자화
- `risk_gate=false`이면 `INCREASE` 차단, `DECREASE` 허용
- v0는 `target_ratio_map=None`으로 Strategy Engine range-maintenance 규칙 위임

---

### 4) Tactical Rotation 규칙
- 조건:
  - `run_universe=true`
  - `risk_gate=true`
  - `long_phase not in {RECESSION, SLOWDOWN}`
- `config.tactical_groups` 기반 필터
  - 기본(v0): `["SECTOR"]`
  - 확장: `["SECTOR", "COMMODITY"]`
- `relative_strength > SPY`인 ETF 상위 2개를 각 15% 비중으로 반영하고, `SCHD`/`SPY`에서 차감

---

### 5) 성과/테스트 현황 (2006-01-03 ~ 2024-06-03)
- 성과 비교:
  - CAGR: v0 `+4.59%`, v1 `+5.37%`, SPY B&H `+10.13%`
  - Total: v0 `+128.7%`, v1 `+162.1%`, SPY B&H `+490.7%`
  - MDD: v0 `-15.7%`, v1 `-23.8%`, SPY B&H `-55.2%`
  - Sharpe: v0 `0.74`, v1 `0.66`
  - GFC MDD: v0 `-9.4%`, v1 `-17.2%`, SPY B&H `-46.0%`
- 테스트:
  - Backtest tests: 62
  - 전체 프로젝트: `257 tests (256 passed, 1 skipped)`

---

## v2026.02.13 — Strategy Engine v0 구현 반영 및 문서 동기화

### 변경 요약
- Strategy Engine 명칭 기준을 확정하고, WHAT/EXPOSURE/SELL 3-경계 출력 + `decision_date` snapshot 저장 원칙을 SOT로 고정
- Gold Macro/EOD snapshot 기반 Strategy Engine v0(7단계 파이프라인) 구현 현황을 문서에 반영
- 테스트 결과(194 passed, 1 skipped) 및 실데이터 검증 요약(GFC 구간 포함)을 운영 문서에 반영
- (Reserved) Stock Extension Port 및 Text/LLM Integration Port를 v1+ 확장 포트로 유지
- Text Observability Contract 신규 추가: Bronze/Silver/Gold 텍스트 레이어, allowlist, event-sort, Strategy Engine 연동 규칙을 문서로 고정

---

## v2026.02.12 — EOD Observability Contract 문서화 및 문서 동기화

### 변경 요약
- PR#1~PR#3 코드 구현을 기준으로 EOD Observability SOT, Bronze/Silver 라벨 계약, Gold EOD Fact Mart를 파이프라인에 반영
- EOD E2E Runner(`eod_job.py`)와 Airflow Gold task(`run_eod_gold_features_task`)를 통합
- EOD 관측용 ETF 세트(Always-on Observability Set)와 분류/라벨 계약을 신규 문서로 고정
- `architecture.md`에 Observability Set 개념(Always-on vs Universe-driven)과 계약 링크를 추가
- `data_requirements.md` EOD 요구사항에 Observability 분류 컬럼 계약(`asset_group`, `asset_name`, `asset_subtype`)을 반영

---

### 1) EOD Observability Contract v1 구현 (PR#1)
- `src/pretrend/pipeline/config/eod_observability.py` 신규 추가
  - SOT 상수: `OBSERVABILITY_SET_V1`, `OBSERVABILITY_SYMBOLS_V1`, `LABEL_BY_SYMBOL_V1`
  - `asset_group` ENUM 5종: `INDEX`, `COUNTRY`, `COMMODITY`, `BOND`, `SECTOR`
  - import 시 `validate_observability_set()` 자동 검증(중복/대문자/ENUM)
- `src/pretrend/pipeline/ingest/eod.py`
  - `EodIngestConfig.default_symbols`를 SOT 참조로 전환
  - `EodNormalizer`에서 미등록 심볼 `ValueError` 처리 및 `asset_group`/`asset_name`/`asset_subtype` 컬럼 확정
- `src/pretrend/pipeline/features/eod_features.py`
  - `build_eod_features()`에서 `asset_*` 라벨을 Silver로 pass-through
- `tests/pipeline/test_eod_observability_contract.py` 신규(9 tests)
  - OL1~OL5 계약 검증(커버리지/라벨/reject/pass-through/멱등 안정성)

---

### 2) 하드코딩 제거 및 SOT 참조 전환 (PR#2)
- `src/pretrend/pipeline/ingest/eod.py` docstring/CLI help를 `Observability SOT` 기준으로 정리
- `dags/eod_pipeline_dag.py` 주석을 `Observability SOT 32개 ETF` 기준으로 정리
- `src/pretrend/pipeline/features/eod_features.py` 내 하드코딩 심볼 예시 정리

---

### 3) Gold EOD Feature v1 Fact Mart 구현 (PR#3)
- `src/pretrend/pipeline/features/gold_eod_features.py` 신규
  - `GOLD_EOD_FEATURE_COLUMNS` 계약
  - `load_silver_eod_features()` 로더
  - `build_gold_eod_features()` Silver→Gold 변환(lineage/dedup)
  - `write_gold_eod_features()` 멱등 저장(symbol/year/month, atomic overwrite)
  - CLI 엔트리포인트: `python -m pretrend.pipeline.features.gold_eod_features`
- `src/pretrend/pipeline/eod_job.py` 신규
  - `EodJobConfig` / `EodJobRunner` / `EodJobResult`
  - Bronze→Silver→Gold 순차 실행 + 메타 로그(`data/meta/eod_job_log.parquet`)
- `dags/eod_pipeline_dag.py`
  - `run_eod_gold_features_task` 추가
  - 의존 체인 Bronze → Silver → Gold로 확장, DAG tag에 `gold` 추가
- `tests/pipeline/test_gold_eod_features.py` 신규(7 tests)
  - GE1~GE5 계약 검증(grain/columns/labels/lineage/idempotency)

---

### 4) 테스트 현황
- 전체 테스트: **71 passed, 1 skipped**

---

### 5) 신규 계약 문서 추가
- `docs/architecture/eod_observability_contract.md` 생성
- 포함 범위:
  - 용어 정의(Observability Set, 분류 컬럼, Always-on vs Universe-driven)
  - Scope / Non-Goals
  - 분류 체계(`INDEX`, `COUNTRY`, `COMMODITY`, `BOND`, `SECTOR`)
  - Base EOD Observability Set v1 전체 심볼 표
  - Bronze/Silver/Gold 라벨 전파 규칙 및 ENUM 계약
  - Universe read-only 소비 원칙 및 변경 관리(Versioning)

### 6) Architecture 문서 동기화
- `docs/architecture.md`에 EOD Observability Set 설명 단락 추가
- Always-on 센서 입력 목적, 라벨 고정 원칙, 계약 문서 링크 반영

---

### 7) Data Requirements 문서 동기화
- `docs/data_requirements.md`의 EOD 섹션에 `Always-on Observability ETFs v1` 항목 추가
- 필수 분류 컬럼 계약 및 Universe 그룹핑 사용 규칙을 명시

---

### 8) Risk-Control 전략 문서 구조 재정의 (4축 + Composer + Allocation v0)
- Design vs Contract 분리 원칙으로 전략 문서를 재구성
  - Design: `docs/strategy_architecture.md`
  - Contracts: `market_structure_long/mid/short/composer`, `universe`, `allocation_engine`
  - Inventory: `docs/market_structure_data_inventory.md`
- 전략 흐름을 `Layer -> Market Structure(4축) -> Composer -> Universe -> Allocation Engine -> Weekly Report`로 고정
- v0 원칙 반영:
  - 총 투자 비율(`invested_ratio`) 조절만 허용
  - `risk_gate` 기반 증가 차단
  - Universe 내부 가중치 조절 금지
- 심리 축 입력 정책 갱신:
  - v0: VIX 필수 아님, Risk Spread + Volatility proxy 기반 상태 전이
  - v1+: VIX 편입(직접 VIX vs term structure 범위 결정 필요)
- 구버전 문서 정리:
  - `docs/architecture/market_structure_v1_contract.md` 삭제
  - 레거시 전략 계약 문서 제거(현행 구조에서 비사용)

---

### 9) 전략 로드맵 문서 동기화
- `docs/milestones.md`에 Risk-Control 전략 로드맵(v0~v3) 추가
- 운영 주기 분리 명시:
  - Adjustment Cycle: 주 1회(화요일)
  - Portfolio Rebalance: 월 1회(마지막 주 금요일, 휴장 시 직전 영업일)

## v2026.02.11 — Gold Macro Feature v1 E2E 통합 구현

### 변경 요약
- Gold Layer v1을 설계 계약(`gold_design_contract.md`)에서 구현 완료 단계로 전환
- `macro_job.py` E2E 플로우에 Gold 단계 통합: Bronze → Silver → Gold 1회 실행 동기화
- Calendar Silver(`econ_events`, `fred_vintages`)를 소비하는 3-tier fallback cascade로 `release_date` 증거 구축
- PIT 불변식(`selected_release_date < trade_date`) 100% 충족 검증 완료

---

### 1) Gold Macro Feature v1 핵심 로직 (`gold_macro_features.py`)
- 기존 순수 함수(`build_gold_macro_features`, MF1-MF10 테스트 완료)에 통합 인프라 추가:
  - `load_silver_macro()`: Silver macro → `[indicator_id, date, value]` 로드
  - `build_release_calendar()`: 3-tier fallback cascade
    - Tier 1: `econ_events` (`release_date = release_date_utc`)
    - Tier 2: `fred_vintages` (`is_first_vintage=True`, `release_date = vintage_date`)
    - Tier 3: `assumed_t+1` (`release_date = observation_date + 1 day`)
  - `write_gold_macro_features()`: `trade_date` 기준 파티션, `tmp -> atomic rename` 멱등 저장

---

### 2) `macro_job.py` E2E 플로우 통합
- 변경 전:
  - `bronze_ingest -> bronze_vintages -> bronze_econ_events -> silver_features -> silver_calendar`
- 변경 후:
  - 위 플로우 + `gold_macro_features` 추가
- `MacroJobConfig.gold_root` 프로퍼티, `MacroJobResult.gold_macro_result` 필드, Meta log `gold_macro_row_count` 반영

---

### 3) Calendar Runner Silver 로더 추가 (`calendar/runner.py`)
- `load_silver_econ_events()`, `load_silver_fred_vintages()` 추가
- Gold가 Silver Calendar의 첫 번째 downstream 소비자

---

### 4) E2E 검증 결과 (`--start 2024-01-01 --end 2024-06-30`)
- Gold 출력: 650행 (5 지표 × 130 영업일), 6개 월별 파티션
- PIT 불변식 위반: 0건
- `release_source` 태깅:
  - `CPI_US_ALL_ITEMS_SA`, `CPI_US_CORE_SA`, `US_UNEMPLOYMENT_RATE` → `econ_events`
  - `US_FED_FUNDS_RATE`, `US_TREASURY_10Y_YIELD` → `fred_vintages`
- `is_assumption_based`: 전부 `False` (Calendar 증거 100% 커버)
- Gold 저장 경로:
  - `data/gold/macro/macro_features/year=YYYY/month=MM/gold_macro_features_YYYYMM.parquet`

---

### 5) 테스트 현황
- Gold MF1-MF10: 22개 패스 (`tests/pipeline/test_gold_macro_feature_v1.py`)
- Calendar ST1-ST11: 12개 패스 (`tests/pipeline/test_calendar.py`)
- 전체 34개 테스트 통과

---

### 6) zscore_12m v1.1 구현 (`gold_macro_features.py`)
- `_zscore_12m()` 헬퍼 함수 추가 (lines 194-217)
- 공식: `(selected_value - mean) / std` — 12-month rolling z-score
- Monthly 지표 (CPI, UNRATE, FEDFUNDS): window = 12 관측치
- Daily 지표 (DGS10): window = 252 관측치 (약 1년 영업일)
- Edge cases:
  - `selected_value` NULL/NaN → None
  - window 내 관측치 부족 → None
  - std == 0 또는 NaN → None
- `_select_and_compute()`에서 기존 `"zscore_12m": None` → `_zscore_12m()` 호출로 변경

---

### 7) zscore_12m 테스트 (MF10a-MF10e)
- 기존 `TestZscoreV1` (항상 NULL 검증) → `TestZscoreV1_1` (실제 계산 검증)으로 교체
- MF10a: zscore_12m 컬럼 존재 확인
- MF10b: 히스토리 부족 시 NULL (standard fixture: 7 CPI months < 12)
- MF10c: 충분한 히스토리 시 계산값 검증 (12 monthly values, expected = 5.5/sqrt(13))
- MF10d: selected_value=NULL → zscore=NULL
- MF10e: std=0 (모든 값 동일) → zscore=NULL
- 전체 테스트: 54 passed, 1 skipped (EOD integration)

---

### 8) Gold EOD Feature v1 E2E 통합 구현
- `gold_eod_features.py`에 CLI 엔트리포인트(`parse_args`, `main`)를 추가하여 모듈 단독 실행을 지원
  - `python -m pretrend.pipeline.features.gold_eod_features --start ... --end ...`
- `eod_job.py`를 추가하여 EOD Bronze → Silver → Gold를 1회 실행으로 동기화
  - 핵심 구성: `EodJobConfig`, `EodJobRunner`, `EodJobResult`
  - 메타 로그: `data/meta/eod_job_log.parquet`
- `eod_pipeline_dag.py`에 `run_eod_gold_features_task`를 추가하고 의존 체인을 Bronze → Silver → Gold로 확장
- Gold EOD 출력 계약:
  - Grain: `(symbol, trade_date)`
  - 저장 경로: `data/gold/eod/eod_features/symbol=XXX/year=YYYY/month=MM/gold_eod_features_YYYYMM.parquet`
  - 라벨(`asset_group`, `asset_name`, `asset_subtype`)은 Silver에서 carry-forward

---

### 향후 계획
- (완료) `zscore_12m` 구현 (v1.1)
- (완료) EOD Gold Layer 설계 및 구현
- Universe(U0~U3) 계산 로직 구현

## v2026.02.10 — Calendar Pipeline v1 구현 (Bronze + Silver)

### 변경 요약
- Calendar Pipeline v1을 설계 명세 단계에서 구현 완료 단계로 전환하여, `econ_events` / `fred_vintages` Bronze→Silver 파이프라인이 실제 동작하도록 반영
- FRED 기반 Calendar Bronze ingest를 추가하여 release 증거 수집 경로를 코드로 고정
- `macro_job.py` E2E 플로우에 `bronze_econ_events`와 `silver_calendar(econ_events + fred_vintages)` 단계를 통합
- Silver Calendar 스키마를 release evidence 중심으로 경량화(`actual_value`, `value` 제거)
- Calendar 테스트 12개(ST1~ST11 + ST3 variant)를 통해 스키마/멱등성/dedup/timezone 계약 검증 완료

---

### 1) Calendar Silver 구현 완료 (`econ_events` + `fred_vintages`)
- 구현 모듈:
  - `src/pretrend/pipeline/calendar/config.py`
  - `src/pretrend/pipeline/calendar/econ_events.py`
  - `src/pretrend/pipeline/calendar/fred_vintages.py`
  - `src/pretrend/pipeline/calendar/runner.py`
- `runner.py`는 Bronze loader(`load_bronze_econ_events`, `load_bronze_fred_vintages`)와 CLI(`--target econ_events|fred_vintages|all`)를 제공
- 저장 경로(파티션 overwrite):
  - Bronze: `data/bronze/calendar/{econ_events|fred_vintages}/year=YYYY/month=MM/*.parquet`
  - Silver: `data/silver/calendar/{econ_events|fred_vintages}/year=YYYY/month=MM/*.parquet`

---

### 2) Calendar Bronze ingest 추가 (FRED release/dates + vintage API)
- `src/pretrend/pipeline/ingest/macro.py` 확장:
  - `MacroFetcher.fetch_vintages()` 추가
    - FRED observations API(`realtime_start/end`) 기반 vintage 수집
    - observation 연도 × realtime 2년 이중 청크
    - rate limit 0.5s + 429 exponential backoff
  - `MacroFetcher.fetch_econ_events()` 추가
    - FRED release/dates API 기반 release 날짜 수집
    - `release_id=10`(CPI), `release_id=50`(Employment) 반영
    - `release_id=18`(H.15)은 제외(주간/일간 릴리즈, `fred_vintages` fallback으로 커버)
    - `release_date -> observation_date`는 전월 1일 매핑(월간 지표)
  - `VintageNormalizer` / `VintageWriter`, `EconEventsNormalizer` / `EconEventsWriter` 추가

---

### 3) `macro_job.py` E2E 플로우 통합
- 변경 전:
  - `bronze_ingest -> bronze_vintages -> silver_features -> silver_calendar(fred_vintages만)`
- 변경 후:
  - `bronze_ingest -> bronze_vintages -> bronze_econ_events -> silver_features -> silver_calendar(fred_vintages + econ_events)`
- 결과적으로 Macro Job 1회 실행으로 Calendar Bronze+Silver까지 동기화 가능

---

### 4) Silver Calendar 스키마 경량화
- `econ_events Silver`에서 `actual_value` 컬럼 제거
- `fred_vintages Silver`에서 `value` 컬럼 제거
- Calendar Silver는 값(value) 저장소가 아니라 Gold PIT용 `release_date` 증거 레이어로 역할 고정

---

### 5) 테스트 및 검증
- 테스트 파일: `tests/pipeline/test_calendar.py`
- 테스트 수: 12개 (ST1~ST11 + ST3 variant)
  - Schema invariant
  - Idempotency
  - Dedup
  - Timezone normalization
- 모든 테스트는 synthetic fixture 기반이며 외부 API 호출 없음
- 검증 실행 요약:
  - 단기 실행(`--start 2024-01-01 --end 2024-06-30`): Bronze 21행, Silver 18행(econ_events)
  - 전체 실행(`--start 2015-01-01 --end 2026-02-01`): `fred_vintages` Silver 28,412행

---

### 향후 계획
- (완료) Gold Layer v1에서 Calendar(`econ_events`, `fred_vintages`)를 소비하는 PIT-safe 결합 로직 구현
- Gold release source 태깅(`econ_events` / `fred_vintages` / `assumed_t_plus_1`)과 계약 테스트 연계 강화

## v2026.02.06 — Pipeline Idempotency 강화 및 Agent 운영 기준 확정

### 변경 요약
- Macro / EOD Silver 파이프라인의 **멱등성(idempotency) 검증 수준을 파티션 invariant 기준으로 상향**
- AI Agent(Codex) 도입 범위를 **tests/docs 전용 보조 도구**로 명확히 제한하고, 운영 규칙을 문서로 고정
- 현재 구현 범위와 문서 간 **정합성(Doc Sync) 완료**

---

### 1) Silver Layer 멱등성 검증 강화

#### Macro / EOD Silver 공통
- 기존:
  - 파일 존재 여부 또는 단일 파일 overwrite 여부 중심 검증
- 개선:
  - **파티션 단위 invariant 검증**
    - 재실행 시 파티션 내 row 수 증가 없음
    - 중복 artifact 생성 없음
    - overwrite 보장

#### 테스트 설계 원칙
- 구현 세부(파일명, 내부 로직)에 결합된 assert 제거
- 의미적 불변조건(invariant) 중심 테스트로 재설계
- 향후 저장 포맷/경로 변경에도 테스트 재사용 가능하도록 구성

---

### 2) 테스트 품질 및 결합도 개선
- 파티션 전체를 기준으로 검증하도록 테스트 구조 단순화
- parquet 파일 반복 로딩/순회 로직 제거
- 테스트가 “구현을 설명”하지 않고 “결과를 검증”하도록 역할 정리

---

### 3) Agent(Codex) 도입 운영 기준 확정

#### 도입 결론
- Codex는 **설계·판단·전략·실행 주체가 아님**
- 역할:
  - 테스트 코드 초안 생성
  - 문서 동기화
  - 반복 작업 보조

#### 통제 장치
- `AGENTS.md` 고정:
  - Scope 제한 (tests/docs 중심)
  - 작은 diff (1 task / ≤300 LOC 권장)
  - public API 변경 금지
  - 멱등성/파티션 overwrite 규칙 보존
  - 검증 커맨드 명시 필수
- 브랜치 전략:
  - `codex/<task>` 단위 작업
- Task Spec에 Scope / DoD 명시

#### 면접·대외 설명 기준
- “AI가 다 했다” ❌
- “AI 초안 → 사람이 리뷰·수정·승인 → 테스트/문서로 증명” ⭕
- Agent 사용 여부 및 역할 분리는 `agent_adoption_notes.md`에 명시

---

### 4) 문서 동기화 완료
- README
- operation_guide
- agent_adoption_notes

→ 현재 코드 구현 범위(Macro/EOD Bronze→Silver, 멱등성 정책, Agent 운영 기준)와 문서 내용이 일치하도록 정렬 완료

---

### 5) 현재 스코프 및 다음 단계

#### 완료 범위
- Macro Bronze → Silver 파이프라인
- EOD Bronze → Silver 파이프라인
- 파티션 overwrite 기반 멱등성 보장
- 운영 환경을 가정한 테스트/문서/Agent 통제 구조

#### 다음 목표 (Out of scope → Next)
- Gold Layer:
  - Macro Silver + EOD Silver 결합
  - as-of join 기반 Feature Mart 설계
- Universe(U1~U3) 계산 로직 구현 및 테스트


## v2026.01.14
- Macro Pipeline 운영 정책 정리
  - DAG 매일 트리거 + 직전월 1일~전일 롤링 재처리
  - Silver Macro Feature year/month overwrite 멱등성 명시
- Gold Layer 설계 준비를 위한 Macro/EOD 정합성 문서화

## v2025.12.05 - EOD Airflow Pipeline (Bronze → Silver) 통합 및 Silver Feature Layer 구축

### 변경 요약
- EOD Bronze/Silver를 하나의 Airflow DAG(`eod_pipeline_dag`)로 통합
- 미국장 기준 "마지막 완전 거래일" 기반 Bronze ingest 자동화
- EOD Silver Feature Layer(v1) 신규 구축 (수익률/MA/ATR/RSI 포함)
- Silver Writer 멱등성 적용 및 파티션 구조 확정
- Gold Layer 설계를 위한 준비 작업 완료

---

### 1) EOD Pipeline 통합 (Bronze → Silver)
- 기존 단일 Bronze DAG를 제거하고 Macro pipeline 구조와 동일하게 **Bronze→Silver 통합 DAG** 구성
- DAG: `eod_pipeline_dag`
  - Task 1: `run_eod_bronze_ingest`
    - yfinance 기반 SPY/QQQ/VOO ingest
    - 미국장 ET 기준 "마지막 완전 거래일" 계산하여 하루 구간만 ingest
    - Bronze 저장 구조 유지:
      ```
      data/bronze/eod/daily_prices/
        source=YF/theme=GENERIC/symbol=SPY/trade_date=YYYY-MM-DD/eod.parquet
      ```
  - Task 2: `run_eod_silver_features`
    - Bronze 결과(XCom) 기반 동일 날짜/심볼로 Silver 생성
    - EOD Silver Writer는 (symbol/year/month) 파티션으로 멱등성 저장

---

### 2) EOD Silver Feature Layer 구축
- 신규 파일: `src/pretrend/pipeline/features/eod_features.py`
- Feature Set(v1):
  - **수익률:** ret_1d / log_ret_1d / ret_5d / ret_20d
  - **변동성:** vol_20d / vol_60d
  - **이동평균:** ma_5 / ma_20 / ma_60 / ma_120 / ma_ratio_5_20
  - **ATR & TR:** atr_14
  - **RSI:** rsi_14 (gain/loss SMA 기반)
  - **Volume 특성:** volume_zscore_20d
  - **Micro-structure:** gap_open, intraday_range
  - **Data Quality Flags:** is_trading_day, is_missing_imputed, is_outlier, is_partial_day
- Feature 계산 방식은 symbol 단위 groupby에서 shift/rolling 기반으로 안정화

---

### 3) EOD Silver 저장 구조 표준화
- 저장 경로: data/silver/eod/eod_features/symbol=SPY/year=2024/month=12/eod_features_202412.parquet
- 멱등성 전략: `_tmp_run={run_id}` 임시 디렉토리 생성
- 파티션 단위 atomic overwrite

---

### 4) Gold Layer 준비 단계 완료
- Gold 설계를 위해 필요한 전제조건 모두 충족:
- Macro Silver 완성
- EOD Silver v1 완성
- Airflow 기반 Bronze→Silver 자동화 환경 구축

### 향후계획
- Macro Silver + EOD Silver as-of join 구조 설계
- Gold Feature 스키마 정의
- Gold Pipeline DAG 구성(`gold_pipeline_dag`)
- 이후 NLP Bronze/Silver 추가(뉴스/FOMC/경제 리포트)
---

## v2025.12.03 - Macro Airflow Pipeline (Bronze → Silver) E2E 통합

### 변경 요약
- Macro Bronze/Silver 파이프라인을 Airflow DAG(`macro_pipeline_dag`)로 통합
- Airflow 전용 환경(`airflow-pretrend`)에서 MacroJob E2E (Bronze ingest → Silver features → Meta log) 자동 실행 성공
- 운영을 위한 환경변수 설계(`.env.airflow`) 및 개발용 런처 스크립트(`run_airflow_dev.sh`) 도입

### Airflow 환경 구성
- 별도 conda env: `airflow-pretrend`
- `AIRFLOW_HOME=/home/redtable/Desktop/ethan/pretrend/airflow_pretrend`
- `DAGS_FOLDER`를 `pretrend_ai/dags`로 지정 (`AIRFLOW__CORE__DAGS_FOLDER`)
- `run_airflow_dev.sh`에서:
  - `PROJECT_ROOT` 기반 공통 경로 설정
  - `.env.airflow`를 `set -a; source .env.airflow; set +a` 패턴으로 로드하여 환경변수 일괄 export
  - `webserver`, `scheduler`, `init-db`를 서브커맨드 형태로 실행 가능하도록 구성

### 환경변수 / 시크릿 설계
- `.env.airflow`에 운영에 필요한 핵심 변수만 정의
  - `FRED_API_KEY` : FRED 연동용 API 키
  - `PRETREND_DATA_ROOT` : `/home/redtable/Desktop/ethan/pretrend/pretrend_ai/data`
- 모든 시크릿/경로는 Git에 커밋하지 않고 `.env.airflow` + 런처 스크립트 구조로 관리

### MacroJob Airflow 통합
- DAG: `macro_pipeline_dag`
  - Task: `run_macro_job` (PythonDecoratedOperator 기반)
  - 내부에서 `MacroJobRunner.from_env()` 호출
- Airflow 실행 시 E2E 플로우:
  1. Bronze ingest
     - MacroFetcher → MacroNormalizer → MacroWriter
     - FRED에서 FEDFUNDS, 10Y YIELD 등 거시 지표 수집
     - 절대경로 기반 저장:
       - `data/bronze/macro/econ_indicators/year=YYYY/month=MM/{indicator_id}_YYYYMM.parquet`
  2. Silver macro features
     - Bronze 파티션 로딩 후 feature 계산
     - `data/silver/macro/macro_features/year=YYYY/month=MM/macro_features_YYYYMM.parquet`
  3. Meta log
     - `data/meta/macro_job_log.parquet`에 run_id, 기간, row count 등 실행 이력 기록

### 기술 이슈 해결 내역
- Airflow 태스크 내에서 `FRED_API_KEY` 미설정 오류 발생 → `.env.airflow` + `run_airflow_dev.sh`로 해결
- Parquet 저장 시 `pyarrow` 미설치로 인한 ImportError 발생 → `airflow-pretrend` 환경에 `pyarrow` 추가 설치
- `PRETREND_DATA_ROOT`를 기준으로 Bronze/Silver/Meta 경로를 절대경로로 통일 → CLI와 Airflow 간 경로 일관성 확보

### 향후 계획 (Macro 관련)
- `macro_pipeline_dag`의 `schedule_interval`을 매일 1회, 한국 시간 기준 오전(예: 09:00 KST)으로 설정하여 EOD Macro 자동 수집
- pandas `groupby.apply` FutureWarning 제거를 위한 Silver Feature 코드 리팩토링
- Macro DAG 모니터링 및 실패 알림(Slack/Email) 연동을 MLOps 단계에서 추가
---

## v2025.12.02 - FRED macro CPI ingest + parquet writer (bronze)

### 구조
  - IngestContext + BaseFetcher / BaseNormalizer / BaseWriter 공통 인터페이스 확립
  - MacroFetcher → MacroNormalizer → MacroWriter E2E 플로우 정상 동작

### FRED 연동
  - FRED API Key 환경변수로 연동 (FRED_API_KEY)
  - CPIAUCSL 기준으로 fetch/normalize/write 전부 검증 완료

### 저장 스키마
  - Bronze 스키마: indicator_id, date, value, unit, source, run_id, ingestion_ts
  - 디렉토리/파일 구조: data/bronze/macro/econ_indicators/year=YYYY/month=MM/{indicator_id}_YYYYMM.parquet

### 멱등성
  - 기준 키: (indicator_id, date)
  - 같은 파라미터로 재실행 시 파일 덮어쓰기 → 비즈니스 데이터 상태는 동일
  - run_id, ingestion_ts는 실행 이력(lineage)용 메타데이터

### Multi-indicator 확장 준비
  - FredSeriesSpec, FredMacroConfig 설계 완료
  - from_env_with_defaults()에서 CPI, Core CPI, UNRATE, FEDFUNDS, DGS10까지 한 번에 수집 가능
  - MacroFetcher는 series_list 기반 multi-series ingest 구조로 설계됨
---

## v2025.11.28

### 변경 요약
- Universe 설계를 "전 종목 기반"에서 "거시→테마→종목(U0~U3)" 구조로 전면 개편
- 한국 주식 종목은 Universe 대상에서 제외하고, 글로벌/미국 시장 중심 구조로 전환
- EOD 수집 대상은 전체 종목이 아니라 **U3 최종 Universe에 포함된 종목만**으로 한정

### 신규 문서
- `docs/universe_design.md`
  - U0: Macro Signal Detector (거시 신호 감지 및 영향력 수치화)
  - U1: Theme Prioritization (각광받을 테마 스코어링)
  - U2: Theme Universe Builder (테마 기반 주요 종목 1차 필터링)
  - U3: Growth & Flow Candidates (성장성 + 수급 기반 최종 Universe)
  - Universe와 EOD Ingest 연계 구조 정의

- `docs/data_requirements.md`
  - Macro / Theme / Stock / EOD별 필수 데이터 항목 정의
  - MVP 단계에서 수집해야 할 최소 데이터 셋(Macro 4종, Theme 3종, Stock 3종, EOD OHLCV) 명시
  - 주요 데이터 소스(FRED, Yahoo Finance, FMP 등) 개략 정리

### 설계 방향 결정 사항
- 한국 주식 종목은 Universe에서 제외하고, 미국/글로벌 종목을 기반으로 전략 설계
- 전 종목 EOD 수집은 스코프에서 제외
- Universe는 "신호 → 테마 → 종목"의 탑다운 방식으로 생성하고,
  U0~U3 각 단계의 역할과 필요 데이터 정의를 완료
## 2026-03-10

### Broker Mock DAG 독립 실행 전환
- `broker_mock_trading_dag`가 더 이상 SIM `execution_ledger`를 입력으로 사용하지 않도록 변경했다.
- broker 주문은 strategy stages(`exposure`, `what_to_hold`, `next_step`) + broker 실시간 상태를 직접 읽어 `build_broker_target_orders()`로 계산한다.
- MOCK Telegram의 `virtual_fills`는 SIM 계획 행이 아니라 `broker_fills` 기준 실제 broker 체결 요약으로 표시된다.

### Backtest SIM/SCHD 정책 비교 확장
- `v3.4.1-sim` preset을 추가해 월간 전면 리밸런싱이 없는 SIM 방식 backtest를 별도 비교 가능하게 했다.
- `BacktestConfig`에 `schd_min_weight`를 추가하고, `v3.4.1-schd-floor-20` preset으로 SCHD 최소 비중 floor 정책을 검증할 수 있게 했다.
- 장기 구간(`2006-01-03 ~ 2024-06-03`) 비교 결과:
  - `v3.4.1`: XIRR `+8.85%`, MDD `-24.79%`, Sharpe `1.63`
  - `v3.4.1-sim`: XIRR `+6.92%`, MDD `-26.88%`, Sharpe `1.67`
  - `v3.4.1-schd-floor-20`: XIRR `+6.59%`, MDD `-14.43%`, Sharpe `1.71`
- 해석:
  - SIM 방식은 XIRR 차이는 제한적이지만 장기 MDD가 크게 악화돼 현행 월간 리밸런싱 대체안으로는 부적합하다.
  - SCHD floor 정책은 MDD/Sharpe 개선과 XIRR/CAGR 악화의 trade-off를 보였고, 운영 채택은 별도 정책 판단이 필요하다.

## 2026-03-11

### ^VIX EOD Observability 편입
- `OBSERVABILITY_SET_V1`에 `^VIX`를 `VOLATILITY_INDEX` 그룹으로 추가했다.
- `^VIX`는 매매 대상이 아니라 Short Engine v1.2의 `vix_extreme` 연구/판정용 implied volatility 센서로만 사용한다.
- `eod_observability_contract.md`의 enum과 instrument table도 `39 ETFs + 1 Volatility Index` 기준으로 동기화했다.

### ^VIX 전체 구간 Backfill 완료
- `eod_job --start 2004-01-02 --end 2026-03-10 --symbols "^VIX"` 실행으로 Bronze/Silver/Gold 전체 구간 백필을 완료했다.
- Gold 산출물은 `data/gold/eod/eod_features/symbol=^VIX/`에 저장되며, `adj_close`, `ret_1d`, `vol_20d`, `ma_20` 등 P5-1b step 연구용 컬럼을 포함한다.
## 2026-03-11

### Strategy Engine
- Short Engine v1.2: `vix_extreme(vix_close > 35)`를 secondary PANIC의 5번째 확인 신호로 추가했다.
- VIX 데이터 결측 시 `vix_extreme=False`로 fail-open 처리해 기존 v1.1 동작과의 backward compatibility를 유지했다.
- RELIEF 조건에는 VIX를 추가하지 않았다.

## 2026-03-12

### Strategy Engine
- Short Engine v1.3: `skew_extreme_flag`를 secondary PANIC의 추가 확인 신호로 통합했다.
- 현재 구현 기준 secondary PANIC은 `vol_spike`, `wide_intraday`, `flight_to_safety`, `smallcap_stress`, `vix_extreme`, `skew_extreme`의 6개 신호 중 3개 이상일 때만 발동한다.
- `skew_extreme_flag` 로드 실패는 `0`으로 fail-open 처리한다.

### Backtest Validation
- 장기 `v2` 비교(`2006-01-03 ~ 2024-06-03`)에서 `v1.2`와 `v1.3`의 성과 지표는 사실상 동일했다.
  - `v1.2`: XIRR `+7.42%`, MDD `-16.21%`, Sharpe `1.68`, PANIC `172`
  - `v1.3`: XIRR `+7.42%`, MDD `-16.21%`, Sharpe `1.68`, PANIC `152`
- 해석:
  - `v1.3`는 PANIC 횟수를 줄였지만(`-20`), `GFC`와 `2022` 첫 PANIC은 늦어졌다.
  - 장기 `v2` 기준으로는 `false positive` 억제 효과만 확인됐고, 성과 개선 근거는 아직 부족하다.
  - 비교 산출물: `result/backtest_compare/skew_engine_v12_vs_v13_20260312.md`

## 2026-03-25

### Telegram Report
- `strategy_engine_dag`의 Telegram 출력이 Signal 본문과 AI 해석을 별도 2메시지로 고정 발송하던 구조에서, `main + support` 기반 1~2 메시지 조합 구조로 바뀌었다.
- AI 해석은 별도 `🤖 Pretrend AI 해석` 메시지가 아니라 본문 안 `핵심 판단 해석` 섹션으로 통합된다.
- 보조 운영 정보(`next step`, `시장 근거`, `진단 요약`, `전술 그룹`, `전술 ETF`)는 support block으로 분리되며, 전체 길이가 짧으면 본문과 함께 1개 메시지로 발송된다.

### Report Analyzer Transition
- `report_context.generate_llm_analysis()`가 direct Gemini/Ollama owner 구조에서 `Codex report analyzer session` 우선 구조로 전환됐다.
- transitional 단계에서는 별도 DB를 만들지 않고, 기존 control-plane DB의 `sessions(role='analyzer')`와 `conversation_summary(role='analyzer')`를 report workspace memory로 재사용한다.
- analyzer 경로 실패 시 기존 direct provider(Gemini/Ollama) 경로로 fallback해 초기 전환 안정성을 유지한다.
- 해석 앵커(2026-03-30):
  - 여기서의 `Telegram Report`, `Report Analyzer`, `report workspace memory`는 현재 용어의 `analyzer_report` 축이다.
  - 이 항목은 `audit_report`나 `task_review_report` 체계를 설명하지 않는다.

### Paper / Mock Compact
- `PAPER_RESULT` Telegram 포맷터가 긴 운영/실행 로그 나열 중심에서 `본문 우선 + compact 실행 블록` 구조로 재배치됐다.
- `PnL / NAV / 포지션 변화 / 상위 보유 / 핵심 리스크`는 본문에 남기고, 브로커 인증/체결/실행 식별/그룹 게이트/체결 세부는 하단 compact block으로 이동했다.
- payload schema는 유지하고 표시 우선순위만 바꿨다.
