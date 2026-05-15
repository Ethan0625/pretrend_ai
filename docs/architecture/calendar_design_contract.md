# Calendar Pipeline v1 — Design Contract (문서 전용)

Markers: architecture, contract
Status: active

> 🟢 **Infrastructure (공유) — 두 트랙 공통 자산**
>
> Calendar evidence는 Bronze/Silver/Gold 레이어의 PIT 정합성을 보장하는 Infrastructure 자산이며, Observability Track / Personal Track 양쪽이 read-only로 소비합니다.
> 참조: [`track_separation.md`](./track_separation.md)

This document is the SOT for: Calendar evidence tables (`calendar.econ_events`, `calendar.fred_vintages`) used by Gold Layer v1 release-date derivation.

## 1) 개요 및 상태
- 목적: Gold Layer v1의 PIT 안전성을 보장하기 위한 **릴리즈 타이밍 증거** 캘린더를 정의한다.
- 상태: **구현 완료 (v2026.02.10)**. Calendar Pipeline v1 Bronze→Silver 파이프라인이 동작하며, Gold v1 언블록을 위한 릴리즈 증거 레이어를 제공한다.
- 범위: Bronze→Silver 파이프라인 패턴을 따르는 `calendar.econ_events`, `calendar.fred_vintages` 두 테이블의 계약을 고정한다.
- 용어 기준(본 문서): `release_ts_utc`(UTC timestamp), `release_date_utc`(UTC date), Gold 소비 키는 `release_date`, `trade_date`를 사용하며 정의/불변식은 `docs/architecture/gold_design_contract.md` §9를 따른다.

## 2) Scope & Non-Goals
### Scope
- 거시 지표 5종에 대한 릴리즈 캘린더 증거 제공 (PIT 안전성 확보 목적).
- 두 테이블:
  - `calendar.econ_events` — 실시간(일 단위 이상) 릴리즈 타임스탬프 기반 캘린더, 신뢰도 최고.
  - `calendar.fred_vintages` — FRED 빈티지(재무제표 버전) 기록, 날짜 단위, 신뢰도 중간.
### Non-Goals
| 제외 항목 | 사유 |
| --- | --- |
| 실시간/스트리밍 ingest | v1은 배치 전용 |
| 역사적 릴리즈 웹 스크래핑 | 법/컴플라이언스 검토 필요, 범위 밖 |
| econ_events ↔ fred_vintages 교차 검증 | Gold에서 우선순위 캐스케이드로 처리(§8b) |
| forward-fill / interpolation | Calendar는 사실 증거만 제공, 휴리스틱은 Gold 책임 |
| 비거시 지표(earnings/dividends 등) | v1 범위 밖, 향후 확장 대상 |
| Airflow DAG | v1은 runner/CLI만 가정 |
| Revision diff 계산 | 모든 빈티지를 저장하지만 delta 계산은 하지 않음 |

## 3) v1 Indicator 목록
| FRED series_id | indicator_id | Frequency |
| --- | --- | --- |
| CPIAUCSL | CPI_US_ALL_ITEMS_SA | Monthly |
| CPILFESL | CPI_US_CORE_SA | Monthly |
| UNRATE | US_UNEMPLOYMENT_RATE | Monthly |
| FEDFUNDS | US_FED_FUNDS_RATE | Monthly |
| DGS10 | US_TREASURY_10Y_YIELD | Daily |

### 3b) RELEASE_ID_TO_INDICATORS 매핑 (구현 기준)
| FRED release_id | indicator_id 매핑 | 비고 |
| --- | --- | --- |
| 10 | CPI_US_ALL_ITEMS_SA, CPI_US_CORE_SA | CPI release |
| 50 | US_UNEMPLOYMENT_RATE | Employment Situation |
| 18 | 제외 | H.15 주간/일간 릴리즈, `fred_vintages` fallback으로 커버 |

## 4) 데이터 스키마
### 4a. calendar.econ_events
- **Bronze**
  - Path: `data/bronze/calendar/econ_events/year=YYYY/month=MM/econ_events_YYYYMM.parquet`
  - Key: `(indicator_id, observation_date)` — 릴리즈 이벤트당 1행
  - Source: FRED `release/dates` API
  - Mapping rule: `release_date -> observation_date`는 월간 지표 기준 전월 1일로 매핑
  - Columns:
    - indicator_id TEXT
    - observation_date DATE
    - release_ts_utc TIMESTAMP (UTC, 없으면 NULL)
    - release_date_local DATE (소스 현지 기준, 없으면 NULL)
    - source TEXT (예: fred_release_dates)
    - run_id TEXT
    - ingestion_ts TIMESTAMP
