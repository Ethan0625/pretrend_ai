# Changelog

## v2026.02.13 — Strategy Engine v0 구현 반영 및 문서 동기화

### 변경 요약
- Strategy Engine 명칭 기준을 확정하고, WHAT/EXPOSURE/SELL 3-경계 출력 + `decision_date` snapshot 저장 원칙을 SOT로 고정
- Gold Macro/EOD snapshot 기반 Strategy Engine v0(7단계 파이프라인) 구현 현황을 문서에 반영
- 테스트 결과(194 passed, 1 skipped) 및 실데이터 검증 요약(GFC 구간 포함)을 운영 문서에 반영
- (Reserved) Stock Extension Port 및 Text/LLM Integration Port를 v1+ 확장 포트로 유지

---

## v2026.02.12 — EOD Observability Contract 문서화 및 문서 동기화

### 변경 요약
- PR#1~PR#3 코드 구현을 기준으로 EOD Observability SOT, Bronze/Silver 라벨 계약, Gold EOD Fact Mart를 파이프라인에 반영
- EOD E2E Runner(`eod_job.py`)와 Airflow Gold task(`run_eod_gold_features_task`)를 통합
- EOD 관측용 ETF 세트(Always-on Observability Set)와 분류/라벨 계약을 신규 문서로 고정
- `architecture.md`에 Observability Set 개념(Always-on vs Universe-driven)과 계약 링크를 추가
- `data_requirements.md` EOD 요구사항에 Observability 분류 컬럼 계약(`asset_group`, `asset_name`, `asset_subtype`)을 반영

---

### 1) EOD Observability Contract v1 구현 (PR#1)
- `src/pretrend/pipeline/config/eod_observability.py` 신규 추가
  - SOT 상수: `OBSERVABILITY_SET_V1`, `OBSERVABILITY_SYMBOLS_V1`, `LABEL_BY_SYMBOL_V1`
  - `asset_group` ENUM 5종: `INDEX`, `COUNTRY`, `COMMODITY`, `BOND`, `SECTOR`
  - import 시 `validate_observability_set()` 자동 검증(중복/대문자/ENUM)
- `src/pretrend/pipeline/ingest/eod.py`
  - `EodIngestConfig.default_symbols`를 SOT 참조로 전환
  - `EodNormalizer`에서 미등록 심볼 `ValueError` 처리 및 `asset_group`/`asset_name`/`asset_subtype` 컬럼 확정
- `src/pretrend/pipeline/features/eod_features.py`
  - `build_eod_features()`에서 `asset_*` 라벨을 Silver로 pass-through
- `tests/pipeline/test_eod_observability_contract.py` 신규(9 tests)
  - OL1~OL5 계약 검증(커버리지/라벨/reject/pass-through/멱등 안정성)

---

### 2) 하드코딩 제거 및 SOT 참조 전환 (PR#2)
- `src/pretrend/pipeline/ingest/eod.py` docstring/CLI help를 `Observability SOT` 기준으로 정리
- `dags/eod_pipeline_dag.py` 주석을 `Observability SOT 32개 ETF` 기준으로 정리
- `src/pretrend/pipeline/features/eod_features.py` 내 하드코딩 심볼 예시 정리

---

### 3) Gold EOD Feature v1 Fact Mart 구현 (PR#3)
- `src/pretrend/pipeline/features/gold_eod_features.py` 신규
  - `GOLD_EOD_FEATURE_COLUMNS` 계약
  - `load_silver_eod_features()` 로더
  - `build_gold_eod_features()` Silver→Gold 변환(lineage/dedup)
  - `write_gold_eod_features()` 멱등 저장(symbol/year/month, atomic overwrite)
  - CLI 엔트리포인트: `python -m pretrend.pipeline.features.gold_eod_features`
- `src/pretrend/pipeline/eod_job.py` 신규
  - `EodJobConfig` / `EodJobRunner` / `EodJobResult`
  - Bronze→Silver→Gold 순차 실행 + 메타 로그(`data/meta/eod_job_log.parquet`)
- `dags/eod_pipeline_dag.py`
  - `run_eod_gold_features_task` 추가
  - 의존 체인 Bronze → Silver → Gold로 확장, DAG tag에 `gold` 추가
- `tests/pipeline/test_gold_eod_features.py` 신규(7 tests)
  - GE1~GE5 계약 검증(grain/columns/labels/lineage/idempotency)

