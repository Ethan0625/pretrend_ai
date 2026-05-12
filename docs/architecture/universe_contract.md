# Universe-ETF — Contract (SOT)

> 🔄 **Mixed (대부분 Observability Track 공유 자산)**
>
> 본 문서는 2026Q2 방향 재정의 후 다음과 같이 분리됩니다:
> - **ETF Universe 정의** (SOT 32 ETFs, asset_group, asset_subtype 등): **Observability Track 공유 자산** — 시장 관측의 입력 universe로 그대로 활용.
> - **Execution Universe picking 로직** (RS 기반 상위 N 선정 등): **Personal Track Frozen** — 투자 의사결정 영역.
>
> Phase 1+ 진입 시 본 문서에서 picking 로직 부분을 분리해 `universe_observation_contract.md` (가칭)로 재정리할 계획입니다.
> 참조: [`track_separation.md`](./track_separation.md), [`REFACTOR_2026Q2.md`](../../.agent/REFACTOR_2026Q2.md)

## Document Status
| Item | Value |
| --- | --- |
| Status | **Mixed (Observability-shared + Frozen picking)** — 헤더 참조 |
| Structure Policy | ETF SOT(32종) 정의는 두 트랙 공유 유지, picking 로직(RS 상위 N 선정 등)은 동결 |
| Effective Date | 2026-02-21 (재분류: 2026-05-12) |
| Change Tracking | docs/changelog.md |

## Capability Matrix
| Capability | Status | Notes |
| --- | --- | --- |
| Core scope | Active | 본 문서의 계약/설계 범위 |
| Extension ports | Reserved | v1+ 확장 포트는 인터페이스만 정의 |
| Numeric scoring/tuning | Not supported | 본 문서 범위에서 금지 |

