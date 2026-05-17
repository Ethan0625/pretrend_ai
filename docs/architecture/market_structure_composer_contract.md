# Market Structure Composer — Contract (SOT)

Markers: architecture, contract
Status: active

> 🟢 **Market Data Platform 관측 계약**
>
> 본 문서는 Gold feature layer를 소비해 **12-slot AHS (Axis × Horizon State) 관측 매트릭스**를 구성하는 계약입니다.
> 투자 의사결정이나 매매 지시가 아니라 read-only observation context로 활용됩니다.
> `axis_horizon_state/builder.py`는 Phase 1 P19에서 `observability/regime/horizon/builder.py`로 이전 완료되었습니다.
> 기존 `strategy_engine/axis_horizon_state/` import path는 shim으로 backward compat을 유지합니다.
> `market_position/`은 Phase 1 P20에서 `observability/regime/position/`으로 이전 완료되었습니다.
> 기존 `strategy_engine/market_position/` import path는 shim으로 backward compat을 유지합니다.
> 참조: [`track_separation.md`](./track_separation.md)

## 문서 상태
| Item | Value |
| --- | --- |
| Status | **Active (Observability 자료, 시장 관측 컨텍스트)** |
| Structure Policy | 구조는 고정, 기능은 확장 |
| Effective Date | 2026-02-13 |
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
- [4. Outputs (필수)](#4-outputs-필수)
- [5. Grain/Key](#5-grainkey)
- [6. Invariants (핵심)](#6-invariants-핵심)
- [7. DoD](#7-dod)

참조:
- `docs/architecture/market_structure_long_contract.md`
- `docs/architecture/market_structure_mid_contract.md`
- `docs/architecture/market_structure_short_contract.md`
- `docs/architecture/universe_contract.md`
- `docs/architecture/allocation_engine_contract.md`
- `docs/architecture/policy_config_contract.md`
- `docs/architecture/gold_design_contract.md`
- `docs/architecture/calendar_design_contract.md`
- `docs/architecture/eod_observability_contract.md`

## 1. 문서 목적
### 책임
- long/mid/short 출력 3개를 합성해 Universe/Allocation이 소비할 단일 상태 벡터를 생성한다.
- 해석 원칙: long/mid/short는 근거 데이터 축이 아니라 4축(정책/매크로, 가격/변동성, 수급/구조, 심리)을 서로 다른 관측 시점(horizon)으로 해석한 결과를 표준화한 출력이다.
- 하위 모듈 분리를 유지하면서 상위 소비 인터페이스를 표준화한다.

### 제외 범위
- 합성 점수식/가중치/컷오프 수치 정의

## 2. 범위와 제외 범위
### Scope
- 입력: long/mid/short 계약 출력
- 출력: `run_universe`, `risk_gate`를 포함한 Composer 상태 벡터

### 제외 범위
- 장/중/단기 상태 자체 재계산
- Universe 후보 계산
- Allocation 실행 로직 계산

## 3. Inputs
### 책임
- 3개 모듈 출력 스키마 결합 기준을 정의한다.

### 제외 범위
- 모듈별 계산식 튜닝

입력 컬럼:

| 모듈 | 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| Long | trade_date | DATE | Y | 기준일 |
| Long | long_phase | TEXT | Y | 장기 phase |
| Mid | trade_date | DATE | Y | 기준일 |
| Mid | mid_regime | TEXT | Y | 중기 regime |
| Short | trade_date | DATE | Y | 기준일 |
| Short | short_signal | TEXT | Y | 단기 signal |
| Policy Config | policy_profile_id | TEXT | Y | 적용 정책 식별자 |

Policy Config 입력:
- Composer는 `policy_profile_id`를 기반으로 Policy Config(`docs/architecture/policy_config_contract.md`)에서 정책 파라미터를 resolve한다.
- v0에서는 `RC_V0_DEFAULT` 단일 정책만 사용한다.

결측 처리:
- 특정 모듈 입력 누락 시 해당 상태를 `UNKNOWN`으로 채워 합성한다.
- Policy Config resolve 실패 시 파이프라인 실행을 중단한다(fail-fast).

## 4. Outputs (필수)
### 책임
- Universe/Allocation 공통 소비 스키마를 확정한다.

### 제외 범위
- `run_universe`, `risk_gate` 판정 수치화

출력 컬럼:

| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| trade_date | DATE | Y | 기준일 |
| long_phase | TEXT | Y | 장기 상태 |
| mid_regime | TEXT | Y | 중기 상태 |
| short_signal | TEXT | Y | 단기 상태 |
| run_universe | BOOLEAN | Y | Universe 실행 여부 |
| risk_gate | BOOLEAN | Y | Allocation 증가 허용 여부 |
| policy_profile_id | TEXT | Y | 적용된 정책 식별자 |
| target_invested_lower | FLOAT | Y | Policy Config에서 resolve된 목표 하한 |
| target_invested_upper | FLOAT | Y | Policy Config에서 resolve된 목표 상한 |
| adjustment_limit | FLOAT | Y | Policy Config에서 resolve된 주기당 최대 조정폭 |
| step_size | FLOAT | Y | Policy Config에서 resolve된 조정 단위 |
| policy_version | TEXT | Y | 적용된 정책 버전 |
| notes | ARRAY<TEXT> | N | 합성 메모 |
| source_run_id | TEXT | N | lineage |

Policy 필드 설명:
- `target_invested_lower/upper`, `adjustment_limit`, `step_size`는 Policy Config에서 resolve된 값이다.
- SOT는 Policy Config(`docs/architecture/policy_config_contract.md`)이며, Composer 출력에 포함된 값은 Config에서 파생된 사본이다.
- Allocation은 이 필드들을 Composer 출력에서 직접 소비하여, Composer 출력만 의존하는 invariant를 유지한다.

개념 예시:

```yaml
trade_date: 2026-02-12
long_phase: SLOWDOWN
mid_regime: RISK_OFF
short_signal: PANIC
run_universe: false
risk_gate: false
policy_profile_id: RC_V0_DEFAULT
target_invested_lower: 0.30
target_invested_upper: 0.50
adjustment_limit: 0.10
step_size: 0.05
policy_version: v0
notes: ["mid_regime_risk_off", "short_signal_panic", "increase_blocked"]
```

## 5. Grain/Key
### 책임
- Composer 출력 유일성 기준을 정의한다.

### 제외 범위
- 다중 유니버스 버전 관리

- Grain: `trade_date`
- Key: `(trade_date)`

## 6. Invariants (핵심)
### 책임
- Composer-중심 의존 구조를 강제한다.

### 제외 범위
- 실행 비용 최적화 상세 규칙

- Universe/Allocation은 Composer 출력만 의존 (개별 모듈 직접 참조 금지)
- long/mid/short는 4축 근거를 관측 시점별로 해석한 결과여야 하며, Composer는 축 자체를 추가/대체하지 않는다.
- `run_universe=false`이면 Universe 실행 결과는 비어야 함 (연계 불변식)
- long/mid/short 입력 ENUM 외 값 금지
- `policy_profile_id`는 Policy Config에서 resolve 가능해야 함 (미등록 시 fail-fast)
- `target_invested_lower <= target_invested_upper` (Policy Config invariant 전파)

## 7. DoD
### 책임
- Composer 계약 검증 기준을 제공한다.

### 제외 범위
- 테스트 구현 프레임워크 제한

- **MSC1**: Composer 출력 스키마 검증 (policy resolved 필드 포함)
- **MSC2**: ENUM 위반 금지 검증
- **MSC3**: `run_universe=false` 시 Universe/Allocation 스킵 조건 명세/검증
- **MSC4**: `policy_profile_id` resolve 실패 시 fail-fast 검증

---

## 변경 이력
| 날짜 | 요약 | 참조 |
| --- | --- | --- |
| 2026-02-13 | 파일명 버전 제거 및 문서 표준 블록(문서 상태/기능 매트릭스) 적용 | docs/changelog.md |