---

### 4) 테스트 현황
- 전체 테스트: **71 passed, 1 skipped**

---

### 5) 신규 계약 문서 추가
- `docs/architecture/eod_observability_contract.md` 생성
- 포함 범위:
  - 용어 정의(Observability Set, 분류 컬럼, Always-on vs Universe-driven)
  - Scope / Non-Goals
  - 분류 체계(`INDEX`, `COUNTRY`, `COMMODITY`, `BOND`, `SECTOR`)
  - Base EOD Observability Set v1 전체 심볼 표
  - Bronze/Silver/Gold 라벨 전파 규칙 및 ENUM 계약
  - Universe read-only 소비 원칙 및 변경 관리(Versioning)

### 6) Architecture 문서 동기화
- `docs/architecture.md`에 EOD Observability Set 설명 단락 추가
- Always-on 센서 입력 목적, 라벨 고정 원칙, 계약 문서 링크 반영

---

### 7) Data Requirements 문서 동기화
- `docs/data_requirements.md`의 EOD 섹션에 `Always-on Observability ETFs v1` 항목 추가
- 필수 분류 컬럼 계약 및 Universe 그룹핑 사용 규칙을 명시

---

### 8) Risk-Control 전략 문서 구조 재정의 (4축 + Composer + Allocation v0)
- Design vs Contract 분리 원칙으로 전략 문서를 재구성
  - Design: `docs/strategy_architecture.md`
  - Contracts: `market_structure_long/mid/short/composer`, `universe`, `allocation_engine`
  - Inventory: `docs/market_structure_data_inventory.md`
- 전략 흐름을 `Layer -> Market Structure(4축) -> Composer -> Universe -> Allocation Engine -> Weekly Report`로 고정
- v0 원칙 반영:
  - 총 투자 비율(`invested_ratio`) 조절만 허용
  - `risk_gate` 기반 증가 차단
  - Universe 내부 가중치 조절 금지
- 심리 축 입력 정책 갱신:
  - v0: VIX 필수 아님, Risk Spread + Volatility proxy 기반 상태 전이
  - v1+: VIX 편입(직접 VIX vs term structure 범위 결정 필요)
- 구버전 문서 정리:
  - `docs/architecture/market_structure_v1_contract.md` 삭제
  - 레거시 전략 계약 문서 제거(현행 구조에서 비사용)

---

### 9) 전략 로드맵 문서 동기화
- `docs/milestones.md`에 Risk-Control 전략 로드맵(v0~v3) 추가
- 운영 주기 분리 명시:
  - Adjustment Cycle: 주 1회(화요일)
  - Portfolio Rebalance: 월 1회(마지막 주 금요일, 휴장 시 직전 영업일)

## v2026.02.11 — Gold Macro Feature v1 E2E 통합 구현

### 변경 요약
- Gold Layer v1을 설계 계약(`gold_design_contract.md`)에서 구현 완료 단계로 전환
- `macro_job.py` E2E 플로우에 Gold 단계 통합: Bronze → Silver → Gold 1회 실행 동기화
- Calendar Silver(`econ_events`, `fred_vintages`)를 소비하는 3-tier fallback cascade로 `release_date` 증거 구축
- PIT 불변식(`selected_release_date < trade_date`) 100% 충족 검증 완료

---

### 1) Gold Macro Feature v1 핵심 로직 (`gold_macro_features.py`)
- 기존 순수 함수(`build_gold_macro_features`, MF1-MF10 테스트 완료)에 통합 인프라 추가:
  - `load_silver_macro()`: Silver macro → `[indicator_id, date, value]` 로드
  - `build_release_calendar()`: 3-tier fallback cascade
    - Tier 1: `econ_events` (`release_date = release_date_utc`)
    - Tier 2: `fred_vintages` (`is_first_vintage=True`, `release_date = vintage_date`)
    - Tier 3: `assumed_t+1` (`release_date = observation_date + 1 day`)
  - `write_gold_macro_features()`: `trade_date` 기준 파티션, `tmp -> atomic rename` 멱등 저장

---

### 2) `macro_job.py` E2E 플로우 통합
- 변경 전:
  - `bronze_ingest -> bronze_vintages -> bronze_econ_events -> silver_features -> silver_calendar`
- 변경 후:
  - 위 플로우 + `gold_macro_features` 추가