## TOC
- [1. 문서 목적](#1-문서-목적)
- [2. Scope & Non-Goals](#2-scope--non-goals)
- [3. 입력 계약](#3-입력-계약)
- [4. 출력 계약](#4-출력-계약)
- [5. Grain / Key](#5-grain--key)
- [6. 불변식](#6-불변식)
- [7. DoD](#7-dod)
- [8. Universe-Stock(U0~U3) Extension Port (Research)](#8-universe-stocku0u3-extension-port-research)

연계 문서:
- `docs/strategy_architecture.md`
- `docs/architecture/market_structure_composer_contract.md`
- `docs/architecture/gold_design_contract.md`
- `docs/architecture/calendar_design_contract.md`
- `docs/architecture/eod_observability_contract.md`

## 1. 문서 목적
### 책임
- Universe-ETF(v1)의 입력/출력 인터페이스를 SOT로 고정한다.
- Market Structure Composer와 Allocation Engine 사이의 계약 경계를 명확히 한다.

### Non-goals
- 자산별 상세 점수식, 가중치, 랭킹 로직을 정의하지 않는다.

## 2. Scope & Non-Goals
### 책임
- Observability ETF 대상의 후보 선별 계약을 정의한다(Execution Universe 범위).
- Composer 차단 상태에서 결과 제약을 명시한다.

### Non-goals
- 대상: 개별 종목 제외, Observability ETF만
- Universe-Stock(U0~U3) 파이프라인은 본 계약 범위 밖(별도 로드맵)
- 주문 실행/포지션 사이징 포함하지 않음

## 3. 입력 계약
### 책임
- Universe-ETF 입력 소스와 필수 컬럼을 고정한다.

### Non-goals
- 입력 테이블 재계산/보정

입력 소스:
1. Market Structure Composer output
2. Gold EOD Features

입력 스키마:

| 입력 | 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| MS Composer | trade_date | DATE | Y | 기준일 |
| MS Composer | long_phase | TEXT | Y | 장기 국면(`EXPANSION/LATE_CYCLE/SLOWDOWN/RECOVERY/RECESSION/UNKNOWN`) |
| MS Composer | mid_regime | TEXT | Y | 중기 위험 상태(`RISK_ON/NEUTRAL/RISK_OFF/UNKNOWN`) |
| MS Composer | run_universe | BOOLEAN | Y | Universe-ETF 실행 여부 |
| MS Composer | risk_gate | BOOLEAN | Y | 증가 차단 브레이크 상태 |
| Gold EOD | symbol | TEXT | Y | Observability 심볼 |
| Gold EOD | trade_date | DATE | Y | 기준일 |
| Gold EOD | asset_group | TEXT | Y | 그룹 라벨 |
| Gold EOD | asset_name | TEXT | Y | canonical 라벨 |
| Gold EOD | asset_subtype | TEXT | N | 세부 라벨 |
| Gold EOD | ret_20d | FLOAT | N | 상대강도 재료 |
| Gold EOD | vol_20d | FLOAT | N | 리스크 재료 |

## 4. 출력 계약
### 책임
- Allocation Engine이 소비 가능한 `candidate_etf_list` 스키마를 고정한다.

### Non-goals
- 후보 개수 제한/정렬 규칙 확정

필수 출력 컬럼:

| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| rebalance_date | DATE | Y | 리밸런싱 기준일 |
| symbol | TEXT | Y | ETF 심볼 |
| asset_group | TEXT | Y | 그룹 라벨 |
| relative_strength | FLOAT | N | 상대강도 지표 (`ret_20d(symbol) - ret_20d(SPY)`) |
| is_candidate | BOOLEAN | Y | 후보 여부 |

개념 예시:

```yaml
rebalance_date: 2026-02-12
symbol: XLV
asset_group: SECTOR
relative_strength: 0.14
is_candidate: true
```

## 5. Grain / Key
### 책임
- 출력 grain과 유일성 기준을 명시한다.

### Non-goals
- 동일일 다중 버전 관리 전략

- Grain: `(decision_date, symbol)`
- Primary key: `(decision_date, symbol)`
- `decision_date`는 Composer `trade_date`와 동일 캘린더 기준을 사용한다.

## 6. 불변식
### 책임
- Universe-ETF 출력의 무결성 제약을 명시한다.

### Non-goals
- 후보 우선순위 알고리즘 정의

- Observability 라벨은 read-only (입력 라벨 수정 금지)
- `run_universe=false`이면 candidate 0개
- `is_candidate`는 BOOLEAN 외 값 금지
- `asset_group`은 Observability ENUM(`INDEX/COUNTRY/COMMODITY/BOND/SECTOR`) 외 값 금지
- Phase eligible pool 규칙은 아래 표를 따른다.

| long_phase | 제외 심볼 |
| --- | --- |
| RECESSION | `USO`, `UNG` |
| SLOWDOWN | `UNG` |
| LATE_CYCLE | 없음 (전체 허용) |
| EXPANSION | `UNG` |
| RECOVERY | `USO`, `UNG`, `XLE` |
| UNKNOWN | 없음 (fail-open) |

- `mid_regime`별 TACTICAL Top-N 규칙은 아래 표를 따른다.

| mid_regime | Top-N |
| --- | --- |
| RISK_OFF | 5 |
| NEUTRAL | 7 |
| RISK_ON | 9 |
| UNKNOWN | 7 |

- CORE(`SPY`, `SCHD`, `IAU`)는 phase 필터/Top-N 적용 대상이 아니며 항상 `is_candidate=true`를 유지한다.
  (TLT는 BOND tactical로 이동 — RECESSION/SLOWDOWN에서 RS 기반 자동 선정됨)

## 7. DoD
### 책임
- 구현 검증 최소 기준을 제공한다.

### Non-goals
- 테스트 데이터셋 고정

- **UV1**: 차단 상태(`run_universe=false`) 입력 시 candidate 0개 검증
- **UV2**: 필수 컬럼/타입 검증
- **UV3**: `asset_group` ENUM 위반 금지 검증
- **UV4**: phase별 제외 규칙(`RECESSION/SLOWDOWN/RECOVERY`) 검증
- **UV5**: `mid_regime`별 Top-N(`RISK_OFF=5`, `RISK_ON=9`) 검증
- **UV6**: 상대강도 공식(`ret_20d - ret_20d(SPY)`) 검증

## 8. Universe-Stock(U0~U3) Extension Port (Research)
### 책임
- 본 절은 `Universe-Stock(U0~U3)` 연구 파이프라인의 인터페이스 경계만 정의한다.
- Strategy Engine `Universe-ETF(Execution)`와 충돌하지 않도록 입력/출력 분리를 명시한다.

### Non-goals
- U0~U3 계산 로직, 점수식, 외부 API 스펙을 확정하지 않는다.
- 본 문서 범위에서 개별 종목 실행/주문 로직을 정의하지 않는다.

### 단계별 산출물(초안)
| Stage | 이름 | 입력(예시) | 출력(초안) |
| --- | --- | --- | --- |
| U0 | Macro Signal Detector | Macro 정책/이벤트 입력 | `macro_signal_event` |
| U1 | Theme Prioritization | U0 + ETF 성과/유입 proxy | `theme_priority_snapshot` |
| U2 | Theme Universe-Stock Builder | U1 + 테마-종목 매핑 | `theme_stock_candidates` |
| U3 | Growth & Flow Filtering | U2 + 성장/수급/모멘텀 feature | `stock_universe_snapshot` |

### 인터페이스 경계(Execution 분리)
- `Universe-ETF` 입력/출력(`decision_date, symbol`)과 `Universe-Stock` 산출물은 서로 독립 키를 사용한다.
- `Universe-Stock` 산출물은 Strategy Engine 실행 경로의 필수 입력이 아니다(Research 파이프라인).
- M2 구현 전까지 `Universe-ETF` 계약/테스트(UV1~UV6)는 변경 없이 유지한다.

### Grain/Key 분리 원칙 (Gate A)
- Universe-ETF(Execution) grain: `(decision_date, symbol)` (본 문서 §5)
- Universe-Stock(Research) 초안 grain:
  - U0: `(as_of_date, signal_id)`
  - U1: `(as_of_date, theme_id)`
  - U2: `(as_of_date, theme_id, symbol)`
  - U3: `(as_of_date, symbol)`
- 위 키는 Execution Universe key와 격리되며, 동일 테이블/파티션을 공유하지 않는다.

### DoD (U0~U3 계약 초안)
- **US1**: U0~U3 용어/입출력 이름이 문서에 고정됨
- **US2**: Execution/Research 키 격리 원칙이 문서에 명시됨
- **US3**: `milestones.md` M2 범위와 충돌 없음(로드맵 정합)

---

## Change History
| Date | Summary | References |
| --- | --- | --- |
| 2026-02-21 | Universe-ETF v1 규칙 반영: phase eligible pool, mid_regime Top-N, RS 정의 및 CORE 예외 명시 | docs/changelog.md |
| 2026-02-21 | Universe 용어 이원화 반영: Universe-ETF(Execution) 계약으로 명시, Universe-Stock(U0~U3) 범위 분리 | docs/changelog.md |
| 2026-02-13 | 파일명 버전 제거 및 문서 표준 블록(Document Status/Capability Matrix) 적용 | docs/changelog.md |
