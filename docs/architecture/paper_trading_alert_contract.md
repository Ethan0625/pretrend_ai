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
- 실전 계좌 자동 주문 집행
- Level 3(실거래) 브로커 운영

## 2. Scope & Non-Goals
### Scope
- Telegram 메시지 타입 분리(SIGNAL vs PAPER_RESULT)
- Paper Trading 요약 payload(표시) 계약
- 전송 실패 처리 정책
- SIM/MOCK 동시 운영 시 식별 필드 계약

**권위 구현 경로(canonical)**:
- `pretrend.pipeline.paper.execution` — PAPER_RESULT 생성 권위 구현 (source_job=`paper_trading_dag`)
- `pretrend.pipeline.backtest.paper_execution` — 하위 호환 shim (deprecated, 신규 코드는 canonical 경로 사용)
- `pretrend.pipeline.broker.kis_mock` — 모의투자 브로커 어댑터(옵션, `PAPER_BROKER_ENABLED=1`일 때만 실행)
- `pretrend.pipeline.broker.order_manager` — 주문 실행/리컨실리에이션 유틸

### Non-goals
- 가상 체결 계산식/NAV 산출 규칙 정의
- 전략 신호 생성 로직 변경

## 3. Message Types
| 타입 | source_job | 목적 | 기본 주기 |
| --- | --- | --- | --- |
| SIGNAL | strategy_engine_dag | 현재 시장 상태/근거/전술 신호 보고 | 일 1회 |
| PAPER_RESULT | paper_trading_dag | 모의계좌 체결/손익/포지션 변화 요약 | 일 1회 EOD |

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
| paper_start_date | DATE | N | paper 누적 시뮬레이션 시작일(`PAPER_START_DATE`) |

PAPER_RESULT 전용 필드:
| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| action | TEXT | Y | `INCREASE` / `DECREASE` / `HOLD` |
| next_invested_ratio | FLOAT | Y | 다음 목표 투자비중 |
| delta_ratio | FLOAT | Y | 비중 변화량 |
| virtual_fills | ARRAY<TEXT> | Y | 모의계좌 체결 요약 |
| daily_pnl | FLOAT | N | 당일 손익(없으면 null) |
| cumulative_pnl | FLOAT | N | 누적 손익(없으면 null) |
| position_changes | ARRAY<TEXT> | Y | 포지션 변화 요약 |
| top_positions | ARRAY<JSON> | N | 상위 보유 종목(평단/현재가/수량/평가/손익) |
| risk_warnings | ARRAY<TEXT> | N | 리스크 경고 목록 |
| effective_bias | TEXT | N | 실행 시 적용된 bias (`RISK_ON_BIAS` 등) |
| bias_source | TEXT | N | bias 출처 (`SNAPSHOT`, `LOCKED`, `OVERRIDE`, `UNKNOWN`) |
| override_reason | TEXT | N | override 사유 (`PANIC`, `RISK_OFF`, `NONE`) |
| hard_gate_run_universe | BOOLEAN | N | 하드게이트 run_universe 상태 |
| hard_gate_risk_gate | BOOLEAN | N | 하드게이트 risk_gate 상태 |
| effective_max_tactical_slots | INT | N | 적용된 전술 슬롯 수 |
| effective_tactical_weight | FLOAT | N | 적용된 전술 비중 강도 |
| hazard_10d | FLOAT | N | 10거래일 전환 위험도(설명용) |
| broker_auth_status | TEXT | N | 브로커 인증 상태(`OK`, `FAILED`, `UNKNOWN`) |
| broker_token_refresh_count | INT | N | 당일 토큰 갱신 횟수 |
| broker_orders_count | INT | N | 당일 주문 건수 |
| broker_fills_count | INT | N | 당일 체결 건수 |
| execution_mode | TEXT | N | 실행 모드(`SIM`, `MOCK`) |
| capital_source | TEXT | N | 자본 원천(`ENV_SIM`, `BROKER_BALANCE`) |
| broker_source | TEXT | N | 브로커 원천(`NONE`, `KIS_MOCK`, `KIS_LIVE`) |
| account_id | TEXT | N | 계좌 식별자(masked) |
| nav_source | TEXT | N | NAV 원천(`SIM_LEDGER`, `BROKER_SNAPSHOT`) |
| group_gate_applied_groups | ARRAY<TEXT> | N | 적용된 tactical 그룹 |
| group_gate_reduced_groups | ARRAY<TEXT> | N | 축소된 tactical 그룹 |
| group_gate_source | TEXT | N | 그룹 게이트 소스 (`SNAPSHOT`, `MISSING`) |
| fx_usdkrw | FLOAT | N | KRW→USD 환산 환율(표시용, KIS 우선/fallback 가능) |

계산식/운영조건은 `paper_execution_ledger_contract.md`를 따른다.
표시 계층과 계산 계층을 분리하며, 알림 payload는 계산 결과의 요약만 담당한다.

## 6. Invariants
- SIGNAL과 PAPER_RESULT는 `message_type`으로 명확히 구분된다.
- PAPER_RESULT는 일 1회 EOD 전송을 기본으로 한다.
- Telegram 전송 실패는 fail-open 처리된다.
- `message_type/source_job/decision_date/simulation_date` 4개 공통 필드는 항상 포함된다.
- SIM/MOCK 동시 운영 시 `execution_mode`는 필수 식별축으로 동작해야 하며, compare 발송에서도 동일 기준을 유지한다.
- Renderer는 payload를 그대로 렌더링하며 env/config를 재해석하지 않는다(payload-only).

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
| 2026-02-26 | PAPER_RESULT payload에 group gate 요약 필드 추가 | docs/changelog.md |
| 2026-02-25 | SIGNAL/PAPER_RESULT 분리 전송 + paper EOD + fail-open 정책 계약 추가 | docs/changelog.md |