- `MacroJobConfig.gold_root` 프로퍼티, `MacroJobResult.gold_macro_result` 필드, Meta log `gold_macro_row_count` 반영

---

### 3) Calendar Runner Silver 로더 추가 (`calendar/runner.py`)
- `load_silver_econ_events()`, `load_silver_fred_vintages()` 추가
- Gold가 Silver Calendar의 첫 번째 downstream 소비자

---

### 4) E2E 검증 결과 (`--start 2024-01-01 --end 2024-06-30`)
- Gold 출력: 650행 (5 지표 × 130 영업일), 6개 월별 파티션
- PIT 불변식 위반: 0건
- `release_source` 태깅:
  - `CPI_US_ALL_ITEMS_SA`, `CPI_US_CORE_SA`, `US_UNEMPLOYMENT_RATE` → `econ_events`
  - `US_FED_FUNDS_RATE`, `US_TREASURY_10Y_YIELD` → `fred_vintages`
- `is_assumption_based`: 전부 `False` (Calendar 증거 100% 커버)
- Gold 저장 경로:
  - `data/gold/macro/macro_features/year=YYYY/month=MM/gold_macro_features_YYYYMM.parquet`

---

### 5) 테스트 현황
- Gold MF1-MF10: 22개 패스 (`tests/pipeline/test_gold_macro_feature_v1.py`)
- Calendar ST1-ST11: 12개 패스 (`tests/pipeline/test_calendar.py`)
- 전체 34개 테스트 통과

---

### 6) zscore_12m v1.1 구현 (`gold_macro_features.py`)
- `_zscore_12m()` 헬퍼 함수 추가 (lines 194-217)
- 공식: `(selected_value - mean) / std` — 12-month rolling z-score
- Monthly 지표 (CPI, UNRATE, FEDFUNDS): window = 12 관측치
- Daily 지표 (DGS10): window = 252 관측치 (약 1년 영업일)
- Edge cases:
  - `selected_value` NULL/NaN → None
  - window 내 관측치 부족 → None
  - std == 0 또는 NaN → None
- `_select_and_compute()`에서 기존 `"zscore_12m": None` → `_zscore_12m()` 호출로 변경

---

### 7) zscore_12m 테스트 (MF10a-MF10e)
- 기존 `TestZscoreV1` (항상 NULL 검증) → `TestZscoreV1_1` (실제 계산 검증)으로 교체
- MF10a: zscore_12m 컬럼 존재 확인
- MF10b: 히스토리 부족 시 NULL (standard fixture: 7 CPI months < 12)
- MF10c: 충분한 히스토리 시 계산값 검증 (12 monthly values, expected = 5.5/sqrt(13))
- MF10d: selected_value=NULL → zscore=NULL
- MF10e: std=0 (모든 값 동일) → zscore=NULL
- 전체 테스트: 54 passed, 1 skipped (EOD integration)

---

### 8) Gold EOD Feature v1 E2E 통합 구현
- `gold_eod_features.py`에 CLI 엔트리포인트(`parse_args`, `main`)를 추가하여 모듈 단독 실행을 지원
  - `python -m pretrend.pipeline.features.gold_eod_features --start ... --end ...`
- `eod_job.py`를 추가하여 EOD Bronze → Silver → Gold를 1회 실행으로 동기화
  - 핵심 구성: `EodJobConfig`, `EodJobRunner`, `EodJobResult`
  - 메타 로그: `data/meta/eod_job_log.parquet`
- `eod_pipeline_dag.py`에 `run_eod_gold_features_task`를 추가하고 의존 체인을 Bronze → Silver → Gold로 확장
- Gold EOD 출력 계약:
  - Grain: `(symbol, trade_date)`
  - 저장 경로: `data/gold/eod/eod_features/symbol=XXX/year=YYYY/month=MM/gold_eod_features_YYYYMM.parquet`
  - 라벨(`asset_group`, `asset_name`, `asset_subtype`)은 Silver에서 carry-forward

---

### 향후 계획
- (완료) `zscore_12m` 구현 (v1.1)
- (완료) EOD Gold Layer 설계 및 구현
- Universe(U0~U3) 계산 로직 구현

## v2026.02.10 — Calendar Pipeline v1 구현 (Bronze + Silver)

