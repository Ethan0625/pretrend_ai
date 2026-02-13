# 📄 Data Requirements Document

**Project:** Pre-Trend Value 기반 자동매매 AI 시스템  
**Document:** Data Requirements  
**Version:** 2026.02.12  
**Purpose:** Risk-Control 전략 아키텍처(v0) 기준의 데이터 요구사항 정의

---

## 1. Overview

본 문서는 현재 전략 구조
`Layer -> Market Structure(4축) -> Composer -> Universe -> Allocation Engine v0`
에서 필요한 데이터 입력을 정의한다.

본 문서의 범위는 **데이터 항목/스키마/운영 전제**이며,
점수화(가중치/컷오프/임계값) 설계는 포함하지 않는다.

참조 문서:
- `docs/strategy_architecture.md`
- `docs/architecture/market_structure_long_contract.md`
- `docs/architecture/market_structure_mid_contract.md`
- `docs/architecture/market_structure_short_contract.md`
- `docs/architecture/market_structure_composer_contract.md`
- `docs/architecture/universe_contract.md`
- `docs/architecture/allocation_engine_contract.md`
- `docs/architecture/eod_observability_contract.md`
- `docs/architecture/gold_design_contract.md`
- `docs/architecture/calendar_design_contract.md`

---

## 2. Data Requirement Scope

데이터 요구사항은 아래 5개 카테고리로 구성한다.

1. Macro 데이터 (정책/유동성 축)
2. EOD Observability 데이터 (가격/변동성, 수급/구조, 심리 proxy 공통 입력)
3. Market Structure 모듈 입력 (Long/Mid/Short)
4. Composer/Universe 입력
5. Allocation Engine v0 입력

Non-Goals:
- 종목 추천/전략 수익률 최적화용 feature 설계
- Market Structure 점수식 정의
- Universe 내부 종목 가중치 조정 규칙

---

## 3. Macro Data Requirements (정책/유동성)

### 3.1 사용 계층
- 원천: FRED Bronze/Silver + Calendar Silver
- 소비: Gold Macro Feature v1 (`docs/architecture/gold_design_contract.md`)
- 연계 조건: PIT-safe (`release_date < trade_date`)

### 3.2 필수 입력 항목

| 항목 | 설명 | 목적 | 출처 |
| --- | --- | --- | --- |
| CPI / Core CPI | 인플레이션 흐름 | 장기 phase/중기 regime 판단 재료 | FRED |
| Fed Funds Rate | 기준금리 | 정책 방향 판단 | FRED |
| 실업률 | 경기 모멘텀 | 경기 둔화/회복 상태 판단 | FRED |
| 10Y 금리(DGS10) | 금리 레벨/변화 | 정책-시장 연결 재료 | FRED |

### 3.3 필수 컬럼(소비 기준)

| 컬럼 | 타입 | 필수 | 비고 |
| --- | --- | --- | --- |
| indicator_id | TEXT | Y | 지표 식별자 |
| trade_date | DATE | Y | 소비 기준일 |
| selected_value | FLOAT | Y | 선택된 지표값 |
| selected_release_date | DATE | Y | PIT 검증 기준 |
| delta_1m / delta_3m / delta_6m | FLOAT | N | 지표별 증감 |
| regime | TEXT | N | `tightening/easing/neutral` |
| release_source | TEXT | Y | evidence 출처 |

---

## 4. EOD Data Requirements (Observability Set v1)

### 4.1 역할
- Observability Set v1은 Universe 결과와 무관하게 항상 수집되는 고정 관측 입력이다.
- 분류 라벨(`asset_group`, `asset_name`, `asset_subtype`)은 Bronze에서 1회 확정하고 Silver/Gold로 그대로 전파한다.

### 4.2 필수 시세 컬럼

| 컬럼 | 타입 | 필수 |
| --- | --- | --- |
| trade_date | DATE | Y |
| open | FLOAT | Y |
| high | FLOAT | Y |
| low | FLOAT | Y |
| close | FLOAT | Y |
| adj_close | FLOAT | Y |
| volume | BIGINT | Y |
| symbol | TEXT | Y |
| run_id | TEXT | Y |
| ingestion_ts | TIMESTAMP | Y |
| source | TEXT | Y |

