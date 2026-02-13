# Allocation Engine — Contract (SOT)

## Document Status
| Item | Value |
| --- | --- |
| Status | Active |
| Structure Policy | 구조는 고정, 기능은 확장 |
| Effective Date | 2026-02-13 |
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
- [4. Rules](#4-rules)
- [5. Outputs](#5-outputs)
- [6. Grain / Key](#6-grain--key)
- [7. Invariants](#7-invariants)
- [8. DoD](#8-dod)

참조:
- `docs/strategy_architecture.md`
- `docs/architecture/market_structure_composer_contract.md`
- `docs/architecture/policy_config_contract.md`
- `docs/architecture/universe_contract.md`
- `docs/architecture/gold_design_contract.md`
- `docs/architecture/calendar_design_contract.md`
- `docs/architecture/eod_observability_contract.md`

## 1. 문서 목적
### 책임
- Allocation Engine v0의 입력/출력/불변식을 고정한다.
- 총 투자 비율 조절(`invested_ratio`)을 계약 형태로 명확히 한다.

### Non-goals
- Universe 내부 종목 가중치 조절
- 수치 튜닝(가중치/컷오프/최적화)

## 2. Scope & Non-Goals
### Scope
- 주기 기반 총 투자 비율 조절
- `adjustment_limit` 기반 분할 조정
- `risk_gate` 기반 증가 차단 브레이크

### Non-goals
- 즉시 올인/올아웃 실행
- v1+ 고도화(`volatility-aware`, `regime-weighted`) 구현

## 3. Inputs
### 책임
- Allocation 판단에 필요한 최소 입력 스키마를 고정한다.

### Non-goals
- 입력 생성 파이프라인 구현

입력 소스:
1. **Composer 출력** — 정책 파라미터(resolved) 및 게이트 신호
2. **이전 상태** — 현재 투자 비율

Composer 출력에서 소비하는 필드:

| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| trade_date | DATE | Y | 기준일 |
| target_invested_lower | FLOAT | Y | Policy Config에서 resolve된 목표 하한 |
| target_invested_upper | FLOAT | Y | Policy Config에서 resolve된 목표 상한 |
| adjustment_limit | FLOAT | Y | Policy Config에서 resolve된 주기당 최대 조정폭 |
| step_size | FLOAT | Y | Policy Config에서 resolve된 조정 단위 |
| risk_gate | BOOLEAN | Y | 증가 허용 여부 |
| run_universe | BOOLEAN | Y | Universe 실행 허용 신호 |
| policy_profile_id | TEXT | Y | 적용된 정책 식별자 |

이전 상태 입력:

| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| current_invested_ratio | FLOAT | Y | 현재 총 투자 비율 |

입력 예시:

```yaml
# Composer 출력에서 추출
trade_date: 2026-02-17
target_invested_lower: 0.30
target_invested_upper: 0.50
adjustment_limit: 0.10
step_size: 0.05
risk_gate: true
run_universe: true
policy_profile_id: RC_V0_DEFAULT

# 이전 상태
current_invested_ratio: 0.62
```

## 4. Rules
### 책임
- v0 조정 규칙을 수치 튜닝 없이 형태로만 고정한다.

### Non-goals
- 목표 범위/조정폭 최적값 정의

- 목표 범위 밖이면 `adjustment_limit` 이내에서만 이동
- `risk_gate=false`이면 INCREASE 금지
- `run_universe=false`이면 증가 금지(유지 또는 감소만 허용)
- 조정은 총 투자 비율 단일 축에서만 수행

## 5. Outputs
### 책임
- 실행 가능한 action plan 형식을 정의한다.

### Non-goals
- 절대 금액/종목별 주문 수량 산출

| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| trade_date | DATE | Y | 기준일 |
| action | TEXT | Y | `INCREASE`, `DECREASE`, `HOLD` |
| next_invested_ratio | FLOAT | Y | 다음 주기 목표 총 투자 비율 |
| delta_ratio | FLOAT | Y | 조정 비율 |
| blocked_by_risk_gate | BOOLEAN | Y | risk_gate로 증가 차단 여부 |
| notes | ARRAY<TEXT> | N | 판단 메모 |

## 6. Grain / Key
### 책임
- 출력 유일성 기준을 명시한다.

### Non-goals
- 멀티 포트폴리오 동시 관리

- Grain: `(trade_date)`
- Key: `(trade_date)`

## 7. Invariants
### 책임
- v0 핵심 제약을 강제한다.

### Non-goals
- 투자 성과 보장

- `next_invested_ratio`는 `[0.0, 1.0]` 범위를 벗어나지 않는다.
- `abs(delta_ratio) <= adjustment_limit`
- `risk_gate=false`이면 `action != INCREASE`
- `run_universe=false`이면 `action=INCREASE` 금지
- 즉시 올인/올아웃 금지(단일 주기에서 극단 이동 금지)
- `step_size > 0`이면 `delta_ratio`는 `step_size` 단위로 양자화된다(rounding_policy 적용)
- Allocation은 Composer 출력만 의존하며, Policy Config를 직접 참조하지 않는다.

## 8. DoD
### 책임
- 계약 기반 검증 기준을 제공한다.

### Non-goals
- 백테스트 성능 검증

- **AE1**: 입력/출력 필수 컬럼 및 타입 검증
- **AE2**: `adjustment_limit` 제약(`abs(delta_ratio) <= adjustment_limit`) 검증
- **AE3**: `risk_gate=false` 시 증가 차단 검증
- **AE4**: `run_universe=false` 시 증가 차단 검증

---

## Change History
| Date | Summary | References |
| --- | --- | --- |
| 2026-02-13 | 파일명 버전 제거 및 문서 표준 블록(Document Status/Capability Matrix) 적용 | docs/changelog.md |
