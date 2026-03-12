# ADR-001: Medallion Data Architecture (Bronze / Silver / Gold)

## Status
Accepted

## Date
2026-01-01 (초기 설계), 2026-02-14 (문서화)

---

## Context

자동매매 전략 시스템은 외부 데이터(FRED, Yahoo Finance 등)를 수집하고,
정제하고, 피처를 계산하는 전 과정에서 아래 요구사항을 동시에 만족해야 했다.

- **재현성(Reproducibility)**: 과거 임의 시점의 전략 판단을 그대로 재현할 수 있어야 한다.
- **PIT(Point-in-Time) 정합성**: 전략 신호 계산 시 미래 데이터가 누출되면 안 된다. 특히 FRED 거시 지표는 발표 시점과 기준 시점이 다르다(vintages).
- **감사 가능성(Auditability)**: 특정 판단의 근거가 된 원본 데이터를 언제든 추적할 수 있어야 한다.
- **멱등성(Idempotency)**: 동일 입력에 대해 파이프라인을 재실행해도 항상 동일한 결과가 나와야 한다.
- **단계별 독립성**: 데이터 수집 오류가 피처 계산 단계에 영향을 주지 않아야 한다.

---

## Decision

**Bronze → Silver → Gold 3단계 Medallion Architecture를 채택한다.**

| 레이어 | 역할 | 불변 원칙 |
|---|---|---|
| **Bronze** | 외부 소스 원본 데이터 그대로 저장 | 정규화/변환 금지. Raw 보존 |
| **Silver** | 정규화, 결측치 처리, 이상치 필터링 | Bronze read-only consumer |
| **Gold** | 전략 계산용 파생 피처 (z-score, rolling, PIT-safe) | Silver read-only consumer |

파티션 구조: Hive-compatible (`source=`, `symbol=`, `year=`) → 날짜 기반 incremental 처리 지원.

---

## Rationale

**1. PIT 정합성 보장**
FRED 거시 지표는 발표일(release_date)과 기준일(trade_date)이 다르다.
Gold 레이어에서 `econ_events → fred_vintages → assumed_t+1` 3단계 fallback으로
`selected_release_date < trade_date` 조건을 항상 보장한다.
단일 레이어 구조에서는 이 보장이 구현상 어렵다.

**2. 원본 보존으로 재처리 가능**
Bronze에 원본을 유지하면 Silver/Gold 피처 계산 로직이 바뀌어도
원본 재수집 없이 Bronze로부터 전체를 재처리할 수 있다.
전략 연구 중 피처 정의 변경이 잦은 환경에서 필수적이다.

**3. 레이어 간 계약 명확화**
각 레이어는 직전 레이어만 읽는 read-only consumer다.
Gold가 Bronze를 직접 참조하면 데이터 계약이 무너지고 파이프라인 의존성이 복잡해진다.

**4. Airflow 오케스트레이션 적합성**
레이어별 DAG task로 분리되어 있어, 실패 시 해당 레이어부터 재시작 가능하다.
전체 파이프라인을 처음부터 재실행할 필요가 없다.

---

## Alternatives Considered

| 대안 | 거부 이유 |
|---|---|
| 단일 레이어 (직접 피처 계산) | PIT 정합성 구현 복잡, 원본 유실 시 재수집 필요 |
| DB 기반 (PostgreSQL 등) | 시계열 Parquet 대비 스캔 성능 낮음, 로컬 개발 환경 제약 |
| 외부 Feature Store | 인프라 의존성 추가, 로컬 연구 환경에 과도한 복잡성 |

---

## Consequences

**수용한 트레이드오프**
- 저장 공간: 동일 데이터가 3개 레이어에 존재하여 용량 증가
- 파이프라인 복잡성: Bronze/Silver/Gold 각각 별도 작업 필요

**얻은 것**
- 임의 과거 시점 전략 재현 가능 (Snapshot Reproducibility)
- PIT 위반 없는 Backtest 보장
- 피처 재정의 시 Bronze 재수집 없이 재처리 가능
- 레이어별 독립 테스트 가능
