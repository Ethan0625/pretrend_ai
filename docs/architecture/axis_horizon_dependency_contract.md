# Axis-Horizon Dependency — Contract (SOT)

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
- [1. 문서 목적](#1-문서-목적)
- [2. Scope & Non-Goals](#2-scope--non-goals)
- [3. Axis Feature Contract (Inputs)](#3-axis-feature-contract-inputs)
- [4. Horizon Engine Dependency Matrix](#4-horizon-engine-dependency-matrix)
- [5. Data Freshness / Coverage 규칙](#5-data-freshness--coverage-규칙)
- [6. Invariants](#6-invariants)
- [7. DoD](#7-dod)

참조:
- `docs/strategy_architecture.md`
- `docs/architecture/market_structure_long_contract.md`
- `docs/architecture/market_structure_mid_contract.md`
- `docs/architecture/market_structure_short_contract.md`
- `docs/architecture/market_structure_composer_contract.md`
- `docs/architecture/universe_contract.md`
- `docs/architecture/allocation_engine_contract.md`
- `docs/market_structure_data_inventory.md`

## 1. 문서 목적
### 책임
- Axis Feature와 Horizon Engine의 입력 의존성을 표준화한다.
- `axis(근거 데이터 축)`과 `horizon(관측 해상도)` 혼선을 방지한다.
- Composer/Universe/Allocation 구현 시 공통 참조 기준(SOT)을 제공한다.

축 vs 해상도 구분(요약):
- Axis는 상태 판단의 근거 데이터 분류다.
- Horizon은 동일 Axis를 시간 해상도별로 해석하는 계산 모듈이다.
- Axis는 feature를 생산하고, Horizon은 해당 feature를 소비한다.
- 동일 Axis라도 Horizon마다 REQUIRED/OPTIONAL이 달라질 수 있다.
- Horizon은 raw feature를 직접 계산하지 않는다.

### Non-goals
- 상태 판정식 정의
- 임계값/가중치/스코어링 정의

## 2. Scope & Non-Goals
### Scope
- Axis Feature 입력 소스/그레인/키/필수 컬럼 표준화
- Horizon(long_phase, mid_regime, short_signal)별 입력 의존성 매핑
- 결측/coverage/freshness 표현 규칙

### Non-goals
- 상태 전이 로직 상세
- 신규 데이터 ingest 정의(VIX/Flow/뉴스/설문)

## 3. Axis Feature Contract (Inputs)

### 3.1 Axis Feature 요약표

| Axis Feature | Source Tables | Grain / Key | v0 가용성 | v1+ 가용성 |
| --- | --- | --- | --- | --- |
| macro_policy | `data/gold/macro/macro_features/year=YYYY/month=MM/*.parquet` | Grain: `(indicator_id, trade_date)` / Key: `(indicator_id, trade_date)` | ✅ | ✅ |
| price_volatility | `data/gold/eod/eod_features/symbol=XXX/year=YYYY/month=MM/*.parquet` | Grain: `(symbol, trade_date)` / Key: `(symbol, trade_date)` | ✅ | ✅ |
| flow_structure | `data/gold/eod/eod_features/symbol=XXX/year=YYYY/month=MM/*.parquet` + 파생 뷰 | Grain: `(symbol, trade_date)` / Key: `(symbol, trade_date)` | ⏳ (부분 수집) | ✅ (확장) |
| sentiment | v0: `data/gold/eod/eod_features/...` 기반 proxy 파생 / v1+: `data/sentiment/vix/...`(예정) | Grain: `(trade_date)` 또는 `(symbol, trade_date)` 파생 후 정규화 | ✅ (proxy) | ⏳ (VIX 옵션) |

### 3.2 Axis별 Required Columns

| Axis Feature | Required Columns |
| --- | --- |
| macro_policy | `indicator_id`, `trade_date`, `selected_value`, `selected_release_date`, `regime` |
| price_volatility | `symbol`, `trade_date`, `ret_*`, `vol_*` |
| flow_structure | `symbol`, `trade_date`, `volume`, `asset_group` |
| sentiment(v0 proxy) | `trade_date`, `SPY/TLT/IAU` 기반 return proxy, `SPY` 변동성 proxy |

### 3.3 Axis별 Optional Columns

| Axis Feature | Optional Columns |
| --- | --- |
| macro_policy | `delta_1m`, `delta_3m`, `delta_6m`, `release_source` |
| price_volatility | `outlier_flag`, `drawdown_*`, `range_*` |
| flow_structure | `volume_zscore_20d`, `obv_*`, `breadth_proxy(iwm_spy_ratio)` |
| sentiment | v0: `iwm_spy_vol_spread`, `intraday_range` / v1+: `vix_level`, `vix_term_structure_*` |

### 3.4 가용성 명시
- `macro_policy`, `price_volatility`: v0 필수 입력으로 사용 가능
- `flow_structure`: v0는 부분 수집 상태 허용, 누락 시 `UNKNOWN` 허용
- `sentiment`: v0는 proxy 기반만 사용, v1+에서만 VIX 옵션 활성화 가능

## 4. Horizon Engine Dependency Matrix

### 4.1 Axis × Horizon 매핑

| Axis \ Horizon | long_phase | mid_regime | short_signal |
| --- | --- | --- | --- |
| macro_policy | REQUIRED - 장기 국면 해석의 핵심 거시 근거 | OPTIONAL - 중기 레짐 보강 신호 | NOT_USED - 단기 스트레스 해석 직접 근거 아님 |
| price_volatility | OPTIONAL - 장기 해석 보조 축 | REQUIRED - 중기 위험 상태의 핵심 가격 근거 | REQUIRED - 단기 변동 상태의 핵심 입력 |
| flow_structure | OPTIONAL - 장기에서는 보조 관측 | OPTIONAL - 중기 레짐 확인 보강 | REQUIRED - 단기 수급/구조 신호 근거 |
| sentiment(v0 proxy / v1+ VIX) | NOT_USED - 장기 해석 직접 입력 아님 | OPTIONAL - 중기 심리 보강 축 | REQUIRED - 단기 신호의 핵심 심리 입력 |

### 4.2 버전별 활성 셀

| Axis \ Horizon | long_phase | mid_regime | short_signal |
| --- | --- | --- | --- |
| macro_policy | v0 ✅ / v1+ ✅ | v0 ✅(옵션) / v1+ ✅(옵션) | v0 ❌ / v1+ ❌ |
| price_volatility | v0 ✅(옵션) / v1+ ✅(옵션) | v0 ✅ / v1+ ✅ | v0 ✅ / v1+ ✅ |
| flow_structure | v0 ⏳(부분) / v1+ ✅ | v0 ⏳(부분) / v1+ ✅ | v0 ⏳(부분) / v1+ ✅ |
| sentiment | v0 ❌ / v1+ ❌ | v0 ✅(proxy 옵션) / v1+ ✅(proxy+VIX 옵션) | v0 ✅(proxy) / v1+ ✅(proxy+VIX 옵션) |

표기:
- ✅: 활성/사용 가능
- ⏳: 부분 가용(coverage 의존)
- ❌: 사용하지 않음

## 5. Data Freshness / Coverage 규칙
- Axis feature 결측 시 해당 Horizon 출력 상태는 `UNKNOWN` 허용
- 출력 스키마는 결측 여부와 무관하게 유지(fail-open)
- 품질 표현 필드(권장):
  - `coverage` (FLOAT)
  - `is_stale` (BOOLEAN)
  - `data_quality_flags` (ARRAY<TEXT>)
- partial coverage에서는 REQUIRED 축 결측 여부를 `data_quality_flags`로 명시
- v0에서 sentiment는 proxy만 기준으로 평가하고, VIX 결측은 결함으로 처리하지 않는다

## 6. Invariants
- Horizon engines MUST NOT compute raw features directly; only consume `axis_features_*` outputs.
- Axis feature 산출물은 read-only이며 Gold 입력을 변경하지 않는다.
- 의존성 매트릭스에 없는 Axis×Horizon 조합 사용 금지(추가 시 문서 버전 업 필요).
- 삭제된 과거 실행 단계 계열 필드/개념은 본 계약에 포함하지 않는다.
- v0에서 VIX dependency는 `NOT_USED` 고정이며, v1+에서만 옵션으로 다룬다.

## 7. DoD
- 문서 내 Source/Grain/Key/Columns 표가 상호 모순 없이 일치한다.
- Axis와 Horizon의 역할 구분이 문서 내 일관되게 유지된다.
- 참조 문서 링크가 유효하며 상위 계약과 충돌하지 않는다.
- v0 제약(신규 ingest 없음, proxy 기반 sentiment)이 명시되어 있다.
- Dependency matrix에 REQUIRED/OPTIONAL/NOT_USED 및 버전별 활성 상태가 모두 기재되어 있다.

---

## Change History
| Date | Summary | References |
| --- | --- | --- |
| 2026-02-13 | 파일명 버전 제거 및 문서 표준 블록(Document Status/Capability Matrix) 적용 | docs/changelog.md |
