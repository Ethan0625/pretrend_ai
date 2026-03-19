# 📄 ETL — Data Source Ingest Layer

### Universe-Stock(U0~U3)와 EOD 파이프라인을 위한 기초 데이터 Ingest 구조

**Version:** 2025.12\
**Milestone:** M1 – Data Source Ingest Layer 구축\
**Source Modules:** `pretrend.pipeline.ingest.*`

---

# 1. 개요

본 문서는 Pre-Trend Value 기반 자동매매 시스템의
**데이터 소스 인입 레이어(Data Source Ingest Layer)** 설계를 정의한다.

이 레이어는 Universe-Stock(U0~U3) 생성 및 EOD 파이프라인의 기반이 되는
다음 세 가지 핵심 데이터군을 수집·정규화·저장하는 역할을 수행한다:

* **Macro 데이터** (금리, CPI, PMI, 뉴스 헤드라인 등)
* **Theme 데이터** (ETF 목록, 구성 종목, 성과/모멘텀 등)
* **Stock Fundamentals** (종목 기본 정보, 재무지표)
* EOD는 본 문서에서는 **인터페이스만 정의**하며, 실제 구현은 EOD 파이프라인 문서에서 수행한다.

이 레이어는 기존 문서에서 “Step 0”라고 표현된 개념을 포괄하지만,
코드 구조는 `pretrend.pipeline.ingest.*` 형태로 정리한다.

---

# 2. 아키텍처

## 2.1 전체 구조

```mermaid
flowchart TD
    subgraph Sources
        FRED[FRED API\n(Fed Funds, CPI, PMI)]
        NEWS[News API / RSS]
        ETF[ETF Data\n(Yahoo / FMP / ETFdb)]
        FUND[FMP / Finnhub\n(Fundamentals)]
        EODAPI[EOD API (Yahoo)\n(Interface Only)]
    end

    subgraph IngestLayer[Data Source Ingest Layer\npretrend.pipeline.ingest.*]
        ORCH[orchestrator.py\n(ingest orchestrator)]

        subgraph Macro
            M_F[MacroFetcher]
            M_N[MacroNormalizer]
            M_W[MacroWriter]
        end

        subgraph Theme
            T_F[ThemeFetcher]
            T_N[ThemeNormalizer]
            T_W[ThemeWriter]
        end

        subgraph Stock
            S_F[StockFetcher]
            S_N[StockNormalizer]
            S_W[StockWriter]
        end

        subgraph EOD_Skel[EOD Skeleton]
            E_CFG[EODConfig Interface]
        end
    end

    subgraph Storage[Data Lake (Bronze Layer)]
        MACRO[(macro/*)]
        THEME[(theme/*)]
        STOCK[(stock/*)]
    end

    FRED --> M_F --> M_N --> M_W --> MACRO
    NEWS --> M_F
    ETF --> T_F --> T_N --> T_W --> THEME
    FUND --> S_F --> S_N --> S_W --> STOCK

    ORCH --> M_F
    ORCH --> T_F
    ORCH --> S_F
    EODAPI --> E_CFG
```

---

# 3. 저장 구조

## 3.1 디렉토리 구조 (Bronze Layer)

```text
data/
└── bronze/
    ├── macro/
    │   ├── econ_indicators/
    │   │   └── year=YYYY/month=MM/*.parquet
    │   └── news_headlines/
    │       └── date=YYYY-MM-DD/*.parquet
    ├── theme/
    │   ├── etf_master/
    │   ├── etf_holdings/
    │   └── etf_performance/
    └── stock/
        ├── stock_master/
        └── fundamentals/

meta/
└── ingest_log.parquet
```

→ 기존 문서의 `/bronze/step0/...` 구조는 모두 제거됨.
→ 코드 구조와 동일하게 `macro/`, `theme/`, `stock/` 3도메인 중심으로 단순화.

---

# 4. 파이프라인 구성요소

## 4.1 공통 컴포넌트 (`ingest/base.py`)

모든 ingest job은 다음 3단계를 공통으로 갖는다:

1. **Fetcher**: 외부 API/CSV에서 raw data 수집
2. **Normalizer**: 스키마 통일, 컬럼 정규화, 지표 파생
3. **Writer**: 파티션 결정 → tmp 저장 → overwrite → ingest_log 기록

코드 구조:

```
pretrend.pipeline.ingest.base
 ├── BaseFetcher
 ├── BaseNormalizer
 ├── BaseWriter
 └── IngestContext
```

---

# 5. 멱등성 전략 (Idempotency)

본 ingest 레이어는 **파티션 단위 overwrite 전략**을 사용한다.

1. 실행마다 `run_id` 생성
2. 대상 기간(예: 2025-12)의 파티션 계산
3. `/tmp/pretrend/bronze/{domain}/{dataset}/{run_id}/` 에 임시 저장
4. 기존 파티션 삭제 후 tmp를 최종 위치로 atomic move
5. `meta/ingest_log.parquet`에 로그 append

이 방식은:

* 중복 적재를 방지하고
* 동일 기간을 재수집해도 항상 동일한 최종 결과를 보장하며
* Airflow 도입 시 Task-level 멱등성 관리와도 자연스럽게 연결된다.

---

# 6. 도메인별 Ingest 정의

## 6.1 Macro Ingest (`ingest/macro.py`)

### 입력

