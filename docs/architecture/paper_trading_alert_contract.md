# Paper Trading Alert — Contract (SOT)

## Document Status
| Item | Value |
| --- | --- |
| Status | Active |
| Structure Policy | 구조는 고정, 기능은 확장 |
| Effective Date | 2026-02-25 |
| Change Tracking | docs/changelog.md |

## Capability Matrix
| Capability | Status | Notes |
| --- | --- | --- |
| Core scope | Active | 본 문서의 계약/설계 범위 |
| Extension ports | Reserved | Paper execution 고도화 포트만 정의 |
| Numeric scoring/tuning | Not supported | 본 문서 범위에서 금지 |

## TOC
- [1. 문서 목적](#1-문서-목적)
- [2. Scope & Non-Goals](#2-scope--non-goals)
- [3. Message Types](#3-message-types)
- [4. Scheduling / Delivery](#4-scheduling--delivery)
- [5. Payload Interface](#5-payload-interface)
- [6. Invariants](#6-invariants)
- [7. DoD](#7-dod)

참조:
- `docs/architecture/paper_execution_ledger_contract.md`
- `docs/strategy_engine_design.md`
- `docs/architecture/next_step_signal_contract.md`
- `docs/architecture/walk_forward_validation_contract.md`
- `docs/operation_guide.md`

## 1. 문서 목적
### 책임
- SIGNAL(`strategy_engine_job`)과 PAPER_RESULT(`paper_trading`)를 동일 Telegram 채널에서 분리 전송하는 규칙을 고정한다.
- Paper Trading 알림 범위를 "일 1회 EOD 요약"으로 고정한다.
- Telegram 전송 실패 시 fail-open 정책을 고정한다.

### Non-goals
- 실거래 주문 집행
- broker API 연동

## 2. Scope & Non-Goals
### Scope
- Telegram 메시지 타입 분리(SIGNAL vs PAPER_RESULT)
- Paper Trading 요약 payload(표시) 계약
- 전송 실패 처리 정책

### Non-goals
- 가상 체결 계산식/NAV 산출 규칙 정의
- 전략 신호 생성 로직 변경

## 3. Message Types
| 타입 | source_job | 목적 | 기본 주기 |
| --- | --- | --- | --- |
| SIGNAL | strategy_engine_dag | 현재 시장 상태/근거/전술 신호 보고 | 일 1회 |
| PAPER_RESULT | paper_trading_dag | 가상 체결/손익/포지션 변화 요약 | 일 1회 EOD |

## 4. Scheduling / Delivery
- 전송 채널은 동일 Telegram chat_id를 사용한다.
- `strategy_engine_dag`는 기존 스케줄을 유지한다.
- `paper_trading_dag`는 EOD 기준 일 1회 실행한다.
- Telegram 미설정/전송 오류는 fail-open으로 처리한다(경고 로그 + 파이프라인 성공 유지).

## 5. Payload Interface
공통 필드:
| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| message_type | TEXT | Y | `SIGNAL` 또는 `PAPER_RESULT` |
| source_job | TEXT | Y | 생성 DAG/Job 식별자 |
| decision_date | DATE | Y | 전략 판단 기준일 |
| simulation_date | DATE | Y | 시뮬레이션/전송 기준일 |

PAPER_RESULT 전용 필드:
| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| action | TEXT | Y | `INCREASE` / `DECREASE` / `HOLD` |
| next_invested_ratio | FLOAT | Y | 다음 목표 투자비중 |
| delta_ratio | FLOAT | Y | 비중 변화량 |
| virtual_fills | ARRAY<TEXT> | Y | 가상 체결 요약 |
| daily_pnl | FLOAT | N | 당일 손익(없으면 null) |
| cumulative_pnl | FLOAT | N | 누적 손익(없으면 null) |
| position_changes | ARRAY<TEXT> | Y | 포지션 변화 요약 |
| top_positions | ARRAY<JSON> | N | 상위 보유 종목(평단/현재가/수량/평가/손익) |
| risk_warnings | ARRAY<TEXT> | N | 리스크 경고 목록 |

계산식/운영조건은 `paper_execution_ledger_contract.md`를 따른다.

## 6. Invariants
- SIGNAL과 PAPER_RESULT는 `message_type`으로 명확히 구분된다.
- PAPER_RESULT는 일 1회 EOD 전송을 기본으로 한다.
- Telegram 전송 실패는 fail-open 처리된다.
- `message_type/source_job/decision_date/simulation_date` 4개 공통 필드는 항상 포함된다.

## 7. DoD
- **PTA1**: SIGNAL/PAPER_RESULT 메시지 타입 구분 검증
- **PTA2**: PAPER_RESULT payload 필수 필드 검증
- **PTA3**: EOD 일 1회 스케줄 검증
- **PTA4**: Telegram 전송 실패 시 fail-open 동작 검증
- **PTA5**: 운영 문서에서 메시지 경계/실패 정책 확인 가능

---

## Change History
| Date | Summary | References |
| --- | --- | --- |
| 2026-02-25 | SIGNAL/PAPER_RESULT 분리 전송 + paper EOD + fail-open 정책 계약 추가 | docs/changelog.md |
