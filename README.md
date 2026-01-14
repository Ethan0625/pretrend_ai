# Pretrend AI — Pre-Trend Value 기반 주식 자동매매 시스템

v.26.01.14\
본 프로젝트는 **Pre-Trend Value** 관점에서  

- 유효한 데이터 (EOD·뉴스·정책·거시) 기반 분석  
- 테마 스코어링 + 저평가 종목 필터링  
- LLM 기반 리서치  
- EOD 기반 자동매매 신호 생성  

까지 포함하는 **종합 자동매매 시스템**을 구축하는 것을 목표로 한다.

본 Repository는 다음 기능을 포함한다.

- 🎛 **FastAPI 기반 백엔드 API**
- 🧠 **vLLM 기반 LLM 서버(Qwen/Llama 계열)**
- 📊 **데이터 파이프라인 / Airflow ETL (Bronze/Silver 레이어)**
- 🧮 **거시 지표 기반 Macro Feature 생성 (FRED 연동)**
- 📚 **리서치(Notebook) 기반 모델 실험**
- 🧩 **전략/신호 생성 로직**
- 📦 **Docker/K8s 기반 배포 구성(향후)**

---

## 1. 폴더 구조

[그림] 상위 폴더 구조

```text
pretrend_ai/
├─ .gitignore
├─ .env.example
├─ README.md
├─ requirements.txt
│
├─ docs/
│  ├─ dev_plan.md
│  ├─ environment.md
│  ├─ universe_design.md
│  ├─ data_requirements.md
│  ├─ data_ingest_datasources.md
│  ├─ architecture.md         
│  ├─ api_spec.md             
│  └─ changelog.md
│
├─ data/
│  ├─ bronze/                 # Raw/Bronze 레이어 (Ingest 결과)
│  │  └─ macro/
│  │      └─ econ_indicators/
│  │          └─ year=YYYY/month=MM/*.parquet
│  ├─ silver/                 # Silver 레이어 (Feature 변환 결과)
│  │  └─ macro/
│  │      └─ macro_features/
│  │          └─ year=YYYY/month=MM/*.parquet
│  └─ meta/                   # Ingest/Silver 메타 정보(추후)
│
├─ dags/
│  ├─ macro_pipeline_dag.py    # Macro Bronze → Silver DAG
│  └─ eod_pipeline_dag.py      # EOD Bronze → Silver DAG
│
├─ src/
│  └─ pretrend/
│      ├─ pipeline/           # 데이터 파이프라인 (Ingest → Feature)
│      │   ├─ __init__.py
│      │   ├─ ingest/
│      │   │   ├─ __init__.py
│      │   │   ├─ base.py         
│      │   │   └─ macro.py        
│      │   └─ features/
│      │       ├─ __init__.py
│      │       └─ macro_features.py  # Macro Silver Feature Layer (Bronze → Silver)
│      │       └─ eod_features.py    # EOD Silver Feature Layer
│      ├─ signals/            # 신호/전략 모듈 (예정)
│      ├─ llm/                # LLM 클라이언트, RAG, 프롬프트 템플릿 (예정)
│      ├─ config/             # 설정/스키마 정의 (예정)
│      └─ utils/              # 공통 유틸 (예정)
│
├─ backend_api/
│  ├─ app/
│  │  ├─ __init__.py
│  │  ├─ main.py
│  │  ├─ config.py
│  │  ├─ routers/
│  │  ├─ services/
│  │  └─ models/
│  └─ tests/
│
├─ tests/
│  ├─ pipeline/
│  │  ├─ test_macro_ingest.py        
│  │  └─ test_macro_features.py      
│  └─ ...
│
├─ deploy/
│  ├─ docker/
│  ├─ compose/
│  └─ k8s/
│
└─ .github/
   └─ workflows/
      └─ ci.yml
```

---

## 2. 데이터 레이어 구조 (Bronze / Silver)

### 2.1 Bronze Layer — Macro Econ Indicators