### 4.3 필수 분류 컬럼 계약

| 컬럼 | 타입 | 필수 | 허용/설명 |
| --- | --- | --- | --- |
| asset_group | TEXT(ENUM) | Y | `INDEX`, `COUNTRY`, `COMMODITY`, `BOND`, `SECTOR` |
| asset_name | TEXT | Y | canonical 분류명 |
| asset_subtype | TEXT | N | 세부 분류 |

---

## 5. Market Structure 4축 입력 요구사항

### 5.1 정책/유동성 축
- 입력: Gold Macro Feature
- 핵심 필드: `indicator_id`, `selected_value`, `delta_*`, `regime`

### 5.2 가격/변동성 축
- 입력: Gold EOD Feature
- 핵심 필드: 수익률/변동성/drawdown 계열

### 5.3 수급/구조 축
- 입력: Gold EOD Feature 기반 flow/breadth proxy
- v0 최소 재료: `SPY`, `IWM`, `TLT`, `IAU` 기반 상대 강도/스프레드
- 확장 재료(추가 수집 시): OBV 계열, turnover spike

### 5.4 심리 축 (v0)
- 입력: 직접 VIX가 아닌 proxy 기반 상태 재료
- 예: risk spread 프레임, realized volatility, intraday range
- VIX 직접 수집/term structure는 v1+ 확장 항목

---

## 6. Composer / Universe / Allocation 입력 계약 관점

### 6.1 Composer 입력 요건
- Long/Mid/Short 모듈 출력이 동일 `trade_date` 기준으로 정렬 가능해야 한다.
- 입력 누락 시 `UNKNOWN` 상태를 허용해야 한다.

### 6.2 Universe 입력 요건
- Composer 출력(`run_universe`, `risk_gate` 포함)
- Gold EOD Feature + Observability 라벨
- 라벨은 read-only

### 6.3 Allocation 입력 요건(v0)

| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| trade_date | DATE | Y | 기준일 |
| target_invested_lower | FLOAT | Y | 목표 하한 |
| target_invested_upper | FLOAT | Y | 목표 상한 |
| current_invested_ratio | FLOAT | Y | 현재 투자 비율 |
| adjustment_limit | FLOAT | Y | 주기당 최대 조정폭 |
| risk_gate | BOOLEAN | Y | 증가 허용 여부 |
| run_universe | BOOLEAN | Y | Universe 실행 허용 여부 |

---

## 7. 운영 주기 요구사항

- Adjustment Cycle: 주 1회 (화요일)
- Portfolio Rebalance: 월 1회 (마지막 주 금요일, 휴장 시 직전 영업일)
- 원칙: Adjustment와 Rebalance는 분리 운영

---

## 8. 데이터 품질/불변식 요구사항

- PIT 불변식 준수: `selected_release_date < trade_date`
- Observability 라벨 read-only 전파
- Composer ENUM 외 값 금지
- `run_universe=false`이면 Universe 결과는 비어야 함
- `risk_gate=false`이면 Allocation 증가(INCREASE) 금지

---

## 9. Minimal Data Set for v0

v0 운영의 최소 필수 데이터:
1. Gold Macro Feature v1 (CPI/Core CPI/UNRATE/FEDFUNDS/DGS10)
2. Gold EOD Feature v1 (Observability 라벨 포함)
3. Risk Spread/Volatility proxy 계산용 관측 심볼(`SPY`, `IWM`, `TLT`, `IAU`)
4. Composer 출력(`run_universe`, `risk_gate`)
5. Allocation 입력 7개 컬럼

---

## 10. Data Source Summary

| 데이터 | 소스 | 비고 |
| --- | --- | --- |
| Macro 원천 | FRED | Calendar 연계 PIT 적용 |
| EOD 시세 | Yahoo Finance 등 | Observability Set 상시 수집 |
| Calendar release 증거 | FRED vintage/release API | Gold release_date 근거 |
| Sentiment(v0) | EOD proxy 기반 | VIX 직접 수집은 v1+ |