### 변경 요약
- Calendar Pipeline v1을 설계 명세 단계에서 구현 완료 단계로 전환하여, `econ_events` / `fred_vintages` Bronze→Silver 파이프라인이 실제 동작하도록 반영
- FRED 기반 Calendar Bronze ingest를 추가하여 release 증거 수집 경로를 코드로 고정
- `macro_job.py` E2E 플로우에 `bronze_econ_events`와 `silver_calendar(econ_events + fred_vintages)` 단계를 통합
- Silver Calendar 스키마를 release evidence 중심으로 경량화(`actual_value`, `value` 제거)
- Calendar 테스트 12개(ST1~ST11 + ST3 variant)를 통해 스키마/멱등성/dedup/timezone 계약 검증 완료

---

### 1) Calendar Silver 구현 완료 (`econ_events` + `fred_vintages`)
- 구현 모듈:
  - `src/pretrend/pipeline/calendar/config.py`
  - `src/pretrend/pipeline/calendar/econ_events.py`
  - `src/pretrend/pipeline/calendar/fred_vintages.py`
  - `src/pretrend/pipeline/calendar/runner.py`
- `runner.py`는 Bronze loader(`load_bronze_econ_events`, `load_bronze_fred_vintages`)와 CLI(`--target econ_events|fred_vintages|all`)를 제공
- 저장 경로(파티션 overwrite):
  - Bronze: `data/bronze/calendar/{econ_events|fred_vintages}/year=YYYY/month=MM/*.parquet`
  - Silver: `data/silver/calendar/{econ_events|fred_vintages}/year=YYYY/month=MM/*.parquet`

---

### 2) Calendar Bronze ingest 추가 (FRED release/dates + vintage API)
- `src/pretrend/pipeline/ingest/macro.py` 확장:
  - `MacroFetcher.fetch_vintages()` 추가
    - FRED observations API(`realtime_start/end`) 기반 vintage 수집
    - observation 연도 × realtime 2년 이중 청크
    - rate limit 0.5s + 429 exponential backoff
  - `MacroFetcher.fetch_econ_events()` 추가
    - FRED release/dates API 기반 release 날짜 수집
    - `release_id=10`(CPI), `release_id=50`(Employment) 반영
    - `release_id=18`(H.15)은 제외(주간/일간 릴리즈, `fred_vintages` fallback으로 커버)
    - `release_date -> observation_date`는 전월 1일 매핑(월간 지표)
  - `VintageNormalizer` / `VintageWriter`, `EconEventsNormalizer` / `EconEventsWriter` 추가

---

### 3) `macro_job.py` E2E 플로우 통합
- 변경 전:
  - `bronze_ingest -> bronze_vintages -> silver_features -> silver_calendar(fred_vintages만)`
- 변경 후:
  - `bronze_ingest -> bronze_vintages -> bronze_econ_events -> silver_features -> silver_calendar(fred_vintages + econ_events)`
- 결과적으로 Macro Job 1회 실행으로 Calendar Bronze+Silver까지 동기화 가능

---

### 4) Silver Calendar 스키마 경량화
- `econ_events Silver`에서 `actual_value` 컬럼 제거
- `fred_vintages Silver`에서 `value` 컬럼 제거
- Calendar Silver는 값(value) 저장소가 아니라 Gold PIT용 `release_date` 증거 레이어로 역할 고정

---

### 5) 테스트 및 검증
- 테스트 파일: `tests/pipeline/test_calendar.py`
- 테스트 수: 12개 (ST1~ST11 + ST3 variant)
  - Schema invariant
  - Idempotency
  - Dedup
  - Timezone normalization
- 모든 테스트는 synthetic fixture 기반이며 외부 API 호출 없음
- 검증 실행 요약:
  - 단기 실행(`--start 2024-01-01 --end 2024-06-30`): Bronze 21행, Silver 18행(econ_events)
  - 전체 실행(`--start 2015-01-01 --end 2026-02-01`): `fred_vintages` Silver 28,412행

---

### 향후 계획
- (완료) Gold Layer v1에서 Calendar(`econ_events`, `fred_vintages`)를 소비하는 PIT-safe 결합 로직 구현
- Gold release source 태깅(`econ_events` / `fred_vintages` / `assumed_t_plus_1`)과 계약 테스트 연계 강화

## v2026.02.06 — Pipeline Idempotency 강화 및 Agent 운영 기준 확정

### 변경 요약
- Macro / EOD Silver 파이프라인의 **멱등성(idempotency) 검증 수준을 파티션 invariant 기준으로 상향**
- AI Agent(Codex) 도입 범위를 **tests/docs 전용 보조 도구**로 명확히 제한하고, 운영 규칙을 문서로 고정
- 현재 구현 범위와 문서 간 **정합성(Doc Sync) 완료**

