# Policy Config — Contract (SOT)

Markers: architecture, contract, legacy
Status: legacy

> 🔒 **Legacy Execution Reference — 자동매매·자산배분 정책 영역**
>
> 본 문서는 과거 실행 실험 계약을 보존하기 위한 reference입니다.
> Allocation v0/v1/v2 정책은 운영 중단(2026-05-12~) 상태이며, 현재 market data platform의 공개 운영 표면이 아닙니다.
> 참조: [`track_separation.md`](./track_separation.md)

## 문서 상태
| Item | Value |
| --- | --- |
| Status | **Frozen (legacy execution 운영 중단, 2026-05-12~)** |
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
- [3. Policy Profile 스키마](#3-policy-profile-스키마)
- [4. v0 기본 정책](#4-v0-기본-정책)
- [5. Resolve 규칙](#5-resolve-규칙)
- [6. Invariants](#6-invariants)
- [7. DoD](#7-dod)

참조:
- `docs/architecture/strategy_architecture.md`
- `docs/architecture/market_structure_composer_contract.md`
- `docs/architecture/allocation_engine_contract.md`

## 1. 문서 목적
### 책임
- Composer가 Allocation에 전달하는 정책 파라미터의 SOT(Source of Truth)를 정의한다.
- `policy_profile_id` 기반의 정적 정책 파라미터 계약을 고정한다.
- Composer ↔ Allocation 간 `target_invested_lower/upper`, `adjustment_limit` 등의 연결 경로를 명시한다.

### 제외 범위
- 정책 파라미터 수치 최적화/튜닝
- 동적 정책 변경 로직 (v1+ 범위)

## 2. 범위와 제외 범위
### Scope
- Policy Profile의 스키마 및 필수 필드 정의
- v0에서 사용하는 단일 기본 정책 정의
- Composer가 정책을 resolve하여 출력에 포함하는 규칙 정의

### 제외 범위
- 복수 정책 간 전환 로직 (v1+)
- 정책 파라미터의 백테스트 기반 최적화
- 운영 환경에서의 정책 주입/오버라이드 상세

## 3. Policy Profile 스키마

| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| policy_profile_id | TEXT | Y | 정책 식별자 (unique key) |
| target_invested_lower | FLOAT | Y | 목표 투자 비율 하한 |
| target_invested_upper | FLOAT | Y | 목표 투자 비율 상한 |
| adjustment_limit | FLOAT | Y | 주기당 최대 조정폭 |
| step_size | FLOAT | Y | 조정 단위 (양자화 간격) |
| rounding_policy | TEXT | Y | 반올림 정책 (`ROUND_DOWN`, `ROUND_NEAREST`) |
| policy_version | TEXT | Y | 정책 버전 |

## 4. v0 기본 정책

v0에서는 단일 정책만 사용한다.

```yaml
policy_profile_id: RC_V0_DEFAULT
target_invested_lower: <TBD>
target_invested_upper: <TBD>
adjustment_limit: <TBD>
step_size: <TBD>
rounding_policy: ROUND_DOWN
policy_version: v0
```

> 수치 값은 운영 설정에서 주입하며, 본 계약에서는 스키마와 규칙만 고정한다.

## 5. Resolve 규칙
- Composer는 `policy_profile_id`를 기반으로 Policy Config에서 정책 파라미터를 resolve한다.
- resolve된 필드(`target_invested_lower/upper`, `adjustment_limit`, `step_size`)는 Composer 출력에 포함된다.
- Allocation은 Composer 출력에 포함된 resolved 값을 사용한다.
- Policy Config가 SOT이며, Composer 출력의 resolved 값은 Config에서 파생된 사본이다.

resolve 흐름:
```
Policy Config (SOT) → Composer (resolve + 출력에 포함) → Allocation (소비)
```

## 6. Invariants
### 책임
- Policy Config의 무결성 제약을 강제한다.

### 제외 범위
- 수치 범위 유효성 상세 검증 (구현 시 결정)

- `policy_profile_id`는 unique key이며 중복 금지
- `target_invested_lower <= target_invested_upper`
- `adjustment_limit > 0`
- `step_size > 0`
- v0에서 `policy_profile_id`는 `RC_V0_DEFAULT` 하나만 허용
- resolve 실패(미등록 profile_id) 시 파이프라인 실행 중단 (fail-fast)

## 7. DoD
### 책임
- 계약 기반 검증 기준을 제공한다.

### 제외 범위
- 테스트 프레임워크 강제

- **PC1**: Policy Profile 필수 컬럼/타입 검증
- **PC2**: `policy_profile_id` unique key 검증
- **PC3**: `target_invested_lower <= target_invested_upper` invariant 검증
- **PC4**: v0에서 미등록 profile_id resolve 시 실패 검증

---

## 변경 이력
| 날짜 | 요약 | 참조 |
| --- | --- | --- |
| 2026-02-13 | 파일명 버전 제거 및 문서 표준 블록(문서 상태/기능 매트릭스) 적용 | docs/changelog.md |
