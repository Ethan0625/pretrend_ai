# Market Structure — 데이터 인벤토리

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
- [2. 인벤토리 범위](#2-인벤토리-범위)
- [3. 축별 데이터 현황](#3-축별-데이터-현황)
- [4. 상태값 표준(참고)](#4-상태값-표준참고)
- [5. 결측/미수집 처리 원칙](#5-결측미수집-처리-원칙)
- [6. v0/v1/v2/v3 데이터 로드맵 연결](#6-v0v1v2v3-데이터-로드맵-연결)
- [7. Non-Goals](#7-non-goals)

참조 계약 문서:
- `docs/architecture/market_structure_long_contract.md`
- `docs/architecture/market_structure_mid_contract.md`
- `docs/architecture/market_structure_short_contract.md`
- `docs/architecture/market_structure_composer_contract.md`
- `docs/architecture/gold_design_contract.md`
- `docs/architecture/eod_observability_contract.md`

## 1. 문서 목적
### 책임
- Market Structure 4개 축의 데이터 수집/가용 상태를 명시한다.
- 현재 구현 가능한 축과 미수집 축을 분리해 우선순위를 고정한다.

### Non-goals
- 상태 판정 수치 기준 정의
- 스코어링 가중치 정의

## 2. 인벤토리 범위
### 책임
- Layer에서 Market Structure로 전달되는 입력 데이터의 가용성 관리를 수행한다.

### Non-goals
- Universe-ETF/Allocation 엔진 출력 정의

## 3. 축별 데이터 현황

### 해석 원칙
- 4축(정책/매크로, 가격/변동성, 수급/구조, 심리)은 Market Structure 상태 판단의 근거 데이터 축이다.
- long/mid/short는 근거 축이 아니라, 동일한 4축을 관측 시점(horizon)별로 해석하는 모듈이다.
- Composer는 horizon별 해석 결과를 합성하며, 4축 정의 자체를 변경하지 않는다.

| 축 | 주요 재료 | 현재 수집 상태 | 데이터 소스/레이어 | 비고 |
| --- | --- | --- | --- | --- |
| 정책/매크로 | Gold Macro (`regime`, `delta_*`, `selected_release_date`) | 수집 완료 | Gold Macro v1 | 사용 가능 |
| 가격/변동성 | Gold EOD (`ret_*`, `vol_*`, outlier flag) | 수집 완료 | Gold EOD v1 | 사용 가능 |
| 수급/구조 | `volume_zscore_20d`, OBV 계열, breadth proxy(`IWM/SPY`) | 부분 수집 | Gold EOD 파생 + 확장 | v0~v1 |
| 심리(v0) | Risk Spread(`SPY/TLT/IAU`) + Volatility Proxy(`SPY vol`, `IWM/SPY vol`, `intraday_range`) | 부분 수집 | Gold EOD/Observability 파생 | VIX 없이 운용 가능 |
| 심리(v1+) | VIX sentiment 테이블 | 미수집 | 별도 sentiment 레이어(예정) | Term Structure 포함 여부 TBD |

## 4. 상태값 표준(참고)
### 책임
- 미수집 데이터가 있는 동안 상태 표현을 표준화한다.

### Non-goals
- 상태 판정 로직 수치화

| 모듈 | 상태 컬럼 | 기본 결측 값 |
| --- | --- | --- |
| Long | `long_phase` | `UNKNOWN` |
| Mid | `mid_regime` | `UNKNOWN` |
| Short | `short_signal` | `UNKNOWN` |
| Composer | `run_universe` | `false` (보수적 기본값 권장) |

## 5. 결측/미수집 처리 원칙
### 책임
- v0 운영 시 데이터 미수집 구간의 동작 원칙을 명시한다.

### Non-goals
- 결측 보간 알고리즘 정의

- 필수 입력 누락 시 해당 모듈 상태는 `UNKNOWN`
- Composer는 `UNKNOWN` 상태를 그대로 전달 가능
- 보수적 운영 원칙: 위험 신호 미확인 시 공격적 증가를 제한

## 6. v0/v1/v2/v3 데이터 로드맵 연결
### 책임
- 전략 버전별 데이터 요구사항을 연결한다.

### Non-goals
- 각 버전의 수치 정책

- **v0**: 정책/매크로 + 가격/변동성 + 심리 proxy(Risk Spread/Volatility) 기반 운용, 총 투자 비율 조절
- **v1**: VIX sentiment 입력 추가(직접 VIX vs term structure 범위 확정)
- **v2**: 레짐 기반 allocation 입력 고도화
- **v3**: Universe-ETF 그룹별 동적 가중치 지원을 위한 그룹별 상태 입력 확장

## 7. Non-Goals
- 점수/가중치/컷오프 수치 정의
- 모델링/예측 로직 정의
- Observability 계약 변경

---

## Change History
| Date | Summary | References |
| --- | --- | --- |
| 2026-02-13 | 파일명 버전 제거 및 문서 표준 블록(Document Status/Capability Matrix) 적용 | docs/changelog.md |