---

### 1) Silver Layer 멱등성 검증 강화

#### Macro / EOD Silver 공통
- 기존:
  - 파일 존재 여부 또는 단일 파일 overwrite 여부 중심 검증
- 개선:
  - **파티션 단위 invariant 검증**
    - 재실행 시 파티션 내 row 수 증가 없음
    - 중복 artifact 생성 없음
    - overwrite 보장

#### 테스트 설계 원칙
- 구현 세부(파일명, 내부 로직)에 결합된 assert 제거
- 의미적 불변조건(invariant) 중심 테스트로 재설계
- 향후 저장 포맷/경로 변경에도 테스트 재사용 가능하도록 구성

---

### 2) 테스트 품질 및 결합도 개선
- 파티션 전체를 기준으로 검증하도록 테스트 구조 단순화
- parquet 파일 반복 로딩/순회 로직 제거
- 테스트가 “구현을 설명”하지 않고 “결과를 검증”하도록 역할 정리

---

### 3) Agent(Codex) 도입 운영 기준 확정

#### 도입 결론
- Codex는 **설계·판단·전략·실행 주체가 아님**
- 역할:
  - 테스트 코드 초안 생성
  - 문서 동기화
  - 반복 작업 보조

#### 통제 장치
- `AGENTS.md` 고정:
  - Scope 제한 (tests/docs 중심)
  - 작은 diff (1 task / ≤300 LOC 권장)
  - public API 변경 금지
  - 멱등성/파티션 overwrite 규칙 보존
  - 검증 커맨드 명시 필수
- 브랜치 전략:
  - `codex/<task>` 단위 작업
- Task Spec에 Scope / DoD 명시

#### 면접·대외 설명 기준
- “AI가 다 했다” ❌
- “AI 초안 → 사람이 리뷰·수정·승인 → 테스트/문서로 증명” ⭕
- Agent 사용 여부 및 역할 분리는 `agent_adoption_notes.md`에 명시

---

### 4) 문서 동기화 완료
- README
- operation_guide
- agent_adoption_notes

→ 현재 코드 구현 범위(Macro/EOD Bronze→Silver, 멱등성 정책, Agent 운영 기준)와 문서 내용이 일치하도록 정렬 완료

---

### 5) 현재 스코프 및 다음 단계

#### 완료 범위
- Macro Bronze → Silver 파이프라인
- EOD Bronze → Silver 파이프라인
- 파티션 overwrite 기반 멱등성 보장
- 운영 환경을 가정한 테스트/문서/Agent 통제 구조

#### 다음 목표 (Out of scope → Next)
- Gold Layer:
  - Macro Silver + EOD Silver 결합
  - as-of join 기반 Feature Mart 설계
- Universe(U1~U3) 계산 로직 구현 및 테스트


## v2026.01.14
- Macro Pipeline 운영 정책 정리
  - DAG 매일 트리거 + 직전월 1일~전일 롤링 재처리
  - Silver Macro Feature year/month overwrite 멱등성 명시
- Gold Layer 설계 준비를 위한 Macro/EOD 정합성 문서화

## v2025.12.05 - EOD Airflow Pipeline (Bronze → Silver) 통합 및 Silver Feature Layer 구축

### 변경 요약
- EOD Bronze/Silver를 하나의 Airflow DAG(`eod_pipeline_dag`)로 통합
- 미국장 기준 "마지막 완전 거래일" 기반 Bronze ingest 자동화
- EOD Silver Feature Layer(v1) 신규 구축 (수익률/MA/ATR/RSI 포함)
- Silver Writer 멱등성 적용 및 파티션 구조 확정
- Gold Layer 설계를 위한 준비 작업 완료

---

### 1) EOD Pipeline 통합 (Bronze → Silver)
- 기존 단일 Bronze DAG를 제거하고 Macro pipeline 구조와 동일하게 **Bronze→Silver 통합 DAG** 구성
- DAG: `eod_pipeline_dag`
  - Task 1: `run_eod_bronze_ingest`
    - yfinance 기반 SPY/QQQ/VOO ingest
    - 미국장 ET 기준 "마지막 완전 거래일" 계산하여 하루 구간만 ingest
    - Bronze 저장 구조 유지:
      ```
      data/bronze/eod/daily_prices/
        source=YF/theme=GENERIC/symbol=SPY/trade_date=YYYY-MM-DD/eod.parquet
      ```
  - Task 2: `run_eod_silver_features`
    - Bronze 결과(XCom) 기반 동일 날짜/심볼로 Silver 생성
    - EOD Silver Writer는 (symbol/year/month) 파티션으로 멱등성 저장

