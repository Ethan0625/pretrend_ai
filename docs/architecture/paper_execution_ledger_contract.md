# Paper Execution Ledger — Contract (SOT)

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
| Extension ports | Reserved | 체결 모델 고도화 포트만 정의 |
| Numeric scoring/tuning | Not supported | 본 문서 범위에서 금지 |

## TOC
- [1. 문서 목적](#1-문서-목적)
- [2. Scope & Non-Goals](#2-scope--non-goals)
- [3. Inputs](#3-inputs)
- [4. Output Tables](#4-output-tables)
- [5. Grain / Key](#5-grain--key)
- [6. Execution Rules](#6-execution-rules)
- [7. Valuation / PnL Rules](#7-valuation--pnl-rules)
- [8. Invariants](#8-invariants)
- [9. DoD](#9-dod)
- [10. Level 2 운영 가드레일](#10-level-2-운영-가드레일)

참조:
- `docs/architecture/paper_trading_alert_contract.md`
- `docs/architecture/allocation_engine_contract.md`
- `docs/architecture/next_step_signal_contract.md`
- `docs/architecture/group_transition_signal_contract.md`
- `docs/strategy_engine_design.md`

## 1. 문서 목적
### 책임
- EOD 기준 가상 체결 레이어의 입력/출력/계산식을 고정한다.
- NAV 기반 `daily_pnl`, `cumulative_pnl` 산출 규칙을 고정한다.
- 종목별 포지션 상세(평단/현재가/수량/평가금액/손익률) 인터페이스를 고정한다.

### Non-goals
- 실거래 주문 집행
- 인트라데이 체결 모델

## 2. Scope & Non-Goals
### Scope
- strategy `exposure` 신호 기반 EOD 가상 체결
- `execution_ledger`, `positions_daily`, `portfolio_daily` 산출
- 운영 조건(초기자금/DCA/요일 규칙/SCHD 매도 금지) 적용
- SIM/MOCK 동시 운영 시 mode 분리 저장/조회 규칙

### Non-goals
- 실전(Level 3) 자동 주문 연동
- 체결 슬리피지/수수료 모델 최적화

## 3. Inputs
| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| trade_date | DATE | Y | 의사결정/실행 기준일 |
| action | TEXT | Y | `INCREASE` / `DECREASE` / `HOLD` |
| next_invested_ratio | FLOAT | Y | 목표 투자 비율 |
| delta_ratio | FLOAT | Y | 비중 변화량 |
| adj_close | FLOAT | Y | EOD 평가 가격 (`gold/eod/eod_features`) |
| bias_20d (next_step) | TEXT | N | 전이예측 20거래일 bias (`RISK_ON_BIAS`/`NEUTRAL_BIAS`/`RISK_OFF_BIAS`/`UNKNOWN`) |

운영 파라미터 (기본값):
- `initial_capital = 1,000,000원`
- `monthly_addition = 300,000원`
- `sell_tranches = [0.50, 0.30, 0.20]`
- `schd_sell_locked = true`
- `PAPER_FX_USDKRW = 1300` (KRW→USD 환산 기본값, KIS 환율 결측 시 fallback)

통화 처리:
- 운영 입력(`initial_capital`, `monthly_addition`)은 KRW 단위다.
- 체결/평가 가격(`adj_close`)은 USD 단위다.
- 실행 엔진은 KRW 입력을 KIS 환율(`fx_usdkrw`) 우선, 결측 시 `PAPER_FX_USDKRW` fallback으로 USD 환산 후 체결 계산한다.

## 4. Output Tables
### 4.1 execution_ledger
| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| trade_date | DATE | 체결일 |
| execution_mode | TEXT | 실행 모드(`SIM`, `MOCK`) |
| symbol | TEXT | 종목 |
| action | TEXT | `BUY`/`SELL` |
| shares | FLOAT | 체결 수량 |
| price_eod | FLOAT | 체결 가격(EOD) |
| amount | FLOAT | 체결 금액 |
| sequence_id | INT | 동일일 체결 순서 |
| source_job | TEXT | 생성 Job |
| message_type | TEXT | `PAPER_RESULT` |
| decision_date | DATE | 기준 decision_date |
| simulation_date | DATE | 시뮬레이션 생성일 |
| capital_source | TEXT | 자본 원천(`ENV_SIM`, `BROKER_BALANCE`) |
| broker_source | TEXT | 브로커 원천(`NONE`, `KIS_MOCK`, `KIS_LIVE`) |
| account_id | TEXT | 계좌 식별자(masked) |
| nav_source | TEXT | NAV 원천(`SIM_LEDGER`, `BROKER_SNAPSHOT`) |

### 4.2 positions_daily
| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| trade_date | DATE | 기준일 |
| execution_mode | TEXT | 실행 모드(`SIM`, `MOCK`) |
| symbol | TEXT | 종목 |
| shares | FLOAT | 보유 수량 |
| avg_cost | FLOAT | 평단가 |
| eod_price | FLOAT | EOD 가격 |
| market_value | FLOAT | 평가금액 |
| gain_pct | FLOAT | 손익률 |
| weight | FLOAT | 투자자산 내 비중 |

### 4.3 portfolio_daily
| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| trade_date | DATE | 기준일 |
| execution_mode | TEXT | 실행 모드(`SIM`, `MOCK`) |
| cash | FLOAT | 현금 |
| invested_value | FLOAT | 투자자산 합계 |
| nav | FLOAT | 총자산 |
| total_invested_capital | FLOAT | 누적 투입원금 |
| daily_pnl | FLOAT | 일간 손익률 |
| cumulative_pnl | FLOAT | 누적 손익률 |
| capital_source | TEXT | 자본 원천(`ENV_SIM`, `BROKER_BALANCE`) |
| broker_source | TEXT | 브로커 원천(`NONE`, `KIS_MOCK`, `KIS_LIVE`) |
| account_id | TEXT | 계좌 식별자(masked) |
| nav_source | TEXT | NAV 원천(`SIM_LEDGER`, `BROKER_SNAPSHOT`) |

## 5. Grain / Key
- `execution_ledger` Grain: `(trade_date, execution_mode, symbol, action, sequence_id)`
- `positions_daily` Grain: `(trade_date, execution_mode, symbol)`
- `portfolio_daily` Grain: `(trade_date, execution_mode)`

## 6. Execution Rules
- 월요일: 전 거래일(T-1) 기준 신호 평가(체결 없음)
- 화요일: `INCREASE` 실행(현금 배포 매수)
- 금요일: `DECREASE` 단계 매도(`50% -> 30% -> 20%`)
- 월 첫 거래일: `monthly_addition` 자금 추가(DCA)
- `SCHD`는 매도 금지 (`schd_sell_locked=true`)
- phase는 `next_invested_ratio`를 통해 매수 강도에 반영
- tactical universe는 `policy_selection + what_to_hold(is_candidate, relative_strength)` 기준으로 반영
- tactical group 전이는 `group_transition_signal` 저장본(snapshot + history) 기준으로 반영
- `WEAK` 그룹은 tactical slots/weight 우선 축소 대상이다(soft gate)
- v3.4.1에서는 `WEAK` 그룹 수가 2개 이상일 때만 축소를 발동한다.
- v3.4.1 재진입(축소 해제) 조건:
  - `short_signal=RELIEF` 2거래일 연속 또는
  - `mid_regime=RISK_ON`
- 재진입 조건이 충족되기 전까지 축소 상태는 유지된다.
- v3.4.2a(체류 규칙 완화 실험):
  - cooldown 기본값은 5거래일을 유지한다.
  - 단, `mid_regime=RISK_ON` 또는 `short_signal=RELIEF` 2연속이면 cooldown을 2거래일로 압축할 수 있다.
  - `run_universe=false -> true` 복귀 직후 + `RELIEF` 2연속이면 월요일 판정에서 `RISK_OFF_BIAS -> NEUTRAL_BIAS` 1단 완화를 허용한다(즉시 `RISK_ON` 점프 금지).
  - 위 완화는 soft-only이며 하드게이트 우선순위를 변경하지 않는다.
- `next_step` 입력은 저장본 우선(snapshot + history 결합)으로 로드한다.
- 런타임 재계산은 기본 금지하고 결측 시 fail-open을 적용한다.
- 전이예측 soft gate는 tactical 강도만 조절한다:
  - `RISK_ON_BIAS`: 기본 강도 유지
  - `NEUTRAL_BIAS`: 완화
  - `RISK_OFF_BIAS`: 축소/코어 우선
  - `UNKNOWN`: `NEUTRAL_BIAS`와 동일 fail-open
- 우선순위:
  1. 하드 게이트(`run_universe`, `risk_gate`)
  2. 전이예측 soft gate
  3. 기본 리밸런싱 규칙

## 7. Valuation / PnL Rules
- `market_value = shares * eod_price`
- `invested_value = Σ market_value`
- `nav = cash + invested_value`
- `daily_pnl = nav_t / nav_{t-1} - 1`
- `cumulative_pnl = (nav_t - total_invested_capital) / total_invested_capital`
- `total_invested_capital = initial_capital + cumulative_monthly_addition`

## 8. Invariants
- 가격 소스는 `Gold EOD adj_close`로 고정한다.
- `SCHD` 매도 체결은 생성되지 않아야 한다.
- `daily_pnl`, `cumulative_pnl`는 NAV 기준으로 계산된다.
- 누적 투입원금(`total_invested_capital`)은 DCA 반영 시점에 증가한다.
- 결측 가격은 fail-open으로 처리(체결 스킵 + 경고 로그).
- 전이예측은 하드 게이트를 우회하지 못한다(soft-only).
- SIM/MOCK 동시 실행 시 `execution_mode` 구분 저장을 강제한다(동일 `trade_date` overwrite 금지).
- `MOCK` 결과의 NAV/포지션 표시는 `BROKER_SNAPSHOT` 원천이 우선이며, fallback 발생 시 경고를 남긴다.

## 9. DoD
- **PEL1**: 3개 출력 테이블 컬럼/타입 검증
- **PEL2**: NAV/PnL 계산식 검증
- **PEL3**: 월초 DCA 반영 검증
- **PEL4**: 화요일 INCREASE/금요일 DECREASE 실행 규칙 검증
- **PEL5**: SCHD 매도 금지 규칙 검증
- **PEL6**: 결측 가격 fail-open 검증
- **PEL7**: next_step bias soft gate(강도 조절) 검증
- **PEL8**: 하드 게이트 우선 적용(`run_universe=false` 등) 검증
- **PEL9**: group transition soft gate 적용(WEAK 그룹 축소) + 결측 fail-open 검증
- **PEL10**: v3.4.1 재진입 규칙(WEAK>=2 진입, RELIEF streak/MID RISK_ON 해제) 검증
- **PEL11**: v3.4.2a cooldown 압축 플래그(`cooldown_compressed_*`) 및 hard-gate exit assist 플래그(`hard_gate_exit_assist_*`) 반영 검증

## 10. Level 2 운영 가드레일
본 섹션은 Level 2(Paper + Alert) 운영 경계를 정의한다. 자동 주문 실행(Level 3)은 범위 밖이다.

### 임계값 (백테스트 실증 기반)

2006~2024 전체 구간(DCA $300/월) 백테스트에서 도출:
| 조건 | 임계값 | 근거 |
|------|--------|------|
| NAV / total_invested_capital | < 0.85 | 누적 투입원금 대비 -15% 손실 |
| (NAV - peak_NAV) / peak_NAV  | < -0.20 | ATH 대비 -20% 낙폭 (v3.4.2a 최악: -19.08%) |
| PANIC streak | >= 5 | 경고만 (hard stop 아님) |

### 발동 시 동작
- INCREASE 실행 차단 (Tuesday 매수 스킵)
- DECREASE는 허용 (추가 손실 방지 위한 매도는 진행)
- DCA 현금 주입 유지 (누적 투입원금 계산 유지)
- Paper 시뮬레이션은 계속 진행 (루프 중단 없음)
- `portfolio_daily`에 `guardrail_paused=True` 컬럼 기록
- Telegram `risk_warnings`에 `🚨 Level 2 가드레일 발동` 포함

### 복귀 조건 (자동)
- NAV / total_invested_capital >= 0.90 AND ATH 대비 낙폭 >= -0.15
- 자동 복귀 시 `guardrail_paused=False`로 전환, INCREASE 재개

### 수동 승인 지점 (운영자 확인)
- DECREASE 3회 연속 후 첫 INCREASE 시도 구간 (Telegram 경고 포함)
- `run_universe` 하드게이트 복귀 직후 첫 주간 (기존 규칙 유지)

### 기록 의무
- `guardrail_paused` / `guardrail_nav_breach` / `guardrail_peak_dd_breach` / `guardrail_panic_streak` / `peak_nav` 컬럼이 `portfolio_daily`에 매일 기록됨
- 발동/복귀 이벤트는 Telegram `risk_warnings` 섹션에 자동 포함

---

## Change History
| Date | Summary | References |
| --- | --- | --- |
| 2026-02-27 | v3.4.2a 실험 규칙 추가: cooldown 조건부 압축 + hard-gate exit assist(soft-only) | docs/changelog.md |
| 2026-02-26 | v3.4.1 재진입 규칙 추가: WEAK>=2 진입 + RELIEF 2연속/MID RISK_ON 해제 | docs/changelog.md |
| 2026-02-26 | group transition 입력 추가: WEAK 그룹 tactical 축소(soft gate), 결측 fail-open 명시 | docs/changelog.md |
| 2026-02-25 | next_step_signal soft gate 입력 추가(하드 게이트 우선/강도 조절 규칙 명시) | docs/changelog.md |
| 2026-02-25 | EOD 가상체결 레이어 계약 신규 추가 (NAV/PnL/포지션 상세) | docs/changelog.md |
