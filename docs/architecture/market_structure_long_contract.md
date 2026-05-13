# Market Structure Long-Term Phase — Contract (SOT)

> 🔄 **Observability Track 자료 — "시장 구조 관측" 컨텍스트로 재해석**
>
> 본 문서는 2026Q2 방향 재정의 후 Observability Track의 시장 관측 자료로 재해석됩니다.
> "투자 의사결정"이 아닌 **"Long-cycle regime 관측"** 컨텍스트로 활용됩니다.
> 코드 모듈은 Phase 1 P19에서 `observability/regime/horizon/long_engine.py`로 이전 완료되었습니다.
> 기존 `strategy_engine/axis_horizon_state/long_engine.py` import path는 shim으로 backward compat을 유지합니다.
> 참조: [`track_separation.md`](./track_separation.md), [`REFACTOR_2026Q2.md`](../../.agent/REFACTOR_2026Q2.md)

## Document Status
| Item | Value |
| --- | --- |
| Status | **Active (Observability 자료, 시장 관측 컨텍스트)** |
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
- [3. Inputs (Gold Macro 중심)](#3-inputs-gold-macro-중심)
- [4. Outputs](#4-outputs)
- [5. Grain/Key (trade_date 기준)](#5-grainkey-trade_date-기준)
- [6. Invariants](#6-invariants)
- [7. DoD (테스트 계약)](#7-dod-테스트-계약)

참조:
- `docs/architecture/gold_design_contract.md`
- `docs/architecture/calendar_design_contract.md`
- `docs/architecture/eod_observability_contract.md`
- `docs/architecture/market_structure_composer_contract.md`

## 1. 문서 목적
### 책임
- 장기 국면 모듈(`ms_long_term_phase`)의 입력/출력 계약을 고정한다.
- Composer가 소비하는 표준 long-term 상태 인터페이스를 정의한다.

### Non-goals
- long_phase 판정식의 수치화(가중치/컷오프) 정의

## 2. Scope & Non-Goals
### Scope
- Gold Macro 중심 입력을 사용해 장기 phase를 산출한다.
- 결측 입력 처리 규칙(`UNKNOWN`)을 명시한다.

### Non-goals
- Universe/Allocation 직접 제어
- 단기 신호 생성

## 3. Inputs (Gold Macro 중심)
### 책임
- Gold Macro 기반 장기 판단 입력 컬럼을 고정한다.

### Non-goals
- Macro 원천 보정/리샘플링

Source:
- `data/gold/macro/macro_features/*`

필수 입력 컬럼:

| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| trade_date | DATE | Y | 기준일 |
| indicator_id | TEXT | N | 지표 식별자. v1 rolling z-score의 groupby 키(권장); 누락 시 fail-open 경로 사용. |
| selected_value | FLOAT | N | 선택 값 |
| delta_3m | FLOAT | N | 중기 변화 |
| delta_6m | FLOAT | N | 장기 변화. v1에서 지표별 rolling z-score로 정규화됨. |
| regime | TEXT | N | tightening/easing/neutral |
| selected_release_date | DATE | N | PIT 검증용 release date |

결측 처리:
- 장기 판단에 필요한 핵심 입력이 누락되면 `long_phase=UNKNOWN`으로 출력한다.

## 4. Outputs
### 책임
- Composer가 소비하는 long-term 상태 필드를 고정한다.

### Non-goals
- confidence 수치 기준 정의

출력 컬럼:

| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| trade_date | DATE | Y | 기준일 |
| long_phase | TEXT | Y | `EXPANSION`, `LATE_CYCLE`, `SLOWDOWN`, `RECESSION`, `RECOVERY`, `UNKNOWN` |
| long_phase_confidence | FLOAT | N | 신뢰도 형식 필드(선택) |
| source_run_id | TEXT | N | lineage |

## 5. Grain/Key (trade_date 기준)
### 책임
- 장기 모듈 출력 grain을 고정한다.

### Non-goals
- 다중 버전 출력 관리 규칙

- Grain: `trade_date`
- Key: `(trade_date)`

## 6. Invariants
### 책임
- 출력 무결성 규칙을 명시한다.

### Non-goals
- 성능 KPI 보장

- `long_phase`는 ENUM 외 값 금지
- 입력을 수정하지 않고 read-only 소비
- 결측 입력 시 `long_phase=UNKNOWN` 허용, NULL 금지

**v1 분류 로직 (long_engine.py v1)**:
- `delta_6m_z`: 지표별 rolling z-score (window=252, min_periods=60)
  - NaN 시 raw delta_6m 부호(sign) fallback: positive→+1.0, negative→-1.0
  - (indicator_id, trade_date) 중복: keep="last" 적용 후 z-score 계산
- `z_threshold = 0.3` (기본값): `delta_6m_z < -0.3` 일 때만 SLOWDOWN/RECESSION 분류
  - 경계값(|z| < 0.3)은 LATE_CYCLE 또는 RECOVERY로 유지 (과민 반응 방지)
- `indicator_id` 컬럼 누락 시: regime 단독 판정 (fail-open, z-score 미사용)

## 7. DoD (테스트 계약)
### 책임
- 구현 검증 기준을 고정한다.

### Non-goals
- 테스트 프레임워크 강제

- **ML1**: 필수 입력/출력 컬럼 검증
- **ML2**: `long_phase` ENUM 외 값 금지
- **ML3**: 입력 결측 시 `UNKNOWN` 출력 검증
- **V1Normalization**: 단위 불변성, NaN fallback 경로, 중복 처리, threshold 파라미터 경계값 검증 (4건)

---

## Change History
| Date | Summary | References |
| --- | --- | --- |
| 2026-02-21 | Inputs 계약 정합화: indicator_id를 fail-open 정책에 맞춰 N(권장)으로 조정 | docs/changelog.md |
| 2026-02-20 | v1 rolling z-score 로직 반영 — z_threshold=0.3 채택, indicator_id 필수 명시, Invariants §6 상세화 | docs/changelog.md |
| 2026-02-13 | 파일명 버전 제거 및 문서 표준 블록(Document Status/Capability Matrix) 적용 | docs/changelog.md |