---

### 2) EOD Silver Feature Layer 구축
- 신규 파일: `src/pretrend/pipeline/features/eod_features.py`
- Feature Set(v1):
  - **수익률:** ret_1d / log_ret_1d / ret_5d / ret_20d
  - **변동성:** vol_20d / vol_60d
  - **이동평균:** ma_5 / ma_20 / ma_60 / ma_120 / ma_ratio_5_20
  - **ATR & TR:** atr_14
  - **RSI:** rsi_14 (gain/loss SMA 기반)
  - **Volume 특성:** volume_zscore_20d
  - **Micro-structure:** gap_open, intraday_range
  - **Data Quality Flags:** is_trading_day, is_missing_imputed, is_outlier, is_partial_day
- Feature 계산 방식은 symbol 단위 groupby에서 shift/rolling 기반으로 안정화

---

### 3) EOD Silver 저장 구조 표준화
- 저장 경로: data/silver/eod/eod_features/symbol=SPY/year=2024/month=12/eod_features_202412.parquet
- 멱등성 전략: `_tmp_run={run_id}` 임시 디렉토리 생성
- 파티션 단위 atomic overwrite

---

### 4) Gold Layer 준비 단계 완료
- Gold 설계를 위해 필요한 전제조건 모두 충족:
- Macro Silver 완성
- EOD Silver v1 완성
- Airflow 기반 Bronze→Silver 자동화 환경 구축

### 향후계획
- Macro Silver + EOD Silver as-of join 구조 설계
- Gold Feature 스키마 정의
- Gold Pipeline DAG 구성(`gold_pipeline_dag`)
- 이후 NLP Bronze/Silver 추가(뉴스/FOMC/경제 리포트)
---

## v2025.12.03 - Macro Airflow Pipeline (Bronze → Silver) E2E 통합

### 변경 요약
- Macro Bronze/Silver 파이프라인을 Airflow DAG(`macro_pipeline_dag`)로 통합
- Airflow 전용 환경(`airflow-pretrend`)에서 MacroJob E2E (Bronze ingest → Silver features → Meta log) 자동 실행 성공
- 운영을 위한 환경변수 설계(`.env.airflow`) 및 개발용 런처 스크립트(`run_airflow_dev.sh`) 도입

### Airflow 환경 구성
- 별도 conda env: `airflow-pretrend`
- `AIRFLOW_HOME=/home/redtable/Desktop/ethan/pretrend/airflow_pretrend`
- `DAGS_FOLDER`를 `pretrend_ai/dags`로 지정 (`AIRFLOW__CORE__DAGS_FOLDER`)
- `run_airflow_dev.sh`에서:
  - `PROJECT_ROOT` 기반 공통 경로 설정
  - `.env.airflow`를 `set -a; source .env.airflow; set +a` 패턴으로 로드하여 환경변수 일괄 export
  - `webserver`, `scheduler`, `init-db`를 서브커맨드 형태로 실행 가능하도록 구성

### 환경변수 / 시크릿 설계
- `.env.airflow`에 운영에 필요한 핵심 변수만 정의
  - `FRED_API_KEY` : FRED 연동용 API 키
  - `PRETREND_DATA_ROOT` : `/home/redtable/Desktop/ethan/pretrend/pretrend_ai/data`
- 모든 시크릿/경로는 Git에 커밋하지 않고 `.env.airflow` + 런처 스크립트 구조로 관리

### MacroJob Airflow 통합
- DAG: `macro_pipeline_dag`
  - Task: `run_macro_job` (PythonDecoratedOperator 기반)
  - 내부에서 `MacroJobRunner.from_env()` 호출
