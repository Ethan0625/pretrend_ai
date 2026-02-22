# Strategy Engine — Design (SOT)

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
- [SECTION A — One-page Summary](#section-a--one-page-summary)
- [SECTION B — End-to-End Flow](#section-b--end-to-end-flow)
- [SECTION C — Inputs Inventory (Current vs Future)](#section-c--inputs-inventory-current-vs-future)
- [SECTION D — Outputs (3 Boundary Schemas)](#section-d--outputs-3-boundary-schemas)
- [SECTION E — Snapshot Storage](#section-e--snapshot-storage)
- [SECTION F — Invariants (Core Contracts)](#section-f--invariants-core-contracts)
- [SECTION G — Definition of Done (DoD)](#section-g--definition-of-done-dod)
- [SECTION H — Doc Consolidation Plan](#section-h--doc-consolidation-plan)
- [SECTION I — Stock Extension Port (v1+ Reserved)](#section-i--stock-extension-port-v1-reserved)
- [SECTION J — Text Signals & LLM(AI Agent) Integration Port (v1+ Reserved)](#section-j--text-signals--llmai-agent-integration-port-v1-reserved)
- [SECTION K — Implementation Status (2026-02-21)](#section-k--implementation-status-2026-02-21)

---

## SECTION A — One-page Summary

### A1) Pretrend 전체 시스템
Pretrend AI는 시장 위치 판단, 자산 구조 결정, 실행 경계 출력을 분리한 전략 시스템이다. 전략 엔진은 입력 계층을 Gold Layer로 고정해 재현 가능한 스냅샷 기반 실행을 보장한다. 출력 경계는 `WHAT_TO_HOLD`, `HOW_MUCH_EXPOSURE`, `HOW_MUCH_TO_SELL` 3개로 나뉘며, 각 경계는 역할이 중복되지 않도록 계약으로 고정한다. 정책 선택은 하드코딩 분기 대신 정책 registry 기반 선택 구조를 사용한다. v0에서는 수치 점수화, 최적화, 자동 튜닝을 금지하고 상태 기반 규칙만 허용한다. 엔진 결과는 `decision_date` 기준으로 저장되며, 동일 입력 스냅샷 재실행 시 동일 출력이 나와야 한다. 이 문서는 구현 이전/이후 모두 참조 가능한 단일 SOT로 동작한다. 상위 레이어 계약 변경 시 본 문서의 입력 계약을 먼저 동기화해야 한다.

### A2) Data Layer
Data Layer는 Bronze, Silver, Gold의 3단계로 구성되며 Strategy Engine은 Gold만 소비한다. Bronze는 원천 수집과 최소 정규화, Silver는 중복 제거/정합성 보정, Gold는 전략 소비를 위한 PIT-safe feature 스냅샷을 제공한다. Gold는 read-only 입력이며 Strategy Engine은 Gold 데이터를 수정하거나 재해석 저장하지 않는다. v0 기준 핵심 입력은 Gold Macro Feature와 Gold EOD Feature다. Macro는 정책/유동성 축 근거를, EOD는 가격/변동성 및 proxy 축 근거를 제공한다. 입력 스키마는 axis feature 빌더에서 표준화하며 Horizon 엔진은 표준화된 axis outputs만 소비한다. 레이어 경계를 넘는 계산 중복을 금지해 재현성과 책임 분리를 유지한다. 결측 데이터는 fail-open 원칙으로 `UNKNOWN` 상태로 전달한다.

### A3) Strategy Engine
Strategy Engine은 `Axis × Horizon = 12 slots` 상태 해석 구조를 사용한다. Axis는 `macro_policy`, `price_volatility`, `flow_structure`, `sentiment` 4개 근거 축이며 Horizon은 `long`, `mid`, `short` 관측 해상도다. 엔진 순서는 Axis Feature Builder, Axis×Horizon State, Market Position, Policy Selector, Universe-ETF Selector, Allocation Engine, Sell Advisor, Weekly Report로 고정한다. Market Position은 상태 벡터를 표준화해 정책 선택과 실행 경계 출력의 공통 입력을 제공한다. Policy Selector는 registry에서 정책을 선택하되 점수 최적화 없이 상태 기반 룰만 사용한다. Universe-ETF Selector는 무엇을 보유할지 결정하고 Allocation Engine은 총 투자 비율만 조정한다. Sell Advisor는 v0에서 매도 예산과 우선순위만 정의하며 종목별 정밀 매도 비율은 다루지 않는다. 모든 출력은 `decision_date` 스냅샷으로 저장된다.
현재 실행 범위는 `Universe-ETF(Execution Universe)`이며, `Universe-Stock(U0~U3)`는 별도 로드맵 파이프라인이다.

---

## SECTION B — End-to-End Flow

```mermaid
flowchart TD
    GM[Gold Macro Snapshot] --> AFB[Axis Feature Builder]
    GE[Gold EOD Snapshot] --> AFB

    AFB --> AHS[Axis x Horizon State (12 slots)]
    AHS --> MP[Market Position]
    MP --> PS[Policy Selector (registry)]
    PS --> US[Universe-ETF Selector]
    PS --> AE[Allocation Engine]
    US --> WTH[WHAT_TO_HOLD]
    AE --> EXP[HOW_MUCH_EXPOSURE]
    PS --> SA[Sell Advisor]
    SA --> SELL[HOW_MUCH_TO_SELL]

    WTH --> WR[Weekly Report]
    EXP --> WR
    SELL --> WR

    TXT[Text Signals Pipeline (Future, Optional)] -. feature feed only .-> AFB
```

---

## SECTION C — Inputs Inventory (Current vs Future)

### C1) 입력 인벤토리 표

| Input Class | Source Path | Grain / Key | Required Columns | Optional Columns | Coverage / Unknown Handling |
| --- | --- | --- | --- | --- | --- |
| Gold Macro Feature (v0 Required) | `data/gold/macro/macro_features/year=YYYY/month=MM/*.parquet` | Grain `(indicator_id, trade_date)`, Key `(indicator_id, trade_date)` | `indicator_id`, `trade_date`, `selected_value`, `selected_release_date`, `regime` | `delta_1m`, `delta_3m`, `delta_6m`, `release_source` | 결측 시 해당 axis slot `UNKNOWN`; output schema 유지 |
| Gold EOD Feature (v0 Required) | `data/gold/eod/eod_features/symbol=XXX/year=YYYY/month=MM/*.parquet` | Grain `(symbol, trade_date)`, Key `(symbol, trade_date)` | `symbol`, `trade_date`, `ret_*`, `vol_*`, `asset_group`, `asset_name` | `asset_subtype`, `outlier_flag`, `drawdown_*`, `range_*` | 결측 시 axis coverage 하락 플래그 기록, `UNKNOWN` 허용 |
| Flow Structure Proxy (v0 Partial) | `data/gold/eod/eod_features/...` + 파생 집계 | Grain `(trade_date)` 또는 `(symbol, trade_date)` | `volume`, breadth proxy(`iwm_spy_spread`) | `volume_zscore_20d`, `obv_*` | 부분 수집 허용; 누락 시 `flow_structure=UNKNOWN` |
| Sentiment Proxy (v0 Partial) | `data/gold/eod/eod_features/...` 파생 | Grain `(trade_date)` | risk spread proxy(`SPY/TLT/IAU`), volatility proxy(`SPY vol`) | `iwm_spy_vol_spread`, `intraday_range` | v0에서 proxy만 사용; 누락 시 `sentiment=UNKNOWN` |
| VIX Sentiment (v1+ Reserved) | `data/sentiment/vix/year=YYYY/month=MM/*.parquet` | Grain `(trade_date)` | `trade_date`, `vix_level` | `vix_term_structure_*` | v0 `NOT_USED`; v1+에서 옵션 활성화 |
| Text Signals (Future Reserved) | `data/silver/text_signals/...` (예정) | Grain `(trade_date)` 또는 `(topic, trade_date)` | `trade_date`, `signal_type`, `signal_value` | `source`, `confidence_tag` | v0 미사용; feature feed-only |
| External Sentiment Rails (Future Reserved) | `data/silver/external_sentiment/...` (예정) | Grain `(trade_date)` | `trade_date`, `rail_id`, `state_tag` | `metadata` | v0 미사용; 결측 시 무시 가능 |

### C2) v0 입력 원칙
- v0 필수 입력은 Gold Macro + Gold EOD 두 가지다.
- Flow/Sentiment는 proxy 기반 partial 입력을 허용한다.
- Future 입력(VIX/Text/External)은 reserved이며 v0 의사결정에 직접 사용하지 않는다.

---

## SECTION D — Outputs (3 Boundary Schemas)

### D1) WHAT_TO_HOLD
- Grain / Key: Grain `(decision_date)`, Key `(decision_date)`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| decision_date | DATE | Y | 전략 결정 기준일 |
| core_hold_list | ARRAY<TEXT> | Y | 기본 보유 자산군/심볼 목록 |
| tactical_groups_allowed | ARRAY<TEXT> | Y | 전술적으로 허용된 그룹 |
| buy_candidates | ARRAY<TEXT> | N | 신규 매수 후보 심볼 목록 |
| rationale_tags | ARRAY<TEXT> | N | 상태 기반 판단 태그 |

#### D1-1) Universe-ETF v1 선택 규칙
- 선택 규칙은 `phase eligible pool + mid_regime Top-N`으로 고정한다.
- 상대강도는 `ret_20d(symbol) - ret_20d(SPY)`를 사용한다.
- CORE(`SPY`, `SCHD`, `IAU`)는 phase 필터/Top-N과 무관하게 항상 후보(`is_candidate=true`)로 유지한다.
  (`TLT`는 BOND tactical로 이동 — RECESSION/SLOWDOWN에서 RS 기반으로 자동 선정)

Phase eligible pool:

| long_phase | 제외 심볼 |
| --- | --- |
| RECESSION | `USO`, `UNG` |
| SLOWDOWN | `UNG` |
| LATE_CYCLE | 없음 |
| EXPANSION | `UNG` |
| RECOVERY | `USO`, `UNG`, `XLE` |
| UNKNOWN | 없음 (fail-open) |

mid_regime Top-N:

| mid_regime | Top-N |
| --- | --- |
| RISK_OFF | 5 |
| NEUTRAL | 7 |
| RISK_ON | 9 |
| UNKNOWN | 7 |

### D2) HOW_MUCH_EXPOSURE
- Grain / Key: Grain `(decision_date)`, Key `(decision_date)`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| decision_date | DATE | Y | 전략 결정 기준일 |
| next_invested_ratio | FLOAT | Y | 다음 주기 목표 총 투자 비율 |
| action | ENUM(`INCREASE`,`DECREASE`,`HOLD`) | Y | 투자비율 조정 액션 |
| current_invested_ratio | FLOAT | Y | 현재 총 투자 비율 |
| adjustment_applied | FLOAT | Y | 실제 반영된 조정폭 |
| blocked_by_risk_gate | BOOLEAN | N | 증가 차단 여부 |

### D3) HOW_MUCH_TO_SELL
- Grain / Key: Grain `(decision_date)`, Key `(decision_date)`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| decision_date | DATE | Y | 전략 결정 기준일 |
| sell_budget_ratio | FLOAT | Y | 해당 주기 총 매도 예산 비율 |
| sell_priority_list | ARRAY<TEXT> | Y | 매도 우선순위 리스트 |
| rationale_tags | ARRAY<TEXT> | N | 매도 판단 태그 |
| execution_notes | ARRAY<TEXT> | N | 실행 메모 |

---

## SECTION E — Snapshot Storage

### E1) 저장 규칙
- 모든 산출물은 `decision_date` 파티션 기준으로 저장한다.
- write 패턴은 `_tmp_run={run_id}`에 먼저 기록 후 atomic rename으로 최종 반영한다.
- 동일 파티션 재실행 시 overwrite(write-replace)한다.
- 저장 규칙은 idempotent를 유지해야 하며 append 기반 중복 저장을 금지한다.

### E2) 디렉터리 구조 예시
- `data/strategy/axis_horizon_state/decision_date=YYYY-MM-DD/state_YYYYMMDD.parquet`
- `data/strategy/market_position/decision_date=YYYY-MM-DD/market_position_YYYYMMDD.parquet`
- `data/strategy/policy_selection/decision_date=YYYY-MM-DD/policy_selection_YYYYMMDD.parquet`
- `data/strategy/what_to_hold/decision_date=YYYY-MM-DD/what_to_hold_YYYYMMDD.parquet`
- `data/strategy/exposure/decision_date=YYYY-MM-DD/exposure_YYYYMMDD.parquet`
- `data/strategy/sell_plan/decision_date=YYYY-MM-DD/sell_plan_YYYYMMDD.parquet`
- `data/strategy/weekly_report/decision_date=YYYY-MM-DD/weekly_report_YYYYMMDD.parquet`

---

## SECTION F — Invariants (Core Contracts)

- Axis×Horizon 슬롯은 `4 x 3 = 12`로 고정한다.
- 상태 출력은 ENUM 기반만 허용하며 numeric score 출력은 금지한다.
- `risk_gate=false`이면 `action=INCREASE`는 금지한다.
- `run_universe=false`이면 `buy_candidates`는 비어야 하며 증가 액션도 금지한다.
- `adjustment_limit`은 exposure 변화량에 반드시 적용되어야 한다.
- `step_size` 양자화 규칙은 exposure 조정 결과에 반드시 반영되어야 한다.
- SELL v0는 `sell_budget_ratio`와 `sell_priority_list`만 정의하며 심볼별 정밀 퍼센트 할당은 하지 않는다.
- Strategy Engine은 raw feature를 직접 계산하지 않고 axis feature 산출물을 소비한다.

---

## SECTION G — Definition of Done (DoD)

- 출력 경계 3종(WHAT/EXPOSURE/SELL) 스키마 존재 및 타입 일치
- ENUM 필드 유효성 검증(허용값 외 금지)
- Axis×Horizon 12 슬롯 존재 검증
- 동일 `decision_date` 재실행 시 스냅샷 재현성 보장
- exposure 불변식(`adjustment_limit`, `risk_gate`, `step_size`) 충족
- WHAT 출력에 `core_hold_list`와 `tactical_groups_allowed`가 명확히 포함
- SELL 출력에 예산(`sell_budget_ratio`)과 우선순위(`sell_priority_list`) 포함
- 정의된 strategy 저장 경로가 문서 규칙과 일치

---

## SECTION H — Doc Consolidation Plan

### H1) Absorb into Strategy Engine SOT
- `docs/architecture/universe_contract.md`
  - rationale: WHAT 경계 입력/출력 정의를 Strategy Engine 단일 흐름에서 직접 관리
- `docs/architecture/market_structure_composer_contract.md`
  - rationale: Axis×Horizon 상태와 Market Position을 Strategy Engine 내부 표준 인터페이스로 흡수
- `docs/architecture/allocation_engine_contract.md`
  - rationale: EXPOSURE 경계를 Strategy Engine 실행 계약으로 통합

### H2) Keep (Linked)
- `docs/architecture/axis_horizon_dependency_contract.md`
  - rationale: Axis/Horizon 의존성 매트릭스의 별도 계약 유지
- Gold 관련 계약(`docs/architecture/gold_design_contract.md`, `docs/architecture/calendar_design_contract.md`)
  - rationale: Strategy Engine 입력의 상위 데이터 계약
- EOD/Macro 계약(`docs/architecture/eod_observability_contract.md` 포함)
  - rationale: 입력 데이터 라벨/그레인 불변식 유지
- Market Structure Long/Mid/Short 계약
  - rationale: 해상도별 상태 해석 모듈 계약 유지

### H3) Move (Phase2)
- `docs/universe_design.md`의 legacy 서술 중 재활용 가능한 운영 설명
  - rationale: Strategy Engine 중심 구조와 충돌하지 않는 부분만 분리/이관
- U0~U3 계열 문서의 데이터 수집 메모 중 소스 인벤토리 성격 항목
  - rationale: `docs/market_structure_data_inventory.md` 또는 별도 메모 문서로 이관

### H4) Deprecated
- `docs/universe_design.md` (legacy 서술이 남아 있는 버전)
  - rationale: Strategy Engine 단일 SOT에 중복 정의 발생
- U0~U3 기반 구형 문서군
  - rationale: 현재 Axis×Horizon + Composer 구조와 불일치
- score-centric 계약 문서
  - rationale: v0 정책(점수화/튜닝 금지)과 충돌

---

## SECTION I — Stock Extension Port (v1+ Reserved)

### 목적
- v0는 ETF 중심 구조를 유지하고, v1+에서 개별 종목(Stock)을 Tactical 영역에 편입 가능한 reserved 포트를 정의한다.
- Stock 분석은 외부 모듈에서 수행하며 Strategy Engine은 편입 적합성(Eligibility) 결과만 소비한다.

### 프로세스
1. `stock_candidate_input` 수신(수동/외부 입력)
2. 외부 Stock 분석 모듈이 가격/재무/텍스트 근거를 집계
3. Strategy Engine 상태(`Axis×Horizon`, `Market Position`)와 정합성 검증
4. `eligibility_flag` 기반 `Add/Reject` 결정

### 입력(Reserved)
- `stock_candidate_input`: `(symbol, requested_at, request_reason optional)`
- `stock_analysis_snapshot`: `decision_date` 기준 분석 결과 스냅샷

### 출력 스키마 (Reserved: `stock_analysis_snapshot`)
- Grain / Key: Grain `(decision_date, symbol)`, Key `(decision_date, symbol)`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| decision_date | DATE | Y | 전략 의사결정 기준일 |
| symbol | TEXT | Y | 개별 종목 |
| growth_profile | ENUM(`HIGH`,`MED`,`LOW`,`UNKNOWN`) | N | 성장 프로파일 |
| risk_profile | ENUM(`HIGH`,`MED`,`LOW`,`UNKNOWN`) | N | 리스크 프로파일 |
| narrative_alignment | ENUM(`ALIGNED`,`NEUTRAL`,`MISALIGNED`,`UNKNOWN`) | N | 내러티브 정합성 |
| eligibility_flag | BOOLEAN | Y | 편입 가능 여부 |
| notes | TEXT | N | 근거 요약 |

### Invariants
- v0에서는 Stock 자동 편입/자동 매수 금지(`manual approval only`).
- Stock은 v1+에서 Tactical 영역에만 편입 가능하며 Core ETF를 대체하지 않는다.
- Eligibility는 Stock 단독 판단이 아니라 Market Position 정합성을 포함해야 한다.
- `decision_date` 스냅샷 저장/overwrite 규칙은 Strategy Engine 본체 규칙과 동일하다.

### 스냅샷 저장 (Reserved)
- `data/strategy/stock_analysis/decision_date=YYYY-MM-DD/*.parquet`

---

## SECTION J — Text Signals & LLM(AI Agent) Integration Port

### 목적
- Text/LLM 입력은 Strategy Engine 내부 수집이 아니라 외부 Text Pipeline 레이어에서 생성된 Gold numeric feature를 옵션 포트로 소비한다.
- **텍스트 feature는 보조 입력**: Strategy Engine 핵심 판단(4축 Axis Feature)은 Macro + EOD 기반. 텍스트 결측 시에도 핵심 로직은 계속 동작한다 (fail-open).
- v0 구현: `gold.text_daily_features` (long format, 룰 기반 3개 feature) 소비 포트 예약.

### v0 Gold Text Feature 포맷 (2026-02-20 확정)
- 입력: `data/gold/text/text_daily_features/year=YYYY/month=MM/*.parquet`
- 스키마: `(trade_date, feature_name, feature_value, feature_version, coverage_ratio, staleness_days)`
- 초기 feature: `macro_hawkish_score`, `filing_risk_burst`, `policy_uncertainty_idx`
- 수집 소스: SEC EDGAR (8-K/10-Q/10-K), Fed/FOMC RSS

### 입력 포트 (Reserved: `text_signal_snapshot`)
- Grain / Key: Grain `(decision_date, source)`, Key `(decision_date, source)`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| decision_date | DATE | Y | 기준일 |
| source | TEXT | Y | `news`/`policy`/`filing` 등 |
| signal_label | TEXT | N | 정성 라벨(예: `RISK_UP`) |
| confidence | FLOAT | N | 0~1 범위의 upstream 산출 신뢰도 |
| summary | TEXT | N | 1~3문장 요약 |
| entities | TEXT | N | 관련 키워드/티커 목록 |

### 출력 경계 (Reserved)
- 본 포트 자체는 의사결정 출력을 직접 생성하지 않는다.
- Strategy Engine 내부에서는 `axis_features_*` 보조 입력으로만 전달된다.

### Invariants
- Strategy Engine은 LLM을 직접 호출하지 않는다(호출 책임은 외부 서비스/파이프라인).
- Text 입력 결측은 허용되며, 결측이 v0 실행 중단 사유가 되어서는 안 된다.
- Text 신호는 Axis×Horizon/Market Position의 보조 근거로만 사용하며 결정 구조를 변경하지 않는다.

### 스냅샷 저장 (Reserved)
- `data/strategy/text_signals/decision_date=YYYY-MM-DD/*.parquet`

---

## SECTION K — Implementation Status (2026-02-22)

### K1) 구현 범위
- Strategy Engine v0 파이프라인이 end-to-end로 구현되었다.
- Long Engine v1 정규화가 반영되었다(`delta_6m` 지표별 rolling z-score, `z_threshold=0.3` 기본값).
- 실행 단계:
  1. Axis Features (4축)
  2. Axis×Horizon State (12-slot)
  3. Market Position
  4. Policy Selector (`RC_V0_DEFAULT`)
  5. Universe-ETF (Observability ETF)
  6. Allocation (`invested_ratio` 조절)
  7. Sell Advisor (예산/우선순위 — advisory)

### K2) 모듈 구성
| 경로 | 역할 |
| --- | --- |
| `pipeline/strategy_engine/config.py` | StrategyEngineConfig, PolicyProfile, DEFAULT_POLICY_V0 |
| `pipeline/strategy_engine/registries.py` | 정책/코어홀드/전술그룹 레지스트리 |
| `pipeline/strategy_engine/io.py` | Gold 로더, atomic snapshot writer |
| `pipeline/strategy_engine/axis_features/` | 4축 feature 빌더 |
| `pipeline/strategy_engine/axis_horizon_state/` | Long/Mid/Short engine, 12-slot builder |
| `pipeline/strategy_engine/market_position/` | 상태 벡터 결합 |
| `pipeline/strategy_engine/policy_selector/` | 정책 적용, `risk_gate`/`run_universe` 판정 |
| `pipeline/strategy_engine/universe/` | ETF 후보 선별 |
| `pipeline/strategy_engine/allocation/` | 총 투자 비율 조절 |
| `pipeline/strategy_engine/sell_advisor/` | 매도 권고 (advisory) |
| `pipeline/strategy_engine/strategy_job.py` | E2E runner + CLI |

### K3) 데이터 커버리지(보고 기준)
| 레이어 | 범위 | 비고 |
| --- | --- | --- |
| Bronze/Silver/Gold Macro | 2006-01 ~ 2026-02 | 5개 거시 지표 |
| Bronze/Silver/Gold EOD | 2006-01 ~ 2026-02 | 32개 중 25개 심볼 가용(7개 미출시) |
| Strategy snapshots | 2009-03-09, 2024-06-03 | 실데이터 검증용 |

### K4) 테스트/검증(보고 기준)
- 전체 테스트 결과: `389 passed, 1 skipped`
- Strategy Engine 관련 테스트 소계: 140 (+19 Allocation v1/v2)
- Backtest Engine 관련 테스트 소계: 62
- 실데이터 검증(GFC 구간)에서 `RISK_OFF`/`PANIC` 감지 동작을 확인했다.

### K5) 수정 이력(요약)
- Allocation 양자화 부동소수점 오차 수정
- 단기 변동성 임계 스케일 정합성 수정(연환산/일간 스케일 혼동 제거)
- 정책 범위 하한(`target_invested_lower`) 조정 반영
- Long Engine v1 정규화 반영(rolling z-score + NaN sign fallback)
- Long phase 분류 임계값 `z_threshold=0.3` 채택
- Universe Engine v1 반영(phase eligible pool + mid_regime Top-N + RS vs SPY)
- `strategy_job.py`에서 `decision_date` 하루치 Universe 계산으로 snapshot 누적 버그 수정
- Backtest Runner에서 `what_to_hold` snapshot 의존 제거, `gold_eod` 기반 inline Universe 계산으로 전환
- Allocation v1/v2 추가: `build_allocation(allocation_mode)` 파라미터, `_ALLOCATION_V1_MAP`, `_ALLOCATION_V2_MAP`
- `strategy_job.py` CLI에 `--allocation-mode v0|v1|v2` 추가
- `sell_planner/` → `sell_advisor/` 리네임: `build_sell_plan` → `build_sell_advice`, advisory 역할 명시
- Mid Engine v1.1: breadth 계산 `ratio(iwm/spy)` → `spread(iwm-spy)` 교체로 음수 SPY 구간 부호 반전 버그 수정
- Short Engine: `smallcap_stress(iwm_spy_vol_spread > 0.005)`를 secondary PANIC 확인 신호에 추가(4신호 중 2개)

### K8) 백테스트 성과 (2026-02-22 기준, 2006-01-03 ~ 2024-06-03, DCA $300/월, v2 preset)

| 지표 | v0 | v1 | v1.1 |
| --- | --- | --- | --- |
| XIRR (DCA) | +8.00% | +6.94% | +7.25% |
| MDD | -15.71% | -17.74% | -15.65% |
| Sharpe | 1.69 | 1.65 | 1.68 |

> **v1.1**: Mid breadth spread 교정으로 v1 대비 XIRR +0.31%p 회복, MDD/Sharpe 개선.

### K9) Backtest Allocation 아키텍처 vs Strategy Engine

**Allocation 버전 차이**

| 구분 | Strategy Engine | Backtest Engine |
| --- | --- | --- |
| v0 (range-maintenance) | O — `--allocation-mode v0` (기본값) | O — preset v0 |
| v1 (target-seeking) | O — `--allocation-mode v1` | O — preset v1 |
| v2 (2D lookup) | O — `--allocation-mode v2` | O — preset v2 |

Strategy Engine의 Allocation 단계는 `allocation_mode` 파라미터로 v0/v1/v2를 선택한다.
- v0: `_compute_allocation()` — [target_lower, target_upper] 범위 유지, risk_gate=False → INCREASE 차단
- v1: `_compute_allocation_v1()` — `_ALLOCATION_V1_MAP[long_phase]` 목표 추적, PANIC 시 저점매수 허용
- v2: `_compute_allocation_v2()` — `_ALLOCATION_V2_MAP[(long_phase, mid_regime)]` 4단계 fallback

Backtest는 SE 스냅샷 **대신** `gold_eod` inline Universe + 동일한 allocation 함수를 직접 실행한다.

**Sell Advisor — Advisory 역할**

`HOW_MUCH_TO_SELL` 스냅샷(`sell_budget_ratio`, `sell_priority_list`)은 **권고(advisory)** 출력이다.
- `sell_budget_ratio` = Allocation이 계산한 `current - next` delta의 단순 반영 (실행 예산은 Allocation이 결정)
- `sell_priority_list` = RS 역순 정렬 우선순위 목록 (참고용)
- **실제 매도 실행** = Backtest Runner의 `_execute_sell_tranche()` — target_weights 기반으로 과매수 종목 우선 매도

Sell Advisor는 실행 엔진이 아닌 advisory 출력 모듈이다.
모듈: `pipeline/strategy_engine/sell_advisor/`, 함수: `build_sell_advice()`, 스냅샷: `data/strategy/sell_advice/`

### K6) v0 제약 재확인
- 신규 VIX/뉴스/외부 감성 수집 없음(proxy only)
- 동적 ETF 내부 가중치 배분 없음
- 점수/가중치 최적화 없음
- 정책 프로파일 단일(`RC_V0_DEFAULT`)

### K7) 실행 명령
```bash
# v0 (range-maintenance, 기본값)
python -m pretrend.pipeline.strategy_engine.strategy_job --date 2024-06-03 --invested-ratio 0.10

# v1 (target-seeking)
python -m pretrend.pipeline.strategy_engine.strategy_job --date 2024-06-03 --invested-ratio 0.10 \
    --long-z-threshold 0.3 --allocation-mode v1

# v2 (2D lookup)
python -m pretrend.pipeline.strategy_engine.strategy_job --date 2024-06-03 --invested-ratio 0.10 \
    --long-z-threshold 0.3 --allocation-mode v2
```

---

## Change History
| Date | Summary | References |
| --- | --- | --- |
| 2026-02-22 | sell_planner→sell_advisor 리네임, Allocation v1/v2 추가, K4/K5/K7/K9 갱신 | docs/changelog.md |
| 2026-02-22 | CORE 정의 수정(TLT→SCHD), K4 테스트 수 갱신, K8 성과 DCA 기준 교체, K9 Allocation 아키텍처/Sell Advisor advisory 역할 추가 | docs/changelog.md |
| 2026-02-21 | Implementation Status 날짜/테스트 현황/Long Engine v1(z-threshold=0.3) 반영 | docs/changelog.md |
| 2026-02-13 | 파일명 버전 제거 및 문서 표준 블록(Document Status/Capability Matrix) 적용 | docs/changelog.md |
| 2026-02-13 | Strategy Engine 구현 현황(모듈/커버리지/테스트/검증) 반영 | docs/changelog.md |
