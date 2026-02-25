# Next Step Signal — Contract (SOT)

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
- [4. Outputs](#4-outputs)
- [5. Axis×Horizon Evidence Matrix (4x3)](#5-axishorizon-evidence-matrix-4x3)
- [6. Invariants](#6-invariants)
- [7. DoD](#7-dod)

참조:
- `docs/strategy_engine_design.md`
- `docs/architecture/axis_horizon_dependency_contract.md`
- `docs/architecture/market_structure_long_contract.md`
- `docs/architecture/market_structure_mid_contract.md`
- `docs/architecture/market_structure_short_contract.md`

## 1. 문서 목적
### 책임
- 현재 상태(3-state: long/mid/short)와 다음 스텝 가설(1m/3m)의 출력 계약을 고정한다.
- Telegram/리포트 소비용 4축 근거 서술 인터페이스를 고정한다.
- 12셀(4축×3horizon)을 실행 신호가 아닌 진단 KPI 계층으로 정의한다.

### Non-goals
- 실거래 주문/집행 판단 직접 생성
- ML 모델 학습/튜닝 기준 정의

## 2. Scope & Non-Goals
### Scope
- 입력 상태(long_phase, mid_regime, short_signal) 기반 다음 스텝 가설 생성
- 4축(매크로/가격/수급/심리) 근거 문구 생성
- 12셀 진단 KPI(coverage, unknown_ratio) 계산

### Non-goals
- 12셀 개별 셀을 독립 실행 신호로 승격
- 가설 정확도 성능 보장

## 3. Inputs
### 책임
- Next Step Signal의 최소 입력을 고정한다.

### Non-goals
- Axis 엔진 내부 산출식 정의

| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| trade_date | DATE | Y | 기준일 |
| long_phase | TEXT | Y | 장기 상태 ENUM |
| mid_regime | TEXT | Y | 중기 상태 ENUM |
| short_signal | TEXT | Y | 단기 상태 ENUM |
| long_detail_json | TEXT(JSON) | N | 장기 근거 상세 |
| mid_detail_json | TEXT(JSON) | N | 중기 근거 상세 |
| short_detail_json | TEXT(JSON) | N | 단기 근거 상세 |

결측 처리:
- detail JSON 결측/파싱 실패 시 fail-open 문구를 출력한다.

## 4. Outputs
### 책임
- 다음 스텝 가설 + 근거 + 진단 인터페이스를 고정한다.

### Non-goals
- 포트폴리오 비중 조정 명령 생성

| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| trade_date | DATE | Y | 기준일 |
| bias_1m | TEXT | Y | `RISK_ON_BIAS`, `NEUTRAL_BIAS`, `RISK_OFF_BIAS`, `UNKNOWN` |
| confidence_1m | FLOAT | Y | 0~1 |
| bias_3m | TEXT | Y | `RISK_ON_BIAS`, `NEUTRAL_BIAS`, `RISK_OFF_BIAS`, `UNKNOWN` |
| confidence_3m | FLOAT | Y | 0~1 |
| evidence_axis_macro | TEXT | Y | 매크로/정책 서술 |
| evidence_axis_price | TEXT | Y | 가격 서술 |
| evidence_axis_flow | TEXT | Y | 수급/구조 서술 |
| evidence_axis_sentiment | TEXT | Y | 심리 서술 |
| evidence_quality_score | FLOAT | N | 품질 점수(확장 포트, nullable) |
| evidence_unknown_ratio | FLOAT | Y | 0~1 |
| diag_12slot_coverage | FLOAT | Y | 0~1 |
| diag_12slot_quality | TEXT | Y | `양호`, `경고` |

## 5. Axis×Horizon Evidence Matrix (4x3)
### 책임
- 12셀의 역할을 진단 계층으로 명시한다.

### Non-goals
- 12셀 전부를 실행 신호로 사용

- 12셀은 독립 실행 신호가 아니라 **evidence diagnostics layer**다.
- 현재 실행/의사결정 핵심 출력은 3-state(long/mid/short)다.
- 12셀은 coverage/unknown_ratio/축별 일관성 점검용 보조 KPI로 사용한다.

## 6. Invariants
### 책임
- 설명 가능성과 fail-open 동작을 보장한다.

### Non-goals
- 미래 성과 보장

- 4축 근거 서술 필드는 항상 생성되어야 한다.
- 근거 결측/파싱 실패 시 기본 문구(`영향 근거 없음`)로 대체한다.
- 12셀 진단은 quality 표시로 압축되며, 실행 신호를 직접 대체하지 않는다.
- `evidence_unknown_ratio = 1 - diag_12slot_coverage` 제약을 유지한다.

## 7. DoD
### 책임
- 계약 기반 검증 기준을 제공한다.

### Non-goals
- 백테스트 수익성 검증

- **NSS1**: 입력 필수 컬럼/ENUM 검증
- **NSS2**: bias/confidence 출력 필드 생성 검증
- **NSS3**: 4축 근거 문구 4줄 항상 출력 검증
- **NSS4**: detail 결측 시 fail-open 문구 출력 검증
- **NSS5**: 12셀 진단 지표(`diag_12slot_coverage`, `evidence_unknown_ratio`) 계산 검증
- **NSS6**: 4축 근거 서술 필드가 항상 생성됨을 검증(결측 시 fallback)
- **NSS7**: 12셀 진단 지표(`coverage`, `unknown_ratio`) 일관성 검증

---

## Change History
| Date | Summary | References |
| --- | --- | --- |
| 2026-02-24 | Next Step Signal 계약 신규 추가: 3-state + 4축 근거 + 12셀 진단 KPI 계층 정의 | docs/changelog.md |
