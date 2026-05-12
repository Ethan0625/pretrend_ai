# ADR-004: ETF 기반 실행 Universe (개별 종목 대신)

> ⚠️ **Mixed** — ETF SOT(32종)는 공유, picking 로직은 Personal Track. 분류: [`README.md`](README.md)

## Status
Accepted

## Date
2026-01-10 (초기 설계), 2026-02-22 (Universe v1 확정)

---

## Context

전략 신호를 실제 포트폴리오 매매로 연결하기 위해 어떤 자산을 매매 대상으로 삼을지 결정해야 했다.

주요 선택지는 두 가지였다.

1. **개별 종목 (Individual Stocks)**: 기업 분석 + 성장성 필터 기반 선정
2. **ETF (Exchange Traded Fund)**: 섹터/자산군/지역별 ETF 활용

이 시스템의 전략 신호는 거시 경제 Regime과 시장 구조 상태에 기반한다.

---

## Decision

**실행 Universe를 36개 ETF로 구성한다 (SECTOR 14, BOND 5, COMMODITY 7, COUNTRY 5, INDEX 5개 등).**

Core(항상 보유): SPY, SCHD, IAU
Tactical(신호 기반 선택): SECTOR / BOND / COMMODITY / COUNTRY 그룹에서 Relative Strength 상위 선정

개별 종목은 현재 실행 Universe 범위 밖이며, 향후 Research Universe(U0~U3) 파이프라인으로 별도 관리 예정.

---

## Rationale

**1. 거시 신호와 자산군의 직접 매핑**
이 시스템의 Long Engine은 거시 경제 Regime을 판단한다.
RECESSION → BOND 비중 확대, RISK_ON → SECTOR/COUNTRY 편입 같은 규칙이
ETF 단위에서 자연스럽게 구현된다.
개별 종목 선택은 기업 펀더멘털 분석이 추가로 필요하며, 거시 신호와 연결이 복잡하다.

**2. 개별 종목 리스크 제거**
ETF는 내부적으로 분산된 포트폴리오다.
단일 기업의 실적 쇼크, 회계 이슈, 유동성 위기가 포트폴리오에 직격하지 않는다.
거시 전략에서 개별 종목 이벤트 리스크는 불필요한 변수다.

**3. 데이터 품질과 일관성**
ETF는 가격 데이터가 안정적이고 장기 히스토리가 확보된다.
개별 종목은 상장폐지, 분할, 합병, 티커 변경 등으로 장기 시계열 처리가 복잡하다.
2006~2026 장기 Backtest를 위해 데이터 일관성이 필수였다.

**4. 유동성과 거래 비용**
SPY, QQQ, TLT 등 대형 ETF는 유동성이 매우 높아
소규모 포트폴리오에서도 슬리피지 없이 매매 가능하다.
시장가 주문으로 충분하며 알고리즘적 집행이 필요 없다.

**5. 운영 단순성**
36개 ETF는 Observability Set으로 고정 관리된다.
개별 종목은 Universe 변경 시 데이터 수집 대상도 동적으로 변해 운영 복잡성이 높다.

---

## Alternatives Considered

| 대안 | 거부 이유 |
|---|---|
| S&P 500 전 종목 | 데이터 수집·처리 부담, 개별 종목 이벤트 리스크 |
| 성장주 필터링 (U0~U3) | 기업 펀더멘털 분석 인프라 추가 필요 — 별도 로드맵(M2)으로 분리 |
| 글로벌 지수 선물 | 증권사 API 복잡성, 국내 소액 투자자 접근성 낮음 |

---

## Consequences

**수용한 트레이드오프**
- 개별 종목 Alpha 불가. ETF 내부 비효율(저성과 종목 포함)을 피할 수 없음.
- 특정 테마(반도체, AI 등) 집중 투자 어려움.

**얻은 것**
- 개별 종목 이벤트 리스크 없음
- 장기 Backtest 데이터 일관성 확보
- 거시 신호 → 자산군 전환의 직접 매핑
- 운영 Universe가 고정되어 데이터 파이프라인 안정적

**향후 확장**
개별 종목 Research Universe(U0~U3)는 M2 마일스톤으로 분리 예정.
ETF 실행 Universe와 종목 Research Universe는 독립 파이프라인으로 병존한다.