- **Silver**
  - Path: `data/silver/calendar/econ_events/year=YYYY/month=MM/econ_events_YYYYMM.parquet`
  - Key: `(indicator_id, observation_date)` — 중복 제거 후 1행
  - 역할: release 증거만 제공(값 자체는 Silver macro에서 관리)
  - Columns:
    - indicator_id TEXT (유효성 검증)
    - observation_date DATE (정규화, §6)
    - release_ts_utc TIMESTAMP (UTC, NULL 허용)
    - release_date_utc DATE (= release_ts_utc.date() if not NULL; else release_date_local; else NULL)
    - source TEXT
    - has_timestamp BOOLEAN (release_ts_utc 존재 여부)
    - run_id_silver TEXT
    - ingestion_ts_silver TIMESTAMP
  - Dedup 규칙: 동일 `(indicator_id, observation_date)`가 여러 개면 **가장 이른 release_ts_utc** 보존. 모두 NULL이면 최초 ingested 보존.

### 4b. calendar.fred_vintages
- **Bronze**
  - Path: `data/bronze/calendar/fred_vintages/year=YYYY/month=MM/fred_vintages_YYYYMM.parquet`
  - Key: `(series_id, observation_date, vintage_date)`
  - Columns:
    - series_id TEXT
    - observation_date DATE
    - vintage_date DATE
    - value FLOAT
    - source TEXT ("fred_api")
    - run_id TEXT
    - ingestion_ts TIMESTAMP
- **Silver**
  - Path: `data/silver/calendar/fred_vintages/year=YYYY/month=MM/fred_vintages_YYYYMM.parquet`
  - Key: `(indicator_id, observation_date, vintage_date)`
  - 역할: release 증거만 제공(값 자체는 Silver macro에서 관리)
  - Columns:
    - indicator_id TEXT (series_id → indicator_id 매핑)
    - observation_date DATE
    - vintage_date DATE
    - is_first_vintage BOOLEAN (해당 관측치의 최초 vintage_date 여부)
    - source TEXT ("fred_api")
    - run_id_silver TEXT
    - ingestion_ts_silver TIMESTAMP
  - Dedup 규칙: 동일 `(series_id, observation_date, vintage_date)`가 여러 개면 **마지막 ingested (최신 run_id)** 유지. 매핑 후 적용.

## 5) Idempotent Write Strategy
- 파티션 스킴 (observation_date 기준):
  - econ_events Silver: `year=YYYY/month=MM/econ_events_YYYYMM.parquet`
  - fred_vintages Silver: `year=YYYY/month=MM/fred_vintages_YYYYMM.parquet`
- 프로토콜:
  1. `_tmp_run={run_id}/` 아래에 먼저 기록
  2. 파티션 파일을 최종 경로로 원자적 rename
  3. 동일 파티션 존재 시 전체 overwrite (append 금지)
  4. 성공 후 tmp 디렉터리 정리
- 불변식:
  - 파티션 단위 원자성 (all-or-nothing)
  - 무조건 교체(write-replace), append 없음
  - 동일 입력 재실행 시 결과 동일(run_id_silver, ingestion_ts_silver 제외)

## 6) Normalization Rules
- indicator_id
  - econ_events Bronze: 미리 정의된 5개 indicator_id만 허용. 기타는 거부·드롭.
  - fred_vintages Bronze: series_id → indicator_id 매핑(FredSeriesSpec). 미지정 시 거부.
- observation_date
  - Monthly 지표: 참조 월의 첫날 (예: 2024-12 CPI → 2024-12-01)
  - Daily 지표(DGS10): 실제 관측 일자 (예: 2025-01-15)
  - Silver macro의 date 컬럼 의미와 정확히 일치해야 함.
- Timezone (econ_events)
  - release_ts_utc는 반드시 UTC. 소스가 로컬이면 UTC로 변환.
  - release_date_local은 변환 없이 감사용으로 보존.
  - release_date_utc 파생:
    - release_ts_utc 존재 시: `release_ts_utc.date()`
    - 없고 release_date_local 존재 시: release_date_local (approx., has_timestamp=False)
    - 둘 다 없으면 NULL
- 타입/널 허용
  - indicator_id TEXT NOT NULL
  - observation_date DATE NOT NULL
  - release_ts_utc TIMESTAMP NULLABLE
  - release_date_utc DATE NULLABLE
  - vintage_date DATE NOT NULL (fred_vintages)
  - source TEXT NOT NULL
  - has_timestamp BOOLEAN NOT NULL (econ_events Silver)
  - is_first_vintage BOOLEAN NOT NULL (fred_vintages Silver)