* 데이터 소스: **FRED API**
* Ingest 모듈: `src/pretrend/pipeline/ingest/macro.py`
* 공통 인터페이스: `BaseFetcher / BaseNormalizer / BaseWriter` (`base.py`)

[표] Bronze Macro Ingest 요약

| 항목         | 내용                                            |
| ---------- | --------------------------------------------- |
| Fetcher    | `MacroFetcher` (FRED API 호출, multi-series 지원) |
| Normalizer | `MacroNormalizer` (표준 스키마로 정규화)               |
| Writer     | `MacroWriter` (연/월/indicator 파티션 Parquet 저장)  |
| 비즈니스 키     | `(indicator_id, date)`                        |
| 멱등성        | 동일 날짜 범위로 재실행 시 같은 Parquet 파일 덮어쓰기            |

**Bronze 스키마**

```text
indicator_id: str      # 내부 지표 ID (예: CPI_US_ALL_ITEMS_SA)
date: date
value: float
unit: str
source: str            # "FRED"
run_id: str
ingestion_ts: timestamp
```

**Bronze 저장 경로**

```text
data/bronze/macro/econ_indicators/year=YYYY/month=MM/{indicator_id}_YYYYMM.parquet
```

---

### 2.2 Silver Layer — Macro Features

* 입력: Bronze 매크로 지표 (`econ_indicators`)
* 모듈: `src/pretrend/pipeline/features/macro_features.py`
* 역할: 전략 인풋으로 사용할 **Macro Feature 세트** 생성

[표] Silver Macro Feature 요약

| 항목         | 내용                                                                      |
| ---------- | ----------------------------------------------------------------------- |
| 입력         | Bronze econ_indicators (CPI, Core CPI, UNRATE, FEDFUNDS, DGS10)         |
| 공통 Feature | `yoy`, `mom`, `rolling_3m`, `rolling_12m`                               |
| CPI/Core   | 인플레이션 레짐 (`high_inflation`, `elevated`, `moderate`, `disinflation`)     |
| UNRATE     | `level`, `delta_3m`, 노동시장 레짐 (`tight`, `loosening`, ...)                |
| FEDFUNDS   | `level`, `delta_3m`, `delta_12m`, 금리 레짐 (`hiking`, `cutting`, `paused`) |
| DGS10      | `level`, `spread_to_fedfunds`, `is_yield_curve_inverted`, 커브 레짐         |

**Silver 스키마(공통)**

```text
indicator_id: str
date: datetime64[ns]
value: float
yoy: float?
mom: float?
rolling_3m: float?
rolling_12m: float?
regime: str?
level: float?
delta_3m: float?
delta_12m: float?
spread_to_fedfunds: float?
is_yield_curve_inverted: bool?
ingestion_ts: timestamp   # Silver 생성 시각
```

**Silver 저장 경로**

```text
data/silver/macro/macro_features/year=YYYY/month=MM/macro_features_YYYYMM.parquet
```

* 파티션 키: `(year, month)`
* 멱등성: 특정 기간 `[start, end]`에 대해 실행 시, 해당 연/월 파티션 파일을 **통째로 overwrite**하는 방식으로 보장.

---

### 2.3 Bronze Layer — EOD Daily Prices

* 데이터 소스: **Yahoo Finance (yfinance)**
* Ingest 모듈: `src/pretrend/pipeline/ingest/eod.py`
* 대상 자산 (PoC 단계):
  - SPY
  - QQQ
  - VOO
* 기준 날짜:
  - 미국장 기준 **“마지막 완전 거래일”**
  - 장 마감(16:00 ET) + 버퍼 시간 이후 데이터만 수집

[표] Bronze EOD Ingest 요약

| 항목         | 내용 |
|------------|------|
| Fetcher    | `EodFetcher` (yfinance 기반) |
| Normalizer | `EodNormalizer` (표준 스키마 정규화) |
| Writer     | `EodWriter` (symbol / trade_date 파티션 저장) |
| 비즈니스 키 | `(symbol, trade_date)` |
| 멱등성     | 동일 날짜 재실행 시 동일 Parquet overwrite |

