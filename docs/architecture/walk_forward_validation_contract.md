# Walk-Forward Validation — Contract (SOT)

## Document Status
| Item | Value |
| --- | --- |
| Status | Active |
| Structure Policy | 구조는 고정, 기능은 확장 |
| Effective Date | 2026-02-24 |
| Change Tracking | docs/changelog.md |

## Capability Matrix
| Capability | Status | Notes |
| --- | --- | --- |
| Core scope | Active | 본 문서의 계약/설계 범위 |
| Extension ports | Reserved | v1+ 확장 포트는 인터페이스만 정의 |
| Numeric scoring/tuning | Not supported | 본 문서 범위에서 금지 |

## TOC
- [1. 문서 목적](#1-문서-목적)
- [2. Scope & Non-Goals](#2-scope--non-goals)
- [3. Inputs](#3-inputs)
- [4. Validation Tiers](#4-validation-tiers)
- [5. Outputs](#5-outputs)
- [6. Status Transition Rules](#6-status-transition-rules)
- [7. Invariants](#7-invariants)
- [8. DoD](#8-dod)

참조:
- `docs/architecture/next_step_signal_contract.md`
- `docs/strategy_engine_design.md`
- `docs/architecture/allocation_engine_contract.md`
- `docs/architecture/paper_execution_ledger_contract.md`

## 1. 문서 목적
### 책임
- Walk-forward 검증의 성과 KPI(1차) + 진단 KPI(2차) 이중 구조를 고정한다.
- 검증 결과 상태(`PASS`, `PASS_WITH_WARNING`, `FAIL`) 전이 규칙을 고정한다.

### Non-goals
- 성과 KPI 임계값 최적화
- 실거래 차단 정책 자동 집행

## 2. Scope & Non-Goals
### Scope
- 기간별 백테스트 성과 검증
- 기간별 12셀 진단 KPI 평가
- Tier-1/Tier-2 결합 상태 산출
- v3 검증 시 `next_step_signal snapshot` 기반 진단 입력 소비

### Non-goals
- 전략 로직 변경
- 타임머신/완전 PIT 백테스트 보장

## 3. Inputs
### 책임
- Walk-forward 검증 입력 인터페이스를 고정한다.

### Non-goals
- 윈도우 생성 정책 최적화

| 입력 | 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| 성과 지표 | cagr | FLOAT | Y | 연환산 수익률 |
| 성과 지표 | max_drawdown | FLOAT | Y | 최대 낙폭 |
| 성과 지표 | sharpe_ratio | FLOAT | Y | 샤프 |
| 성과 지표 | excess_cagr | FLOAT | N | 벤치마크 대비 CAGR |
| 진단 지표 | diag_12slot_coverage | FLOAT | N | 12셀 커버리지 |
| 진단 지표 | diag_unknown_ratio | FLOAT | N | UNKNOWN 비율 |
| 진단 지표 | diag_axis_consistency | FLOAT | N | 축 일관성 근사 |
| 진단 지표 | hazard_non_null_ratio | FLOAT | N | hazard_5d/10d/20d/60d/120d 비결측 비율(평균) |
| 진단 지표 | diag_calibration_error | FLOAT | N | 간이 Brier calibration error (hazard_10d) |
| 진단 지표 | diag_hazard_bucket_monotonicity | FLOAT | N | hazard bucket 단조성(high-low) |
| 입력 소스 | next_step_signal snapshot | TABLE | N | v3 검증 시 우선 입력 소스 |

## 4. Validation Tiers
### Tier-1 (성과 KPI)
- 핵심 합격 게이트
- 항목: CAGR / MDD / Sharpe / Excess CAGR

### Tier-2 (진단 KPI)
- 보조 진단 게이트
- 항목: 12셀 coverage / unknown ratio / 축별 일관성

원칙:
- Tier-1이 1차 게이트다.
- Tier-2는 경고 판단용 2차 게이트다.

## 5. Outputs
### 책임
- Tier별 결과 및 최종 상태를 고정한다.

### Non-goals
- 자동 재튜닝 실행

| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| window_start | DATE | Y | 시작일 |
| window_end | DATE | Y | 종료일 |
| tier1_pass | BOOLEAN | Y | Tier-1 합격 여부 |
| tier2_warning | BOOLEAN | Y | Tier-2 경고 여부 |
| validation_status | TEXT | Y | `PASS`, `PASS_WITH_WARNING`, `FAIL` |

## 6. Status Transition Rules
### 책임
- 상태 전이를 결정론적으로 고정한다.

### Non-goals
- 예외 수동 개입 규칙 정의

- Tier-1 통과 + Tier-2 경고 없음 -> `PASS`
- Tier-1 통과 + Tier-2 경고 있음 -> `PASS_WITH_WARNING`
- Tier-1 실패(진단 무관) -> `FAIL`
- validation 결과는 품질 게이트이며, 운영 실행 차단 로직을 직접 수행하지 않는다.

## 7. Invariants
### 책임
- 성과 실패 우선 원칙을 강제한다.

### Non-goals
- 경고 상태 자동 차단

- Tier-1 실패 시 `validation_status`는 항상 `FAIL`이다.
- Tier-1 통과 시에만 `PASS`/`PASS_WITH_WARNING`이 가능하다.
- 진단 지표 결측 시 fail-open으로 `tier2_warning=False`를 허용한다.
- v3에서는 `next_step_signal` 진단 컬럼이 있으면 이를 우선 사용하고, 없으면 AHS detail 재계산 fallback을 허용한다.
- hazard 진단(`diag_calibration_error`, `diag_hazard_bucket_monotonicity`)은 Tier-2 경고 판정에만 사용한다.
- 지평 축은 거래일 기준 `5/10/20/60/120D`를 기본으로 사용한다.

## 8. DoD
### 책임
- 계약 기반 검증 기준을 제공한다.

### Non-goals
- 실제 운영 승인 절차 대체

- **WFV1**: Tier-1 KPI 컬럼/타입 검증
- **WFV2**: Tier-2 KPI 컬럼/타입 검증
- **WFV3**: 상태 전이 규칙(`PASS`, `PASS_WITH_WARNING`, `FAIL`) 검증
- **WFV4**: Tier-1 실패 우선(`FAIL`) 검증
- **WFV5**: 진단 지표 결측 시 fallback 처리 검증
- **WFV6**: Tier-1/Tier-2 결과 동시 출력 검증
- **WFV7**: `PASS/PASS_WITH_WARNING/FAIL` 상태 전이 규칙 검증
- **WFV8**: v3 검증 시 `next_step_signal snapshot` 입력 경로 검증
- **WFV9**: hazard 진단 KPI(calibration/monotonicity) 계산 및 Tier-2 반영 검증
- **WFV10**: 저장된 summary/registry만으로 동일 비교표 재생성 검증(backtest rerun-free 비교)

---

## Change History
| Date | Summary | References |
| --- | --- | --- |
| 2026-02-25 | Tier-2에 hazard 품질 KPI(calibration error, bucket monotonicity) 추가 | docs/changelog.md |
| 2026-02-25 | v3 검증 입력 소스를 `next_step_signal snapshot` 우선으로 명시 | docs/changelog.md |
| 2026-02-24 | Walk-forward 이중 검증 계약 신규 추가: Tier-1 성과 + Tier-2 12셀 진단 KPI | docs/changelog.md |
