# Market Structure Short-Term Signal — Contract (SOT)

## Document Status
| Item | Value |
| --- | --- |
| Status | Active |
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
- 단기 신호 모듈(`ms_short_term_signal`)의 입력/출력 계약을 정의한다.
- Risk Spread + 변동성 proxy 기반 단기 상태 인터페이스를 고정한다.

### Non-goals
- 단기 매매 타이밍 알고리즘 수치화

## 2. Scope & Non-Goals
### Scope
- 단기 스트레스/완화 상태를 `short_signal` ENUM으로 산출한다.
- Composer가 소비할 형식으로 표준화한다.

### Non-goals
- 중기/장기 레짐 산출
- Universe 직접 선별

## 3. Inputs
### 책임
- 단기 신호 입력 재료 스키마를 고정한다.

### Non-goals
- VIX 편입 수치/튜닝 정의

입력 컬럼:

| 입력 | 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| Risk Spread Proxy | trade_date | DATE | Y | 기준일 |
| Risk Spread Proxy | spy_ret_1d | FLOAT | N | SPY 수익률 |
| Risk Spread Proxy | tlt_ret_1d | FLOAT | N | TLT 수익률 |
| Risk Spread Proxy | iau_ret_1d | FLOAT | N | IAU 수익률 |
| Risk Spread Proxy | iwm_spy_relative_strength | FLOAT | N | IWM/SPY 상대강도 |
| Volatility Proxy | spy_realized_vol_20d | FLOAT | N | SPY 실현변동성(20d) |
| Volatility Proxy | iwm_spy_vol_spread | FLOAT | N | IWM/SPY 변동성 격차 |
| Volatility Proxy | spy_intraday_range | FLOAT | N | SPY intraday range |
| Flow Proxy | volume_zscore_20d | FLOAT | N | 거래량 이상치 |
| Flow Proxy | obv_slope | FLOAT | N | OBV 기울기 |
| Flow Proxy | turnover_spike_flag | BOOLEAN | N | turnover 스파이크 |
| Sentiment(VIX, optional) | vix_close | FLOAT | N | v1+ 편입 후보 |

결측 처리:
- Risk Spread/Volatility 핵심 입력 누락 시 `short_signal=UNKNOWN`으로 출력한다.
- VIX는 v0에서 필수 입력이 아니다(누락 허용).

## 4. Outputs
### 책임
- Composer 소비용 단기 상태를 정의한다.

### Non-goals
- 신호 강도 수치 기준 정의

출력 컬럼:

| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| trade_date | DATE | Y | 기준일 |
| short_signal | TEXT | Y | `PANIC`, `STABLE`, `RELIEF`, `UNKNOWN` |
| short_signal_confidence | FLOAT | N | 신뢰도 형식 필드 |
| source_run_id | TEXT | N | lineage |

## 5. Grain/Key
### 책임
- 단기 신호 출력 grain을 고정한다.

### Non-goals
- intraday 세분화

- Grain: `trade_date`
- Key: `(trade_date)`

## 6. Invariants
### 책임
- 단기 상태 출력 무결성을 보장한다.

### Non-goals
- 성과 보장

- `short_signal`은 ENUM 외 값 금지
- 입력 read-only
- 결측 입력은 `UNKNOWN`으로 표준화
- 점수/가중치 계산 없이 상태 전이 로직만 허용
- secondary PANIC 확인 신호는 4개(`vol_spike`, `wide_intraday`, `flight_to_safety`, `smallcap_stress`) 중 2개 이상 충족 규칙을 따른다.
- `smallcap_stress`는 `iwm_spy_vol_spread > 0.005` 조건으로 판정한다.

## 7. DoD
### 책임
- 단기 모듈 검증 기준을 제공한다.

### Non-goals
- 테스트 도구 강제

- **MSH1**: 필수 컬럼/타입 검증
- **MSH2**: `short_signal` ENUM 검증
- **MSH3**: 핵심 입력 결측 시 `UNKNOWN` 출력 검증
- **MSH4**: VIX 누락 시에도 v0 파이프라인이 동작함을 검증
- **MSH7**: `smallcap_stress` 임계값 경계(`>0.005`, `<=0.005`) 검증

---

## Change History
| Date | Summary | References |
| --- | --- | --- |
| 2026-02-22 | Short Engine 보강: secondary PANIC 4신호 체계 및 `smallcap_stress(iwm_spy_vol_spread > 0.005)` 기준 반영 | docs/changelog.md |
| 2026-02-13 | 파일명 버전 제거 및 문서 표준 블록(Document Status/Capability Matrix) 적용 | docs/changelog.md |