- Airflow 실행 시 E2E 플로우:
  1. Bronze ingest
     - MacroFetcher → MacroNormalizer → MacroWriter
     - FRED에서 FEDFUNDS, 10Y YIELD 등 거시 지표 수집
     - 절대경로 기반 저장:
       - `data/bronze/macro/econ_indicators/year=YYYY/month=MM/{indicator_id}_YYYYMM.parquet`
  2. Silver macro features
     - Bronze 파티션 로딩 후 feature 계산
     - `data/silver/macro/macro_features/year=YYYY/month=MM/macro_features_YYYYMM.parquet`
  3. Meta log
     - `data/meta/macro_job_log.parquet`에 run_id, 기간, row count 등 실행 이력 기록

### 기술 이슈 해결 내역
- Airflow 태스크 내에서 `FRED_API_KEY` 미설정 오류 발생 → `.env.airflow` + `run_airflow_dev.sh`로 해결
- Parquet 저장 시 `pyarrow` 미설치로 인한 ImportError 발생 → `airflow-pretrend` 환경에 `pyarrow` 추가 설치
- `PRETREND_DATA_ROOT`를 기준으로 Bronze/Silver/Meta 경로를 절대경로로 통일 → CLI와 Airflow 간 경로 일관성 확보

### 향후 계획 (Macro 관련)
- `macro_pipeline_dag`의 `schedule_interval`을 매일 1회, 한국 시간 기준 오전(예: 09:00 KST)으로 설정하여 EOD Macro 자동 수집
- pandas `groupby.apply` FutureWarning 제거를 위한 Silver Feature 코드 리팩토링
- Macro DAG 모니터링 및 실패 알림(Slack/Email) 연동을 MLOps 단계에서 추가
---

## v2025.12.02 - FRED macro CPI ingest + parquet writer (bronze)

### 구조
  - IngestContext + BaseFetcher / BaseNormalizer / BaseWriter 공통 인터페이스 확립
  - MacroFetcher → MacroNormalizer → MacroWriter E2E 플로우 정상 동작

### FRED 연동
  - FRED API Key 환경변수로 연동 (FRED_API_KEY)
  - CPIAUCSL 기준으로 fetch/normalize/write 전부 검증 완료

### 저장 스키마
  - Bronze 스키마: indicator_id, date, value, unit, source, run_id, ingestion_ts
  - 디렉토리/파일 구조: data/bronze/macro/econ_indicators/year=YYYY/month=MM/{indicator_id}_YYYYMM.parquet

### 멱등성
  - 기준 키: (indicator_id, date)
  - 같은 파라미터로 재실행 시 파일 덮어쓰기 → 비즈니스 데이터 상태는 동일
  - run_id, ingestion_ts는 실행 이력(lineage)용 메타데이터

### Multi-indicator 확장 준비
  - FredSeriesSpec, FredMacroConfig 설계 완료
  - from_env_with_defaults()에서 CPI, Core CPI, UNRATE, FEDFUNDS, DGS10까지 한 번에 수집 가능
  - MacroFetcher는 series_list 기반 multi-series ingest 구조로 설계됨
---

## v2025.11.28

### 변경 요약
- Universe 설계를 "전 종목 기반"에서 "거시→테마→종목(U0~U3)" 구조로 전면 개편
- 한국 주식 종목은 Universe 대상에서 제외하고, 글로벌/미국 시장 중심 구조로 전환
- EOD 수집 대상은 전체 종목이 아니라 **U3 최종 Universe에 포함된 종목만**으로 한정

### 신규 문서
- `docs/universe_design.md`
  - U0: Macro Signal Detector (거시 신호 감지 및 영향력 수치화)
  - U1: Theme Prioritization (각광받을 테마 스코어링)
  - U2: Theme Universe Builder (테마 기반 주요 종목 1차 필터링)
  - U3: Growth & Flow Candidates (성장성 + 수급 기반 최종 Universe)
  - Universe와 EOD Ingest 연계 구조 정의

- `docs/data_requirements.md`
  - Macro / Theme / Stock / EOD별 필수 데이터 항목 정의
  - MVP 단계에서 수집해야 할 최소 데이터 셋(Macro 4종, Theme 3종, Stock 3종, EOD OHLCV) 명시
  - 주요 데이터 소스(FRED, Yahoo Finance, FMP 등) 개략 정리

### 설계 방향 결정 사항
- 한국 주식 종목은 Universe에서 제외하고, 미국/글로벌 종목을 기반으로 전략 설계
- 전 종목 EOD 수집은 스코프에서 제외
- Universe는 "신호 → 테마 → 종목"의 탑다운 방식으로 생성하고,
  U0~U3 각 단계의 역할과 필요 데이터 정의를 완료
