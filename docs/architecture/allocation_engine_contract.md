# Allocation Engine — Contract (SOT)

Markers: architecture, contract, legacy
Status: legacy

> 🔒 **Legacy Execution Reference — 자동매매·자산배분 영역**
>
> 본 문서는 과거 실행 실험 계약을 보존하기 위한 reference입니다.
> 2026-05-12부터 운영 중단 상태이며, 현재 market data platform의 공개 운영 표면이 아닙니다.
> 참조: [`track_separation.md`](./track_separation.md)

## 문서 상태
| Item | Value |
| --- | --- |
| Status | **Frozen (legacy execution 운영 중단, 2026-05-12~)** |
| Structure Policy | 구조는 고정, 기능은 확장 |
| Effective Date | 2026-02-25 |
| Change Tracking | docs/changelog.md |

## 기능 매트릭스
| 기능 | 상태 | 비고 |
| --- | --- | --- |
| Core scope | Active | 본 문서의 계약/설계 범위 |
| Extension ports | Reserved | v1+ 확장 포트는 인터페이스만 정의 |
| Numeric scoring/tuning | Not supported | 본 문서 범위에서 금지 |

## 목차
- [1. 문서 목적](#1-문서-목적)
- [2. 범위와 제외 범위](#2-scope--non-goals)
- [3. Inputs](#3-inputs)
- [4. Rules](#4-rules)
- [5. Outputs](#5-outputs)
- [6. Grain / Key](#6-grain--key)
- [7. Invariants](#7-invariants)
- [8. DoD](#8-dod)

참조:
- `docs/architecture/strategy_architecture.md`
- `docs/architecture/market_structure_composer_contract.md`
- `docs/architecture/policy_config_contract.md`
- `docs/architecture/universe_contract.md`
- `docs/architecture/gold_design_contract.md`
- `docs/architecture/calendar_design_contract.md`
- `docs/architecture/eod_observability_contract.md`
- `docs/architecture/next_step_signal_contract.md`
- `docs/architecture/group_transition_signal_contract.md`

## 1. 문서 목적
### 책임
- Allocation Engine(v0/v1/v2/v3/v3.1/v3.2/v3.3/v3.4/v3.4.1/v3.4.2-phase/v3.4.2a)의 입력/출력/불변식을 고정한다.
- 총 투자 비율 조절(`invested_ratio`)을 계약 형태로 명확히 한다.

### 제외 범위
- Universe 내부 종목 가중치 조절
- 수치 튜닝(가중치/컷오프/최적화)

## 2. 범위와 제외 범위
### Scope
- 주기 기반 총 투자 비율 조절
- `adjustment_limit` 기반 분할 조정
- `risk_gate`/`run_universe` 기반 증감 허용 규칙

### 제외 범위
- 즉시 올인/올아웃 실행
- v3+ 고도화(`volatility-aware`, `regime-weighted`) 구현
  - 단, v3 인터페이스 포트(`next_step_bias`)는 본 계약에 정의

## 3. Inputs
### 책임
- Allocation 판단에 필요한 최소 입력 스키마를 고정한다.

### 제외 범위
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
- allocation mode별 조정 규칙을 수치 튜닝 없이 형태로 고정한다.

### 제외 범위
- 목표 범위/조정폭 최적값 정의

- 공통:
  - 조정은 총 투자 비율 단일 축에서만 수행
  - `run_universe=false`이면 `INCREASE` 금지(모든 mode 공통)
  - `next_invested_ratio`는 `[0.0, 1.0]` 범위를 유지
  - `abs(delta_ratio) <= adjustment_limit` 제약 유지
  - `step_size > 0`이면 양자화 규칙을 적용
- v0(range-maintenance):
  - 목표 범위(`[target_invested_lower, target_invested_upper]`) 기반 유지
  - `risk_gate=false`이면 `INCREASE` 금지
- v1(target-seeking), v2(2D target-seeking):
  - 상태 기반 목표 비율 추적(target-seeking)
  - `risk_gate=false`여도 `INCREASE` 허용(저점매수)
- v3(target-seeking + next_step soft adjustment):
  - `v3 = f(long_phase, mid_regime, next_step_bias_20d)` 형태를 따른다.
  - `next_step_bias_20d`가 유일한 실행 기준 bias다(`bias_1m/3m` alias 미사용).
  - `next_step_bias_20d`은 `next_step` 저장본(snapshot + history) 우선 소비를 원칙으로 한다.
  - 저장본 결측 시 fail-open(`UNKNOWN -> NEUTRAL_BIAS`) fallback을 허용한다.
  - bias는 목표 비율 강도 조절용이며, 하드 게이트를 대체하지 않는다.
- v3.1(target-seeking + monthly lock):
  - v3 규칙을 유지하되 `bias_20d`를 월 단위로 lock해 사용한다.
  - 월중에는 동일 lock bias를 유지한다.
- v3.2(monthly lock + shock override, Hypothesis):
  - 기본은 v3.1과 동일한 월간 lock을 사용한다.
  - 단, shock streak 충족 시 `next_step_bias_effective`로 override를 허용한다.
    - `short_signal=PANIC` 2거래일 연속 → `RISK_OFF_BIAS`
    - `mid_regime=RISK_OFF` 3거래일 연속 → `NEUTRAL_BIAS`
  - override 발생 후 5거래일 cooldown 동안 재전환 금지.
  - override는 강도 조절만 수행하며 하드 게이트를 대체하지 않는다.
- v3.3(hazard-aware override, Hypothesis):
  - v3.2 규칙을 유지한다.
  - 단, `transition_hazard_10d`가 임계치 미만이면 override를 완화/무시하고 lock bias를 유지한다.
  - hazard 결측 시 fail-open으로 v3.2 경로를 유지한다.
- v3.4(group transition gate):
  - v3.3 규칙을 유지한다.
  - `group_transition_signal`을 tactical 그룹 강도/우선순위 조절 입력으로 사용한다.
  - `WEAK` 그룹은 tactical 그룹 후보에서 우선 축소한다.
  - group 전이 결측 시 fail-open으로 v3.3 경로를 유지한다.
- v3.4.1(recovery-aware re-entry gate):
  - v3.4 규칙을 유지한다.
  - 축소 진입은 `WEAK` 그룹 수가 2개 이상일 때만 발동한다.
  - 축소 해제(재진입)는 아래 중 하나를 만족할 때만 허용한다.
    - `short_signal=RELIEF` 2거래일 연속
    - `mid_regime=RISK_ON`
  - 재진입 전까지 축소 상태를 유지한다(soft gate 상태 유지).
  - group 전이 결측 시 fail-open으로 v3.3 경로를 유지한다.
- v3.4.2-phase(phase-aware bias state machine):
  - v3.4.1 규칙을 유지한다.
  - 실행 기준 bias는 `next_step_bias_20d` 단일 경로를 사용한다.
  - `next_step` 생성 단계에서 phase-aware 상태머신(weekly/hysteresis/cooldown)으로 계산된 bias를 그대로 소비한다.
  - `RECOVERY` baseline은 `RISK_ON_BIAS`를 사용한다(회복기 참여 강화).
  - 상태 메타(`bias_state_source/switch/reason/cooldown`)는 설명용이며 하드게이트를 대체하지 않는다.
- v3.4.2a(체류 완화 실험):
  - v3.4.2-phase 규칙을 유지한다.
  - 아래 조건에서 `next_step_bias_effective`를 soft-only로 완화할 수 있다.
    - `cooldown_compressed_flag=true` + `bias_state_source=HOLD_COOLDOWN` -> `bias_candidate_20d` 적용
    - `hard_gate_exit_assist_flag=true` + `next_step_bias_20d=RISK_OFF_BIAS` -> `NEUTRAL_BIAS` 1단 완화
  - 위 완화는 하드게이트보다 후순위이며, 실행 금지 규칙을 대체하지 않는다.

## 5. Outputs
### 책임
- 실행 가능한 action plan 형식을 정의한다.

### 제외 범위
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

### 제외 범위
- 멀티 포트폴리오 동시 관리

- Grain: `(trade_date)`
- Key: `(trade_date)`

## 7. Invariants
### 책임
- mode 공존 시에도 핵심 제약을 강제한다.

### 제외 범위
- 투자 성과 보장

- `next_invested_ratio`는 `[0.0, 1.0]` 범위를 벗어나지 않는다.
- `abs(delta_ratio) <= adjustment_limit`
- `run_universe=false`이면 `action=INCREASE` 금지
- `risk_gate` 처리:
  - v0: `risk_gate=false`이면 `action != INCREASE`
  - v1/v2: `risk_gate=false`여도 `INCREASE` 허용
  - v3: v1/v2와 동일 (`risk_gate=false`여도 INCREASE 허용), 단 `run_universe=false`면 INCREASE 금지
  - v3.1/v3.2: v3와 동일한 하드 게이트 규칙 유지
- 하드 게이트(`run_universe`, `risk_gate`)가 soft gate(next_step bias)보다 우선한다.
- 즉시 올인/올아웃 금지(단일 주기에서 극단 이동 금지)
- `step_size > 0`이면 `delta_ratio`는 `step_size` 단위로 양자화된다(rounding_policy 적용)
- Allocation은 Composer 출력만 의존하며, Policy Config를 직접 참조하지 않는다.

## 8. DoD
### 책임
- 계약 기반 검증 기준을 제공한다.

### 제외 범위
- 백테스트 성능 검증

- **AE1**: 입력/출력 필수 컬럼 및 타입 검증
- **AE2**: `adjustment_limit` 제약(`abs(delta_ratio) <= adjustment_limit`) 검증
- **AE-v0**: `risk_gate=false` 시 `INCREASE` 차단 검증
- **AE-v1**: `risk_gate=false` 시 `INCREASE` 허용 검증
- **AE-v2**: `risk_gate=false` 시 `INCREASE` 허용 + `run_universe=false` 시 `INCREASE` 차단 검증
- **AE-v3**: `next_step_bias_20d` 반영 강도 조절 + snapshot 입력 소비 검증
- **AE-v3.1**: monthly lock(동일 월 bias 유지, 월 변경 시 갱신) 검증
- **AE-v3.2**: shock override + cooldown + 하드 게이트 우선 검증
- **AE-v3.3-hypothesis**: hazard 조건부 override 적용/완화 + 결측 fail-open 검증
- **AE-v3.4**: group transition soft gate 적용 + 결측 시 v3.3 동일성 검증
- **AE-v3.4.1**: WEAK>=2 진입 + RELIEF streak/MID RISK_ON 재진입 + 하드 게이트 우선 검증
- **AE-v3.4.2-phase**: `RECOVERY -> RISK_ON_BIAS` baseline + weekly cadence + cooldown 메타 전달 검증
- **AE-v3.4.2a**: cooldown compression/exit assist soft 적용 + 하드 게이트 우선성 회귀 검증

---

## 변경 이력
| 날짜 | 요약 | 참조 |
| --- | --- | --- |
| 2026-02-26 | v3.4.1 규칙 추가: WEAK>=2 진입, RELIEF 2연속/MID RISK_ON 재진입(soft gate 상태 유지) | docs/changelog.md |
| 2026-02-26 | v3.4(group transition gate) 규칙 추가: tactical 그룹 강도/우선순위 조절, 결측 fail-open(v3.3 유지) | docs/changelog.md |
| 2026-02-27 | v3.4.2-phase 규칙 추가: RECOVERY baseline 상향 + phase-aware bias state machine 메타 연동 | docs/changelog.md |
| 2026-02-27 | v3.4.2a 실험 규칙 추가: 체류 완화(cooldown compression, hard-gate exit assist) | docs/changelog.md |
| 2026-02-25 | v3.3(Hypothesis) hazard-aware override 규칙 추가 (`transition_hazard_10d` 게이트) | docs/changelog.md |
| 2026-02-25 | v3.1 monthly lock 정식화 + v3.2(Hypothesis) shock override/cooldown 규칙 추가 | docs/changelog.md |
| 2026-02-25 | v3 예약 포트 확정: `f(long_phase, mid_regime, next_step_bias_20d)` + snapshot 소비 원칙 명시 | docs/changelog.md |
| 2026-02-23 | v0/v1/v2 공존 계약으로 확장: mode별 risk_gate 규칙과 DoD 분리 명시 | docs/changelog.md |
| 2026-02-13 | 파일명 버전 제거 및 문서 표준 블록(문서 상태/기능 매트릭스) 적용 | docs/changelog.md |