**Bronze EOD 스키마**

```text
symbol: str
theme: str
source: str
trade_date: date
open: float
high: float
low: float
close: float
adj_close: float
volume: int
currency: str
run_id: str
ingestion_ts: timestamp
````

**Bronze EOD 저장 경로**

```text
data/bronze/eod/daily_prices/
  source=YF/theme=GENERIC/symbol=SPY/trade_date=YYYY-MM-DD/eod.parquet
```

---

### 2.4 Silver Layer — EOD Price Features

* 입력: EOD Bronze daily_prices
* 모듈: `src/pretrend/pipeline/features/eod_features.py`
* 목적:

  * 종목/ETF 단위 **가격·수급 기반 정량 Feature 생성**
  * Macro Feature와 결합되어 Gold Layer의 입력으로 사용

[표] Silver EOD Feature 요약

| Feature 그룹 | 설명 |
| --- | --- |
| Price | OHLCV, Adj Close 등 원천 가격/거래량 |
| Return | ret_1d, log_ret_1d, ret_5d, ret_20d |
| Trend (MA) | ma_5, ma_20, ma_60, ma_120 및 ma_ratio_5_20 |
| Volatility | vol_20d (rolling std) |
| Momentum / Risk | atr_14, rsi_14, intraday_range, gap_open |
| Volume | volume_zscore_20d |
| Data Quality Flag | is_trading_day, is_missing_imputed, is_outlier, is_partial_day |
| Meta | run_id / ingestion_ts (bronze), run_id_silver / ingestion_ts_silver (silver) |

**Silver EOD 스키마(요약)**

```text
symbol: str
trade_date: datetime64[ns]
close: float
return_1d: float?
log_return_1d: float?
ma_n: float?
volatility_n: float?
atr_n: float?
rsi_14: float?
ingestion_ts: timestamp
```

**Silver EOD 저장 경로**

```text
data/silver/eod/eod_features/
  symbol=SYMBOL_NAME/year=YYYY/month=MM/eod_features_YYYYMM.parquet
```

* 파티션 키: `(symbol, year, month)`
* 멱등성: `(symbol, year, month)` 파티션 단위 overwrite 전략
* 임시 경로에 저장 후 최종 파티션으로 이동(또는 교체)하는 방식으로 파일 정합성 확보

---

### 3.1 선행 조건

1. Conda 환경 활성화

```bash
conda activate pretrend-dev
```

2. FRED API 키 설정 (`.env` 또는 셸 환경 변수)

```bash
export FRED_API_KEY=YOUR_FRED_API_KEY
```

---

### 3.2 Bronze Macro Ingest (FRED → Bronze)

[코드] Macro Bronze Ingest 실행 예시

```bash
# 예: 매크로 지표 전체를 2010-01-01 ~ 2025-12-01 범위로 수집
PYTHONPATH=src python -m pretrend.pipeline.ingest.macro \
  --domain macro \
  --dataset econ_indicators \
  --start 2010-01-01 \
  --end 2025-12-01
```

* `MacroFetcher`가 FRED에서 **CPI / Core CPI / UNRATE / FEDFUNDS / DGS10** 시리즈를 수집
* `MacroNormalizer`가 표준 스키마로 정리
* `MacroWriter`가 `data/bronze/macro/econ_indicators/...`에 Parquet로 저장

---

### 3.3 Silver Macro Features (Bronze → Silver Feature)

[코드] Macro Silver Feature 실행 예시

```bash
# Bronze 데이터를 기반으로 Silver Macro Feature 생성
PYTHONPATH=src python -m pretrend.pipeline.features.macro_features \
  --start 2010-01-01 \
  --end 2025-12-01
