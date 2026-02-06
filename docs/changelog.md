# Changelog

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