* FRED: CPI, PPI, PMI, Fed Funds, 고용지표 등
* News API/RSS: 거시 뉴스 헤드라인

### 출력 테이블

* macro/econ_indicators
* macro/news_headlines

### 사용 흐름

```bash
python -m pretrend.pipeline.ingest.orchestrator --job macro --start 2020-01-01 --end 2025-12-01
```

---

## 6.2 Theme Ingest (`ingest/theme.py`)

### 입력

* ETF 리스트 (SOXX, SMH, AIQ 등)
* ETF 구성 종목/가중치
* ETF 수익률, 모멘텀 지표

### 출력 테이블

* theme/etf_master
* theme/etf_holdings
* theme/etf_performance

---

## 6.3 Stock Fundamentals Ingest (`ingest/stock.py`)

### 입력

* FMP/Finnhub API (종목 기본정보 + 재무지표)

### 출력 테이블

* stock/stock_master
* stock/fundamentals

---

## 6.4 EOD Skeleton (`ingest/eod_interface.py`)

EOD는 본 ingest 레이어에서 실제 수집하지 않고,
EOD 전용 파이프라인 구축 시 연결 가능한 **Config + Interface만 제공**한다.

---

# 7. Orchestrator

## 7.1 위치

`pretrend.pipeline.ingest.orchestrator`

## 7.2 역할

* job 선택 (macro/theme/stock)
* 날짜 기반 파라미터 전달
* run_xxx_ingest 호출

## 7.3 실행 예시

```bash
python -m pretrend.pipeline.ingest.orchestrator --job macro
python -m pretrend.pipeline.ingest.orchestrator --job theme
python -m pretrend.pipeline.ingest.orchestrator --job stock --start 2024-01-01 --end 2024-12-31
```

---

# 8. 테스트 구성

### 테스트 파일 구조

```
tests/pipeline/
 ├── test_ingest_macro.py
 ├── test_ingest_theme.py
 └── test_ingest_stock.py
```

### 테스트 범위

* Fetcher가 dataset dict 반환하는지
* Normalizer가 run_id/ingestion_ts 추가하는지
* Writer가 tmp → final 이동 로직을 실행하는지
  (초기에는 mock 기반으로 테스트)

---

# 9. 텍스트 데이터 소스 (Text Ingest)

## 9.1 개요
텍스트 데이터는 Strategy Engine의 **보조 feature** 생성 목적으로 수집된다.
텍스트 결측 시에도 Strategy Engine 핵심 로직은 계속 동작한다 (fail-open 원칙).

운영 원칙: `$0 시작`, `T+1 일봉 배치`

## 9.2 수집 소스 우선순위

### (1) SEC EDGAR — 기업 공시 텍스트 ✅ 활성
- 목적: 기업 이벤트 신호 (`filing_risk_burst`)
- API: `data.sec.gov` REST API
- 대상: Observability SOT 섹터 ETF 주요 편입 대형주 ~100종목 (초기 hardcode)
- 수집 형식: 8-K, 10-Q, 10-K
- 제약: 10 req/sec 상한, `User-Agent: macosc0625@gmail.com` 필수
- 멱등키: `(source="sec_edgar", source_doc_id=accession_number)`
- 백필 가능: ✅ (EDGAR는 역사 공시 모두 공개)

### (2) Fed / FOMC / Treasury — 정책 텍스트 ✅ 활성
- 목적: 거시 국면 보조 신호 (`macro_hawkish_score`)
- RSS: `https://www.federalreserve.gov/feeds/press_all.xml` (접근 확인 완료)
- 수집 범위: 성명서, 의사록, 연설문/보도자료
- 제약: HTML 파서 안정화 필요 (다양한 문서 포맷)
- 멱등키: `(source="fed_fomc", source_doc_id=rss_link)`

### (3) FMP News — 보조 뉴스 ⚠️ 보류
- 현황: 무료 플랜(250 req/day)에서 뉴스 엔드포인트 미지원
- 활성화 조건: Starter 플랜 이상($22/월) 또는 대체 소스 확정 시
- 대체 후보: NewsAPI.org (100 req/day, 비상업적), Marketaux (100 articles/day)

## 9.3 Gold Feature 초기 목록

| feature_name | 소스 | 계산 방식 |
| --- | --- | --- |
| `macro_hawkish_score` | fed_fomc | FOMC 문서 내 hawkish 키워드 비율 |
| `filing_risk_burst` | sec_edgar | 일별 8-K 건수 rolling z-score (20일) |
| `policy_uncertainty_idx` | sec + fed | SEC burst + Fed burst 가중합 |

## 9.4 저장 구조

```
data/
└── bronze/text/{source}/ingest_date=YYYY-MM-DD/*.parquet
└── silver/text/text_enriched/event_date=YYYY-MM-DD/*.parquet
└── gold/text/text_daily_features/year=YYYY/month=MM/*.parquet
```

---

# 10. 향후 확장

* ingest Writer를 Airflow Sensor + Operator 기반 배치로 변환 (M3)
* Bronze → Silver 정규화 파이프라인 추가 (M4)
* Universe-Stock(U0~U3) 생성 모듈에서 ingest 데이터 활용 (M2~M5)
* Observability ETF 데이터는 Universe-ETF(Execution Universe) 입력으로도 보조 활용
* 텍스트 소스: FMP News 유료 전환 또는 대체 소스 추가 (2주 KPI 관측 후)
