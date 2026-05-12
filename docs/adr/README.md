# Architecture Decision Records (ADR)

> ⚠️ **2026Q2 방향 재정의 — ADR 트랙 컨텍스트**
>
> 본 폴더의 ADR들은 **작성 시점 의사결정 기록**입니다. 2026Q2 방향 재정의 후 트랙 분류:
>
> - **🟢 Infrastructure 결정**: ADR-001 (Medallion) — 두 트랙 공유, 유효
> - **🔄 Observability Track 자료**: ADR-002 (Rule-based Engine), ADR-003 (Three-Layer Market Structure), ADR-005 (LLM Interpretation) — 시장 관측 컨텍스트로 재해석
> - **⚠️ Mixed**: ADR-004 (ETF-based Execution Universe) — Universe SOT는 공유, picking 부분은 Personal Track
> - **🔒 Personal Track Frozen**: ADR-006 (Execution Tier Hierarchy) — Level 1/2/3 실행 계층, 운영 중단
>
> ADR 자체는 immutable 의사결정 기록이며, 현재 트랙 분류는 [`../architecture/track_separation.md`](../architecture/track_separation.md)를 우선 참조합니다.

이 디렉토리는 Pretrend AI 시스템의 핵심 설계 결정과 그 근거를 기록한다.

각 ADR은 "왜 이렇게 설계했는가"에 답한다.
구현 계약(Contract)은 `docs/architecture/`를 참조한다.

---

## ADR 목록

| 번호 | 제목 | 상태 | 영향 범위 |
|---|---|---|---|
| [ADR-001](ADR-001-medallion-data-architecture.md) | Medallion Data Architecture (Bronze/Silver/Gold) | Accepted | 전체 데이터 레이어 |
| [ADR-002](ADR-002-rule-based-signal-engine.md) | Rule-based Signal Engine (ML 대신) | Accepted | Long/Mid/Short Engine |
| [ADR-003](ADR-003-three-layer-market-structure.md) | 3-Layer Market Structure (Long/Mid/Short + Composer) | Accepted | 전략 신호 구조 |
| [ADR-004](ADR-004-etf-based-execution-universe.md) | ETF 기반 실행 Universe | Accepted | Allocation Engine |
| [ADR-005](ADR-005-llm-interpretation-layer.md) | LLM을 해석 계층으로만 한정 | Accepted | LLM 통합 정책 |
| [ADR-006](ADR-006-execution-tier-hierarchy.md) | 실행 계층 분리 (Backtest → SIM → Mock → Live) | Accepted | 실행 인프라 전체 |

---

## ADR 형식

각 ADR은 아래 구조를 따른다.

- **Context**: 이 결정이 필요했던 상황과 제약
- **Decision**: 채택한 결정
- **Rationale**: 결정의 이유
- **Alternatives Considered**: 검토했으나 거부한 대안과 이유
- **Consequences**: 수용한 트레이드오프와 얻은 것

---

## 관련 문서

- 시스템 전체 아키텍처: `docs/architecture.md`
- 전략 아키텍처: `docs/strategy_architecture.md`
- 구현 계약 상세: `docs/architecture/`
- 운영 가이드: `docs/operation_guide.md`
