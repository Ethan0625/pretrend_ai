v2026.02.24

# Pretrend AI — Agent Memory (Stable)

## 1) 목적
- 이 문서는 변동성이 낮은 사실/불변식/SOT 우선순위만 보관한다.
- 로드맵/할 일/세션 실행 기록은 포함하지 않는다.
- 변동 수치(예: 테스트 통과 건수)는 기록하지 않고 최신 pytest/CI 로그를 참조한다.

Source:
- `docs/operation/agent_adoption_notes.md (#4-운영-규칙-고정-agentsmd)`
- `docs/operation_guide.md (#agent-assisted-development-codex)`

## 2) 프로젝트 정체성
- 현재 성격: 계약 중심 아키텍처 + 리서치 실행 인프라.
- 실행 레벨은 단계적으로 관리한다:
  - Level 1: Backtest/Walk-forward + Explainable Report
  - Level 2: Paper trading + Alerts
  - Level 3: Live broker (현재 범위 밖)

Source:
- `docs/architecture/strategy_architecture.md (#2-전체-전략-아키텍처)`
- `docs/architecture/strategy_engine_design.md (#section-a--one-page-summary)`
- `docs/roadmap/milestones.md (#6-전략-아키텍처-로드맵-risk-control)`

## 3) 용어 사전 (혼동 방지)
- `mid_regime`: 중기 성향 라벨 (`RISK_ON/NEUTRAL/RISK_OFF/UNKNOWN`)
- `risk_gate`: 단기 공황 차단 게이트 (`False`면 PANIC 상황)
- `run_universe`: 전술 유니버스 실행 허용 스위치
- 사용자 표시 별칭: `is_panic = not risk_gate`

Source:
- `docs/architecture/strategy_engine_design.md (#section-f--invariants-core-contracts)`
- `docs/operation_guide.md (#telegram-알림-설정)`
- `docs/architecture/market_structure_composer_contract.md (#4-outputs-필수)`

## 4) 불변식 참조 요약
- PIT: `selected_release_date < trade_date`
- Snapshot 저장: `_tmp_run` 경유 후 atomic rename + 동일 파티션 overwrite
- 결측 처리: fail-open, `UNKNOWN` 허용, 스키마 유지
- 레이어 경계: Strategy는 Gold read-only consumer
- Universe 분리: Execution Universe(ETF) vs Research Universe(Stock U0~U3)
- 결과 재현성: 비교 가능한 백테스트 결과는 `save_result()` 산출물 + registry를 기준으로 판단
- Text LLM은 영구 observer-only이며 Strategy/Paper/Backtest 실행 입력으로 사용하지 않는다
- `llm_feature`는 text-only LLM 산출물이고, `interpretation_summary`는 signal+text 결합 해석문이다

Source:
- `docs/architecture/gold_design_contract.md §9`
- `docs/architecture/calendar_design_contract.md (#5-idempotent-write-strategy)`
- `docs/architecture/strategy_engine_design.md (#section-e--snapshot-storage)`
- `docs/architecture/strategy_engine_design.md (#section-a--one-page-summary)`
- `docs/architecture/universe_contract.md (#2-scope--non-goals)`
- `docs/roadmap/milestones.md (#m2-universe-stock-pipelineu0u3-구현-68주)`
- `docs/operation_guide.md (#backtest-engine-실행)`
- `docs/architecture/text_observability_contract.md (#14-운영-경계-정책-v1)`

## 5) SOT 우선순위 맵
- 전략 단일 SOT: `docs/architecture/strategy_engine_design.md`
- 계약 단일 SOT: `docs/architecture/*_contract.md`
- 운영 실행 SOT: `docs/operation_guide.md`
- 변경 이력 SOT: `docs/changelog.md` (과거 원문 보존)
- 에이전트 작업 규칙 SOT: `.agent/WORKFLOW.md`, `.agent/CHANGE_GATES.md`
- 커밋/PR 규칙 SOT: `.agent/WORKFLOW.md (#6-커밋pr-규칙)`

신규 계약(전이예측/검증):
- `docs/architecture/next_step_signal_contract.md`
- `docs/architecture/walk_forward_validation_contract.md`

해석 우선순위:
1. Contract/Invariants
2. Repro(Idempotency/Overwrite)
3. Observability
4. Execution Features
5. Performance Optimization

운영 preset 원칙:
- 실험 preset은 운영 preset과 분리한다.
- 운영 기본 preset은 changelog/operation guide에서 확정된 값을 따른다
  (현재 기준: `v3.4.1`, `v3.4.2-phase/v3.4.2a`는 실험군).

Text 운영 원칙:
- `text_pipeline_dag`는 `Bronze -> Silver -> Gold(rule) -> Gold LLM` 순서로 동작한다.
- Gold LLM 산출물은 `text_annotation_v2` taxonomy 구조를 사용한다.
- SEC adapter는 `filings.recent` + `filings.files`를 모두 순회하도록 확장되었다.

Paper/Broker 운영 원칙:
- Paper execution은 `SIM`과 `MOCK(KIS broker)`를 분리 저장/표시한다.
- `paper_trading_dag`는 SIM 기준 EOD 시뮬레이션 결과를 생성한다.
- `broker_mock_trading_dag`는 strategy stages(`exposure`, `what_to_hold`, `next_step`)를 직접 읽어 broker 잔고/현재가 기반 독립 주문 계획을 생성한다 (P4-2 이후, SIM execution_ledger 의존 없음).
- SIM과 broker_mock의 실행 모델 차이: 초기자금(환경변수 vs KIS 잔고), DCA(SIM 월 자동 주입 vs broker 없음), 가격(Gold EOD vs KIS 실시간)은 의도적 차이이며, 요일 규칙/분할매도/SCHD 매도 금지/Level 2 가드레일은 P4-4에서 정합 구현 예정이다.
- KIS MOCK 미국주식 주문은 현재가 앵커 기반 지정가(`ORD_DVSN=00`)로 전송한다.
- broker 주문 상태는 `ACCEPTED / PARTIAL_FILLED / FILLED`로 구분하며, 체결 조회 미완료 구간은 `ACCEPTED`로 남을 수 있다.

Source:
- `docs/changelog.md (#현재-유효-규칙-as-is)`
- `docs/architecture/strategy_architecture.md (#1-문서-목적)`
- `docs/operation_guide.md (#agent-assisted-development-codex)`
- `docs/architecture/text_observability_contract.md (#13-llm-observer-layer--v1-계약-gate-d)`

## 6) 포함/제외 경계
포함:
- 안정적 사실
- 불변식 요약
- SOT 링크

제외:
- TODO/작업 큐
- 세션 실행 로그
- 테스트/성과 수치 고정 기록

운영 기록 필요 시:
- `.agent/RUN_LOG.md`에 세션별 실행 결과를 기록한다.
