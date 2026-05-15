v2026.02.24

# Change Gates (Contract-First)

## 1) 기본 원칙
- 계약 선행 원칙: SOT/Contract 정리 없이 구현을 진행하지 않는다.
- 변경 영향이 불변식/그레인/키를 건드리면 구현보다 영향 분석 보고를 우선한다.
- 에이전트 행동 규칙은 본 문서와 `.agent/WORKFLOW.md`를 단일 기준으로 유지한다.

Source:
- `docs/strategy_architecture.md (#1-문서-목적)`
- `docs/changelog.md (#현재-유효-규칙-as-is)`

## 2) STOP RULES (강제)
1. 변경이 Grain/Key 또는 Invariant 변화를 암시하면:
   - 즉시 구현 중지
   - 영향 리포트만 제출(변경 범위, 깨지는 계약, 마이그레이션 필요성)
2. 외부 API 추가가 rate-limit/secret/ToS 리스크를 동반하고 완화책이 없으면:
   - 즉시 구현 중지
   - 리스크 리포트만 제출(완화책/운영비용/법적 제약 포함)

Source:
- `docs/architecture/gold_design_contract.md §9`
- `docs/architecture/calendar_design_contract.md (#5-idempotent-write-strategy)`
- `docs/data_ingest_datasources.md (#9-텍스트-데이터-소스-text-ingest)`

## 3) 변경 유형별 게이트

### Gate A — Grain/Key 변경
- 필요 산출물:
  - 계약 문서 변경안
  - 파티션/스냅샷 마이그레이션 계획
  - 회귀 테스트 계획
- 미충족 시: STOP RULE #1 적용

### Gate B — Invariant 변경
- 필요 산출물:
  - 변경 전/후 불변식 비교표
  - 영향 모듈 맵
  - 롤백 계획
- 미충족 시: STOP RULE #1 적용

### Gate C — New Layer 추가
- 필요 산출물:
  - 레이어 책임/경계 정의
  - read/write ownership 정의
  - 운영 관측 항목

### Gate D — External API 추가
- 필요 산출물:
  - Rate-limit 대응
  - Secret 관리 방식
  - ToS/라이선스 체크
  - fail-open 설계
- 미충족 시: STOP RULE #2 적용

### Gate E — Snapshot Schema 변경
- 필요 산출물:
  - backward compatibility 전략
  - 과거 스냅샷 fallback 규칙
  - reader 영향 분석
- 적용 메모:
  - `axis_horizon_state` detail JSON 컬럼 추가 시 Telegram/report fallback을 동시 구현한다.

### Gate F — 용어/해석 변경
- 필요 산출물:
  - 용어 사전 업데이트
  - Telegram/보고서 해석 문구 동기화
  - changelog 해석 앵커 반영

### Gate G — Validation Status 규칙 변경
- 필요 산출물:
  - Tier-1/Tier-2 정의서 업데이트
  - `PASS/PASS_WITH_WARNING/FAIL` 상태 전이 표
  - 테스트 케이스(통과/경고/실패) 3종

## 4) 승인 기준 (Go/No-Go)
- Go 조건:
  - 계약/불변식/멱등성/운영 문서가 상호 정합
  - 테스트/검증 경로가 존재
- No-Go 조건:
  - STOP RULE 트리거 발생
  - 계약 없는 구현 선행

Source:
- `docs/operation_guide.md (#agent-assisted-development-codex)`
- `docs/strategy_engine_design.md (#section-f--invariants-core-contracts)`