## 7) Minimal Tests (테스트 계약, ST1–ST11 + ST3 variant)
- **ST1**: econ_events Silver 필수 컬럼/타입 검증
- **ST2**: fred_vintages Silver 필수 컬럼/타입 검증
- **ST3**: 미승인 indicator_id 거부 (알 수 없는 indicator 제외)
- **ST3 variant**: 미승인 series_id 거부 (fred_vintages)
- **ST4**: econ_events 파티션 overwrite (두 번 기록 시 두 번째 값만 남고 중복 없음)
- **ST5**: fred_vintages 파티션 overwrite (동일 입력 두 번 기록 → 동일 출력, 파티션 1파일 유지)
- **ST6**: econ_events dedup (동일 키 다수 시 가장 이른 release_ts_utc 선택)
- **ST7**: fred_vintages dedup (동일 삼중키 시 최신 run_id 보존)
- **ST8**: fred_vintages is_first_vintage 플래그 (가장 이른 vintage_date만 True)
- **ST9**: econ_events UTC 변환 (비UTC 입력 → UTC 변환, release_date_utc는 UTC 날짜)
- **ST10**: econ_events NULL timestamp + local date 처리 (release_ts_utc NULL, release_date_utc는 local date, has_timestamp=False)
- **ST11**: econ_events timestamp 모두 NULL 처리 (release_ts_utc/release_date_utc NULL, has_timestamp=False)

## 8) Gold Interface Contract
Gold PIT 불변식 연계: 본 절(§8a–§8d)은 `docs/architecture/gold_design_contract.md` §9 PIT Invariants를 만족하기 위한 Calendar→Gold 인터페이스 계약이다.

### 8a. Gold에서 release_date 산출
| Calendar 소스 | Gold의 release_date 계산 | release_source 태그 |
| --- | --- | --- |
| econ_events Silver, has_timestamp=True | release_date_utc (release_ts_utc 기반) | `econ_events` |
| econ_events Silver, has_timestamp=False | release_date_utc (release_date_local 기반, approximation) | `econ_events` |
| fred_vintages Silver, is_first_vintage=True | vintage_date | `fred_vintages` |
| 어떤 소스도 없을 때 | feature_date + 1 day 휴리스틱 | `assumed_t_plus_1` |

### 8b. Gold fallback 캐스케이드 (우선순위 고정)
1. econ_events Silver 조회 → 있으면 release_date_utc 사용.
2. 없으면 fred_vintages Silver (is_first_vintage=True) → vintage_date 사용.
3. 없으면 feature_date + 1 day, 태그 `assumed_t_plus_1`.
4. carry-forward 시 태그 `ffill`; 데이터 전무 시 NULL.

### 8c. Calendar가 Gold에 제공해야 할 보장
- indicator_id 값이 Silver macro와 완전 일치 (ST3 + 공유 상수).
- observation_date 의미가 Silver macro와 동일 (§6).
- `(indicator_id, observation_date)` 당 econ_events Silver 최대 1행 (ST6).
- is_first_vintage가 최초 vintage를 정확히 표시 (ST8).
- release_ts_utc는 UTC 또는 NULL만 허용, 애매한 타임존 없음 (ST9–ST11).

### 8d. Calendar의 비보장 사항
- 완전성 미보장: 모든 (indicator_id, observation_date)가 존재하지 않을 수 있음 → Gold가 `assumed_t_plus_1`로 처리.
- release_ts_utc 정확도 제한: 역사 데이터는 근사치일 수 있으며, source/태그로 신뢰도를 전달.
- 단일 진실원(SOT) 아님: econ_events와 fred_vintages가 불일치할 수 있으나 Calendar는 조정하지 않음; 우선순위 선택은 Gold 책임(§8b).
- 본 절의 비보장 사항은 Gold `release_date < trade_date` 불변식 자체를 완화하지 않으며, 해당 불변식은 `docs/architecture/gold_design_contract.md` §9를 따른다.

## 9) Calendar의 보장사항 / 비보장사항 요약
- 보장: 스키마·키·정규화 규칙·타임존 규칙·dedup 규칙·멱등 파티션 overwrite 준수.
- 비보장: 데이터 완전성, 타임스탬프 역사적 정확성, 소스 간 충돌 해소.

## 10) Implementation Prerequisites (TBD 포함)
| 항목 | 상태 | 비고 |
| --- | --- | --- |
| 공유 indicator_id 상수 | Exists | `macro_features.py` lines 19–23 |
| FredSeriesSpec 매핑 | Exists | `macro.py` from_env_with_defaults() |
| BaseFetcher/Normalizer/Writer | Exists | `pretrend.pipeline.ingest.base` |
| FRED vintage API 접근 | Requires FRED_API_KEY | `fred/series/observations` with realtime params |
| Econ events 데이터 소스 | Implemented | FRED `release/dates` API + `RELEASE_ID_TO_INDICATORS` 매핑 |
| 파일 위치(예정) | N/A | `src/pretrend/pipeline/calendar/*.py`, `tests/pipeline/test_calendar.py` |

---
- Calendar Pipeline v1은 **구현 완료된 계약 기반 파이프라인**이며, Gold는 본 계약의 인터페이스를 소비한다.
- Gold는 Calendar의 불완전/비조정 특성을 전제로 캐스케이드(§8b)로 우선순위를 해결한다.
