# Gold Layer v1 — Design Contract (문서 전용)

> 🟢 **Infrastructure (공유) — 두 트랙 공통 자산**
>
> Gold Layer v1 PIT join contract는 Bronze/Silver/Gold 데이터 파이프라인의 핵심 invariant이며, Observability Track / Personal Track 양쪽이 read-only로 소비합니다.
> 참조: [`track_separation.md`](./track_separation.md)

This document is the SOT for: Gold Layer v1 PIT join contract and release-date usage in Gold outputs.

## 1. 개요 (Overview & Status)
- Gold Layer v1은 Silver 출력물을 기반으로 한 **계약 문서**이며, Macro Feature v1 구현은 완료(v2026.02.11)되었고 확장 범위는 후속 구현 대상이다.
- Gold 구현은 Calendar pipeline(econ_events, fred_vintages) 인터페이스를 전제로 진행한다.
- 목적: 향후 구현·인터뷰 시 참조할 고정된 계약으로, 설계 변경을 의도하지 않는다.
- 용어 기준(본 문서): `release_date`(Gold 소비 기준 날짜), `trade_date`(소비/거래 기준 날짜). Calendar 원천 컬럼 `release_ts_utc`, `release_date_utc`는 `docs/architecture/calendar_design_contract.md` §8a–§8c 정의를 따른다.

### 1.1 용어 정의 (Glossary / Terminology)
본 절의 정의는 Gold Layer v1 전체(모든 섹션)에 공통 적용된다.

| Term | 한글 설명 |
| --- | --- |
| `indicator_id` | 거시 지표 식별자. Gold 계산의 최소 단위이며, 모든 선택·계산은 `indicator_id` 단위로 수행된다. |
| `observation_date` | 해당 지표가 설명하는 관측 대상 시점. Monthly 지표는 해당 월을 대표하는 period anchor 날짜, Daily 지표는 실제 관측 날짜. |
| `vintage_date` | 동일 `observation_date`에 대해 서로 다른 값이 공개된 버전 기준 날짜. |
| `release_ts_utc` | 데이터가 외부에 공개된 실제 UTC 시각 (Calendar 증거). |
| `release_date` | Gold Layer에서 해당 값을 사용할 수 있게 되는 기준 날짜. Calendar 기준 파생값. |
| `trade_date` | Gold feature가 소비되는 기준 날짜 (거래·의사결정 시점). |
| `run_id` | 파이프라인 실행 식별자, 메타 데이터. 의미적 동일성 판단에는 사용하지 않음. |
| `ingestion_ts` | 시스템이 데이터를 수집한 시각, 메타 데이터. 의미적 동일성 판단에는 사용하지 않음. |

### 1.2 용어 사용 원칙 (Gold 전역)
- 모든 선택/계산/파생은 `indicator_id` 단위로 수행한다.
- 선택 기준은 `release_date < trade_date`이며, `observation_date`는 선택 우선순위에 사용하지 않는다.
- `observation_date`는 선택된 값의 관측 대상 시점을 설명하는 용도로만 사용한다.
- `run_id`, `ingestion_ts`는 감사/라인리지 메타 데이터이며, 의미적 동일성 판단 기준이 아니다.
- Calendar 원천 컬럼(`release_ts_utc`, `release_date_utc`)에서 Gold `release_date`로의 매핑 규칙은 `docs/architecture/calendar_design_contract.md` §8a–§8c를 따른다.

## 2. Gold Layer의 역할과 범위
- 역할: Silver Macro/EOD Feature를 사용해 사전 계산된 Gold 신호/타깃을 제공한다.
- 범위: 데이터 가용성·PIT(Poin t-in-Time) 안전성·투명성을 보장하는 계약 정의에 한정한다. 구현, 스케줄링, DAG 설계는 본 문서 범위를 벗어난다.

## 3. Calendar Pipeline 의존성 (구현 차단 사유 명시)
- Gold v1은 Calendar pipeline( econ_events, fred_vintages )에서 제공하는 이벤트/발표 일정에 **의존**한다.
- Calendar 파이프라인은 구현 완료 상태(v2026.02.10)이며, Gold는 해당 인터페이스를 소비한다.
- Calendar는 `release_date` 가정값 검증·보정 및 PIT 조인을 위한 공식 타임라인을 제공한다.

## 4. Core Philosophy (release_date 철학)
- Gold의 모든 값은 `release_date` 시점에 **알 수 있었다고 가정되는 정보**만을 반영해야 한다.
- `release_date`는 가정(assumption)에 기반하며 실제 발표 시각의 그라운드 트루스가 아니다.
- 투명성/설명가능성: 각 값이 어떤 `release_date` 가정 아래 산출됐는지 명시하고, Silver 입력으로 추적 가능해야 한다.

## 5. Market Cutoff 규칙 (T+1)
- 기본 전제: 시장 반영 기준은 T+1 컷오프를 따른다.
- `release_date` 기준으로 다음 거래일부터 사용할 수 있다는 가정이며, 실거래 시각 검증은 Calendar가 준비된 후 수행한다.

