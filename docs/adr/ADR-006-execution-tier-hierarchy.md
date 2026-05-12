# ADR-006: 실행 계층 분리 (Backtest → Paper SIM → Broker Mock → Live)

> 🔒 **Personal Track Frozen** — 매매 실행 계층 결정. Personal Track 운영 중단(2026-05-12~). 분류: [`README.md`](README.md)

## Status
Accepted

## Date
2026-02-21 (Backtest 완성), 2026-03-09 (SIM/Mock 분리 확정)

---

## Context

전략 신호를 실제 매매로 연결하는 과정에서 검증 없이 바로 실 계좌에 연결하는 것은
운영 리스크가 너무 크다. 동시에 Backtest만으로는 실제 실행 환경의 문제를
사전에 발견하기 어렵다.

아래 문제들을 단계적으로 검증할 구조가 필요했다.

1. 전략 로직 자체의 유효성 (수익성, 리스크 통제)
2. 실시간 신호 생성의 정확성 (PIT 오염, 스냅샷 정합성)
3. 주문 API 연동의 신뢰성 (체결 수량, 취소 오경보)
4. 실 계좌 운영의 안정성 (자금 관리, 포지션 정합)

---

## Decision

**4단계 실행 계층을 분리하여 각 단계가 다음 단계의 전제 조건이 되도록 설계한다.**

```
[Backtest Engine]
    ↓ 전략 로직 검증 (2006~현재, DCA, Walk-Forward)
[Paper SIM (paper_trading_dag)]
    ↓ 실시간 신호 검증 (가상 자본, 실 시장 데이터)
[Broker Mock (broker_mock_trading_dag)]
    ↓ 실 API 연동 검증 (KIS Mock API, 가상 체결)
[Broker Live] ← 현재 Out-of-scope
```

각 계층은 독립 실행되며, 상위 계층의 결과가 하위 계층 설계의 입력이 된다.
SIM과 Mock은 동일 전략 신호를 공유하지만 NAV와 체결 기록은 독립 유지한다.

---

## Rationale

**1. 단계적 리스크 격리**
Backtest에서 발견하지 못한 버그(예: 스냅샷 비결정성, PIT 오염)는
Paper SIM 운영에서 실 시장 데이터로 노출된다.
SIM에서 발견하지 못한 API 연동 문제(예: 체결 수량 오류, 취소 오경보)는
Broker Mock에서 실 API로 노출된다.
단계가 없으면 실 계좌에서 처음 발견하게 된다.

**2. SIM과 Mock의 역할 분리**
Paper SIM: 전략 신호의 실시간 정확성 검증. 가상 자본으로 포트폴리오 시뮬레이션.
Broker Mock: KIS API 연동, 주문 생성/체결/취소 흐름 검증. 실 계좌 구조 반영.
두 계층이 동일 DAG에 있으면 하나의 실패가 다른 검증을 방해한다.
분리함으로써 각자 독립적으로 실패하고 디버깅할 수 있다.

**3. Backtest와 실운영의 정합 유지**
Backtest Engine은 실운영(SIM/Mock)과 동일한 전략 신호를 소비한다.
이를 통해 Backtest 결과와 실운영 결과를 직접 비교할 수 있다.
전략 로직이 Backtest에서만 작동하고 실운영에서 다르게 작동하면
Backtest의 검증 가치가 없다.

**4. 각 계층의 독립 진화 가능**
Backtest에 새 preset 추가해도 SIM/Mock에 영향 없다.
Mock API 연동 방식 변경해도 SIM 로직에 영향 없다.
레이어 간 인터페이스는 전략 스냅샷(Parquet)으로 고정되어 있어
각 계층이 독립적으로 버전업 가능하다.

**5. 실 계좌 진입 기준 명확화**
Live 계층 진입은 각 하위 계층의 안정 운영 기간과 DoD 충족이 전제 조건이다.
이 구조가 없으면 "언제 Live로 가도 되는가"의 기준이 주관적이 된다.

---

## Alternatives Considered

| 대안 | 거부 이유 |
|---|---|
| Backtest → 바로 Live | API 연동 문제, 실시간 신호 오류를 실 계좌에서 처음 발견 |
| Backtest + SIM 단 2단계 | API 연동 검증 불가 — Mock 없이 Live 진입 시 체결 오류 리스크 |
| SIM과 Mock 통합 | 역할 혼재로 실패 원인 특정 어려움, 독립 디버깅 불가 |

---

## Consequences

**수용한 트레이드오프**
- DAG 3개 병렬 운영 (macro, eod, strategy + paper + broker_mock)으로 운영 부담 증가
- SIM/Mock 각 NAV 독립 관리로 비교 분석이 필요할 때 추가 작업 필요

**얻은 것**
- 각 계층별 독립 실패 격리 및 디버깅
- Backtest ↔ SIM ↔ Mock 결과 비교로 전략 드리프트 조기 감지
- Live 진입 기준의 객관적 정의 가능
- 각 계층이 독립적으로 진화 가능 (인터페이스는 Parquet 스냅샷으로 고정)

**현재 상태**
- Backtest v0/v1/v2: 완성 (2006~2024 검증, Walk-Forward 완료)
- Paper SIM: 운영 중 (Airflow 자동 스케줄)
- Broker Mock: 운영 중 (ET 09:40 자동 스케줄, KIS Mock API 연동)
- Live: Out-of-scope (별도 승인 전까지)
