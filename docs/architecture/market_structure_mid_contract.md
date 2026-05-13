# Market Structure Mid-Term Regime — Contract (SOT)

> 🔄 **Observability Track 자료 — "시장 구조 관측" 컨텍스트로 재해석**
>
> 본 문서는 2026Q2 방향 재정의 후 Observability Track의 시장 관측 자료로 재해석됩니다.
> "투자 의사결정"이 아닌 **"Mid-term regime (RISK_ON/OFF) 관측"** 컨텍스트로 활용됩니다.
> 코드 모듈은 Phase 1 P19에서 `observability/regime/horizon/mid_engine.py`로 이전 완료되었습니다.
> 기존 `strategy_engine/axis_horizon_state/mid_engine.py` import path는 shim으로 backward compat을 유지합니다.
> 참조: [`track_separation.md`](./track_separation.md), [`REFACTOR_2026Q2.md`](../../.agent/REFACTOR_2026Q2.md)

## Document Status
| Item | Value |
| --- | --- |
| Status | **Active (Observability 자료, 시장 관측 컨텍스트)** |
| Structure Policy | 구조는 고정, 기능은 확장 |
| Effective Date | 2026-02-22 |
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
- [5. Grain/Key](#5-grainkey)
- [6. Invariants](#6-invariants)
- [7. DoD](#7-dod)

참조:
- `docs/architecture/gold_design_contract.md`
- `docs/architecture/calendar_design_contract.md`
- `docs/architecture/eod_observability_contract.md`
- `docs/architecture/market_structure_composer_contract.md`

## 1. 문서 목적
### 책임
- 중기 레짐 모듈(`ms_mid_term_regime`)의 계약을 고정한다.
- Macro/EOD/Flow 입력을 통합하는 중기 상태 인터페이스를 정의한다.

### Non-goals
- 레짐 판정 수치/컷오프 정의

## 2. Scope & Non-Goals
### Scope
- Gold Macro + Gold EOD + (가능 시) breadth/flow proxy를 입력으로 사용한다.
- Composer에 전달할 `mid_regime` 상태를 산출한다.

### Non-goals
- 장기/단기 모듈 결과 직접 산출
- Universe 후보 생성

## 3. Inputs
### 책임
- 중기 레짐 판단 입력 스키마를 정의한다.

### Non-goals
- Flow/Breadth 원천 테이블 구조 확정

필수 입력:

| 입력 | 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| Gold Macro | trade_date | DATE | Y | 기준일 |
| Gold Macro | indicator_id | TEXT | Y | 지표 |
| Gold Macro | delta_3m | FLOAT | N | 중기 변화 |
| Gold Macro | regime | TEXT | N | 정책 상태 |
| Gold EOD | symbol | TEXT | Y | 심볼 |
| Gold EOD | trade_date | DATE | Y | 기준일 |
| Gold EOD | ret_20d | FLOAT | N | 추세 proxy |
| Gold EOD | vol_20d | FLOAT | N | 변동성 proxy |
| Flow/Breadth (선택) | breadth_iwm_spy_spread | FLOAT | N | breadth proxy (`iwm_ret_20d - spy_ret_20d`) |
| Flow/Breadth (선택) | volume_zscore_20d | FLOAT | N | flow proxy |

결측 처리:
- 핵심 입력 부족 시 `mid_regime=UNKNOWN`으로 출력한다.

## 4. Outputs
### 책임
- Composer 소비용 중기 레짐 출력을 고정한다.

### Non-goals
- confidence 임계값 수치 정의

출력 컬럼:

| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| trade_date | DATE | Y | 기준일 |
| mid_regime | TEXT | Y | `RISK_ON`, `NEUTRAL`, `RISK_OFF`, `UNKNOWN` |
| mid_regime_confidence | FLOAT | N | 신뢰도 형식 필드 |
| source_run_id | TEXT | N | lineage |

## 5. Grain/Key
### 책임
- 중기 모듈 출력 유일성 기준을 정의한다.

### Non-goals
- 멀티리전/멀티유니버스 분리

- Grain: `trade_date`
- Key: `(trade_date)`

## 6. Invariants
### 책임
- 출력 상태 일관성을 강제한다.

### Non-goals
- 모델 성능 보장

- `mid_regime`는 ENUM 외 값 금지
- 입력은 read-only
- 결측 입력일 경우 `mid_regime=UNKNOWN` 허용

## 7. DoD
### 책임
- 계약 기반 검증 기준을 제공한다.

### Non-goals
- 테스트 실행 환경 제한

- **MM1**: 입력/출력 컬럼 계약 검증
- **MM2**: `mid_regime` ENUM 검증
- **MM3**: 결측 입력 시 `UNKNOWN` 출력 검증
- **MM5**: `SPY ret_20d < 0` 구간에서 spread 방식이 부호 반전 오판정을 방지함을 검증

---

## Change History
| Date | Summary | References |
| --- | --- | --- |
| 2026-02-22 | Mid Engine v1.1 반영: breadth 계산을 ratio에서 spread(`iwm_ret_20d - spy_ret_20d`)로 변경 | docs/changelog.md |
| 2026-02-13 | 파일명 버전 제거 및 문서 표준 블록(Document Status/Capability Matrix) 적용 | docs/changelog.md |
