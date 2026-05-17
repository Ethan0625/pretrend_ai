# Group Transition Signal — Contract (SOT)

Markers: architecture, contract
Status: active

> 🟢 **Market Data Platform 관측 계약**
>
> 본 문서는 Gold feature layer를 소비해 **섹터/자산군 rotation**을 관측하는 계약입니다.
> 투자 의사결정이나 매매 지시가 아니라 read-only observation context로 활용됩니다.
> `group_transition` 코드는 P21에서 `observability/regime/rotation/`로 이전 완료되었습니다.
> 기존 `strategy_engine/group_transition/`는 re-export shim으로 backward compat을 유지합니다.
> 디렉토리 명은 `rotation`이지만 코드 심볼(`GROUP_TRANSITION_SIGNAL_COLUMNS`, `build_group_transition_signal`)은 그대로 유지합니다.
> 참조: [`track_separation.md`](./track_separation.md)

## 문서 상태
| Item | Value |
| --- | --- |
| Status | **Active (Observability 자료, Phase 1 추출 완료 — 2026-05-13)** |
| Structure Policy | 구조는 고정, 기능은 확장 |
| Effective Date | 2026-02-26 |
| Change Tracking | docs/changelog.md |

## 목차
- [1. 문서 목적](#1-문서-목적)
- [2. 범위와 제외 범위](#2-scope--non-goals)
- [3. Inputs](#3-inputs)
- [4. Outputs](#4-outputs)
- [5. Grain / Key](#5-grain--key)
- [6. State Rules](#6-state-rules)
- [7. Invariants](#7-invariants)
- [8. DoD](#8-dod)

참조:
- `docs/architecture/next_step_signal_contract.md`
- `docs/architecture/allocation_engine_contract.md`
- `docs/architecture/paper_execution_ledger_contract.md`
- `docs/architecture/strategy_engine_design.md`

## 1. 문서 목적
### 책임
- 전술 자산군(SECTOR/COMMODITY/BOND/COUNTRY) 전이예측 계약을 고정한다.
- Strategy/Paper/Backtest가 공통 소비하는 그룹 전이 snapshot 인터페이스를 고정한다.

### 제외 범위
- 하드게이트(`run_universe`, `risk_gate`) 대체
- 종목 단위 실행 신호 생성

## 2. 범위와 제외 범위
### Scope
- 그룹 현재 상태(`STRONG/NEUTRAL/WEAK/UNKNOWN`) 산출
- 5/10/20 거래일 sojourn/hazard/expected 출력
- snapshot/history 저장 및 소비 규칙

### 제외 범위
- ML 학습/튜닝
- 그룹 상태 기반 하드 차단 로직

## 3. Inputs
| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| trade_date / rebalance_date | DATE | Y | 기준일 |
| symbol | TEXT | Y | ETF 심볼 |
| asset_group | TEXT | Y | `SECTOR`, `COMMODITY`, `BOND`, `COUNTRY` |
| relative_strength | FLOAT | Y | `ret_20d(symbol) - ret_20d(SPY)` |
| is_candidate | BOOLEAN | N | Universe 후보 여부 |

## 4. Outputs
저장 경로:
- Snapshot: `data/strategy/group_transition_signal/decision_date=YYYY-MM-DD/*.parquet`
- History: `data/strategy/group_transition_history/year=YYYY/month=MM/*.parquet`

| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| trade_date | DATE | Y | 기준일 |
| asset_group | TEXT | Y | 전술 자산군 |
| group_state_now | TEXT | Y | `STRONG`, `NEUTRAL`, `WEAK`, `UNKNOWN` |
| group_expected_5d | TEXT | N | 5D 예상 상태 |
| group_expected_10d | TEXT | N | 10D 예상 상태 |
| group_expected_20d | TEXT | N | 20D 예상 상태 |
| group_sojourn_prob_5d | FLOAT | N | 5D 지속확률 |
| group_sojourn_prob_10d | FLOAT | N | 10D 지속확률 |
| group_sojourn_prob_20d | FLOAT | N | 20D 지속확률 |
| group_transition_hazard_5d | FLOAT | N | 5D 전환위험 |
| group_transition_hazard_10d | FLOAT | N | 10D 전환위험 |
| group_transition_hazard_20d | FLOAT | N | 20D 전환위험 |
| group_confidence | FLOAT | N | 신뢰도 |
| source_run_id | TEXT | Y | 생성 run 식별자 |

## 5. Grain / Key
- Snapshot Grain: `(trade_date, asset_group)`
- History Key: `(trade_date, asset_group, decision_date_ref)`

## 6. State Rules
- `STRONG`: 그룹 RS 중앙값 > 0 이고 양수 비율(`pos_ratio`)이 `>= 0.5`인 경우
- `WEAK`: 그룹 RS 중앙값 < 0 이고 양수 비율(`pos_ratio`)이 `< 0.4`인 경우
- 나머지: `NEUTRAL`
- 표본 부족(`rs_values` 수 < 2) 시: `UNKNOWN` (fail-open)

## 7. Invariants
- 하드게이트 우선 원칙은 유지된다(본 신호는 soft gate 전용).
- `group_transition_hazard_hd = 1 - group_sojourn_prob_hd` 관계를 유지한다(결측 제외).
- 결측/소표본은 `UNKNOWN`/`N/A`로 fail-open 처리한다.
- 런타임 소비는 저장본(snapshot + history) 우선이다.

## 8. DoD
- **GTS1**: 필수 컬럼/ENUM/그레인 검증
- **GTS2**: 5/10/20 hazard 값 범위 `[0,1]` 검증(결측 제외)
- **GTS3**: 표본 부족 시 `UNKNOWN` fail-open 검증
- **GTS4**: history key 중복 방지 검증
- **GTS5**: SIGNAL/PAPER/BACKTEST 소비 경로에서 결측 fallback 검증

---

## 변경 이력
| 날짜 | 요약 | 참조 |
| --- | --- | --- |
| 2026-02-26 | tactical asset-group 전이예측 계약 신규 추가 | docs/changelog.md |
| 2026-05-13 | P21로 `group_transition`을 `observability/regime/rotation/`으로 추출, 기존 경로는 shim 유지 | docs/changelog.md |