## 6. Gold 데이터 모델 개요 (코드 없이 설명)
- 입력: Silver Macro Features, Silver EOD Features, 그리고 향후 Calendar 이벤트/빈티지 정보.
- 출력: `business key`(symbol 또는 indicator_id + date 등), `release_date`, `trade_date`(또는 대상 날짜), 파생 신호/타깃, 입력 파티션·라인리지, 감사용 메타데이터.
- 파티셔닝: Silver와 일관된 단위(예: symbol/year/month 또는 macro date 버킷)를 유지한다.

### 6.1 Transition Forecast Feature 확장 포트 (운영 기준)
- 전이예측 운영 지평은 거래일 기준 `5/10/20/60/120D`로 고정한다.
- Gold 저장본은 Strategy/Paper/Backtest가 공통 소비하는 단일 소스 역할을 수행한다.
- 지평별 출력은 `forecast_bias_hd`, `forecast_confidence_hd`, `transition_hazard_hd`, `transition_expected_hd` 형태를 권장한다.
- 결측은 nullable 허용하되, 소비 계층은 fail-open(`UNKNOWN/N/A`)을 유지한다.

## 7. PIT Join 규칙 (Plain English → 한국어)
- 조인은 항상 `release_date` 기준으로 수행하며, 소비 시점보다 이후의 정보는 사용할 수 없다.
- 인게스트 시각이나 관측 시각으로 조인하지 않는다(이는 감사 전용).
- 동일 지표/값에 여러 릴리즈가 있는 경우, 소비 측 `trade_date`보다 **엄격히 이전**의 `release_date` 버전을 선택한다.
- Calendar 데이터가 없을 때는 가정된 `release_date`를 사용하되, “assumption-based”로 명시한다.
- Calendar 연계 기준: `release_date` 산출/소스 우선순위/보장사항은 `docs/architecture/calendar_design_contract.md` §8a–§8c를 참조한다.

## 8. Evidence Columns와 감사 가능성(Auditability)
- Silver 입력 파티션/파일을 추적할 수 있는 라인리지 컬럼, 사용한 `release_date` 가정, 인게스트 시각 메타를 보존한다.
- 관측 시점과 가용 시점을 구분하기 위해 ingestion 메타와 `release_date`를 모두 기록한다.
- Calendar 검증 여부(assumption vs validated)를 식별할 플래그를 포함한다.
- 재실행 결정성: 동일 입력·가정으로 재실행 시 동일 결과를 산출해야 한다.

## 9. PIT Invariants (테스트 계약)
- `release_date`는 소비되는 `trade_date`보다 반드시 이른 시점이어야 한다: `release_date < trade_date`.
- 중복 릴리즈가 있을 경우 가장 늦은(가장 최근) `release_date`를 선택하되, 여전히 소비 시점 이전이어야 한다.
- Calendar 증거가 없는 경우 가정 기반임을 표시해야 하며, Calendar 인터페이스 기준으로 동일 로직 재현이 가능해야 한다.
- Calendar 인터페이스 컬럼(`release_ts_utc`, `release_date_utc`)에서 Gold `release_date`로의 매핑은 `docs/architecture/calendar_design_contract.md` §8a–§8c를 따른다.

## 10. Macro Feature v1 (상태 Feature 계약)
### 10.1 목적과 범위
- 본 섹션은 Gold Macro Feature v1의 상태(feature) 산출 계약만 정의한다.
- 예측/전략/점수화/시장 반응 결합은 범위 밖이며 Universe/Signal 책임이다.
- 혼합 주기(Monthly/Daily)는 `observation_date` 의미를 분리해 해석한다(§10.3).

### 10.2 Selection Criterion (indicator_id 당 trade_date 시점 1값 선택)
- Gold는 `indicator_id`와 `trade_date` 기준으로 사용 가능한 값 1개를 선택한다.
- 선택 조건은 `release_date < trade_date` 이다.
- 후보가 여러 개면 `release_date`가 가장 최근(최대)인 값을 선택한다(latest-as-of).
- 본 선택 규칙은 Gold PIT 불변식(§9)을 반드시 만족해야 한다.

### 10.3 시간 축 정의 (Monthly/Daily 혼합)
- `observation_date`:
  - Monthly indicator: 해당 월을 대표하는 period anchor date.
  - Daily indicator: 실제 관측 날짜.
- `trade_date`: Gold 소비/거래 기준 날짜.
- `release_date`: 해당 값이 Gold에서 사용 가능해진 날짜(캘린더 인터페이스에서 제공된 날짜).

### 10.4 Output Schema (Macro Feature v1)
- Grain/Key: `(indicator_id, trade_date)`
- Required columns:
  - `indicator_id` TEXT NOT NULL
  - `trade_date` DATE NOT NULL
  - `selected_observation_date` DATE NULLABLE
  - `selected_value` FLOAT NULLABLE  # level
  - `selected_release_date` DATE NULLABLE
  - `delta_1m` FLOAT NULLABLE
  - `delta_3m` FLOAT NULLABLE
  - `delta_6m` FLOAT NULLABLE
  - `direction` TEXT NULLABLE  # up/down/flat
  - `regime` TEXT NULLABLE  # tightening/easing/neutral
  - `zscore_12m` FLOAT NULLABLE  # v1에서는 계산 제외, 컬럼 존재 시 NULL 허용 (v1.1 이관)
  - `release_source` TEXT NULLABLE
  - `is_assumption_based` BOOLEAN NOT NULL