```

* Bronze 폴더에서 대상 기간의 매크로 지표 로드
* 공통 Feature + indicator-specific Feature 계산
* `data/silver/macro/macro_features/year=YYYY/month=MM/*.parquet` 로 저장

### 3.4 Airflow 기반 Macro / EOD 파이프라인 실행 (권장)

현재 Macro 및 EOD 파이프라인은 **Apache Airflow DAG 기반으로 통합 운영**된다.
Macro DAG는 매일 트리거되지만, 운영상 실행 누락 가능성을 고려하여 매 실행 시 직전월 1일~전일까지를 롤링 재처리한다(파티션 overwrite 기반 멱등성).


* DAG 위치: `pretrend_ai/dags/`
  - `macro_pipeline_dag.py`
  - `eod_pipeline_dag.py`

**실행 방법 (개발 환경)**

```bash
conda activate airflow-pretrend
cd ~/Desktop/ethan/pretrend

./run_airflow_dev.sh init-db     # 최초 1회
./run_airflow_dev.sh webserver   # 터미널 1
./run_airflow_dev.sh scheduler   # 터미널 2
```

* Airflow UI: [http://localhost:8080](http://localhost:8080)
* DAG 단위로 Bronze → Silver E2E 실행

---

## 4. 백엔드 API / vLLM 서버

### 4.1 FastAPI 서버 실행

```bash
cd backend_api
uvicorn app.main:app --host 0.0.0.0 --port 8100
```

헬스체크:

```text
http://127.0.0.1:8100/health
```

### 4.2 vLLM 서버 실행 (예: Qwen2-7B)

```bash
CUDA_VISIBLE_DEVICES=2 python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2-7B-Instruct \
  --host 0.0.0.0 \
  --port 8101 \
  --tensor-parallel-size 1 \
  --max-model-len 4096 \
  --dtype float16
```

확인:

```bash
curl http://127.0.0.1:8101/v1/models
```

---

## 5. 환경 변수 관리

* 실제 환경 변수 파일: **`.env`** (Git ignore 대상)
* GitHub 공개용 템플릿: **`.env.example`**

[코드] `.env.example` 일부

```bash
API_PORT=8100
VLLM_BASE_URL=http://127.0.0.1:8101/v1
VLLM_MODEL_NAME=Qwen/Qwen2-7B-Instruct

DB_HOST=127.0.0.1
DB_USER=pretrend_user
DB_PASSWORD=CHANGE_ME

FRED_API_KEY=CHANGE_ME
```

---

## 6. 문서

* 환경 구성: `/docs/environment.md`
* 전체 Universe / 데이터 요구사항:

  * `/docs/universe_design.md`
  * `/docs/data_requirements.md`
  * `/docs/data_ingest_datasources.md`
* 개발 계획: `/docs/dev_plan.md`
* 아키텍처: `/docs/architecture.md` (Silver/Bronze 구조 및 파이프라인 다이어그램 추가 예정)
* API 명세: `/docs/api_spec.md` (향후 FastAPI 엔드포인트 정의)

---

## 7. 향후 작업 로드맵

* [x] **FRED Macro Bronze Ingest (CPI/UNRATE/FEDFUNDS/DGS10)**
* [x] **Macro Silver Feature 설계 (YoY/MoM/Rolling/Regime)**
* [x] **EOD Bronze Ingest (yfinance, SPY/QQQ/VOO)**
* [x] **EOD Silver Feature 설계 (Return / Vol / ATR / RSI)**
* [x] **Airflow DAG 기반 Macro/EOD Bronze → Silver 통합 파이프라인**
* [ ] Gold Layer 설계 (Macro + EOD 결합 Feature)
* [ ] Universe U1~U3 스코어링 로직 구현
* [ ] 뉴스 / FOMC / 거시 리포트 텍스트 수집
* [ ] 전략/신호 생성 모듈 (Pre-Trend Value Score)
* [ ] Docker → Kubernetes 전환 / 배포 자동화
* [ ] Grafana 기반 모니터링 및 LLM 비용 리포팅 구축

---

## 8. 라이선스 / 기여 가이드

(추후 업데이트)

---

#### 📌 이 프로젝트는 *실제 자동매매 시스템 구축*을 목표로 하며, 코드와 문서가 함께 발전하는 형태로 관리됩니다.