### 10.5 Feature 정의 및 계산 규칙
- base
  - `level = selected_value`
- trend
  - `delta_1m`, `delta_3m`, `delta_6m`는 모두 동일 `indicator_id` 내 시계열에서 계산한다.
  - Monthly indicator: month offset 기반으로 계산한다(1m/3m/6m).
  - Daily indicator: trading day 캘린더 계산 없이 row-offset 기반 근사로 계산한다.
    - `delta_1m = value - value.shift(21)`
    - `delta_3m = value - value.shift(63)`
    - `delta_6m = value - value.shift(126)`
  - offset 값이 없거나 결측이면 해당 delta는 NULL 허용.
  - Monthly/Daily 혼합 시에도 다른 indicator와 결합하지 않는다.
- direction
  - 값 집합은 `up`, `down`, `flat`으로 고정한다.
  - 판정 규칙: 정확히 0이면 `flat`, 양수면 `up`, 음수면 `down`.
- regime
  - 값 집합은 `tightening`, `easing`, `neutral`으로 고정한다.
  - rule-based이며 단일 지표 내에서만 판정한다.
  - 판정 규칙:
    - `tightening`: `delta_3m > 0 AND delta_6m > 0`
    - `easing`: `delta_3m < 0 AND delta_6m < 0`
    - `neutral`: 그 외
- optional
  - `zscore_12m`은 Gold v1에서 계산하지 않는다.
  - 스키마에 컬럼이 존재하는 경우 NULL 허용으로 유지한다(v1.1 이관).

### 10.6 PIT Rules (Macro Feature v1)
- `selected_release_date < trade_date`를 만족하지 못하면 해당 후보는 선택 불가다.
- 선택 가능한 후보 중 `selected_release_date`가 가장 최근인 값만 채택한다.
- `observation_date`는 선택 우선순위 기준이 아니라, 선택된 값의 관측 기준일로 기록한다.
- Calendar 인터페이스 연동 규칙은 `docs/architecture/calendar_design_contract.md` §8a–§8c를 따른다.

### 10.7 Edge Cases (NULL, Missing Calendar)
- NULL value
  - `selected_value`가 NULL이면 `level`, `delta_*`, `direction`, `regime`, `zscore_12m`은 NULL 허용.
- 과거값 부족
  - `delta_1m/3m/6m` 계산에 필요한 offset 관측치가 부족하거나 결측이면 해당 delta는 NULL.
  - `zscore_12m`은 v1 계산 대상이 아니므로 NULL 허용.
- Missing Calendar
  - Gold v1은 Calendar에서 제공되는 `release_date` 기반 selection을 전제로 한다.
  - Calendar 증거가 없는 경우 본 섹션에서 별도 fallback을 정의하지 않는다.
  - 기존 Gold assumption-based 정책(§7) 및 `docs/architecture/calendar_design_contract.md` §8a–§8c를 따른다.

### 10.8 DoD (테스트 계약)
- **MF1**: `(indicator_id, trade_date)` 당 최대 1행 보장.
- **MF2**: 모든 선택 행은 `selected_release_date < trade_date`를 만족.
- **MF3**: 복수 후보 존재 시 `selected_release_date` 최대값 행이 선택됨.
- **MF4**: Monthly indicator의 `selected_observation_date`는 period anchor 의미를 유지.
- **MF5**: Daily indicator의 `selected_observation_date`는 실제 관측 날짜 의미를 유지.
- **MF6**: `direction` 값은 `up/down/flat` 외 값 금지.
- **MF7**: `regime` 값은 `tightening/easing/neutral` 외 값 금지.
- **MF8**: 단일 지표 내 계산 불변식: 다른 indicator 데이터와 결합 계산 금지.
- **MF9**: 과거값 부족/NULL 입력 시 파생 컬럼 NULL 처리 일관성 유지.
- **MF10**: `zscore_12m`은 v1.1에서 구현 완료. Monthly window=12, Daily window=252. NULL 조건: value NULL, 히스토리 부족, std=0.

## 11. Gold v1의 Non-Goals
- EOD 결합 Gold 및 전략/유니버스 연계 계산 로직 구현은 본 범위에 포함하지 않는다.
- 실제 발표 시각의 완전한 정확성을 보장하지 않는다(`release_date`는 가정).
- 전략/유니버스/LLM 기능 확장이나 새로운 설계 제안은 범위 밖이다.

## 12. 구현 선행 조건 (Implementation Prerequisites)
- Calendar pipeline(econ_events, fred_vintages) 인터페이스가 유지되어 `release_date` 가정을 검증할 수 있어야 한다.
- Macro Feature v1 이후 확장 구현(EOD 결합/Universe 연계)은 동일 PIT 계약을 준수해야 한다.
- 본 문서는 구현/검증 시 기준 계약(SOT)으로 사용한다.
