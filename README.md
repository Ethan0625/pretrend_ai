# Pretrend Data Pipeline

### Market & Macro Data Feature Platform (AI-ready)

v.26.01.22

본 프로젝트는 모델 성능 향상이 아닌, **AI/ML 판단 이전 단계에서 데이터 정합성과 재현성을 확보하는 것**을 최우선 목표로 설계된 **개인 연구 프로젝트**이다.

> ⚠️ 본 Repository는 **모델 학습·추론·자동매매를 직접 구현하지 않는다.**
> 본 프로젝트의 목적은 **AI/ML·LLM 모델이 적용되기 전 단계에서
> 데이터 정합성·재현성·확장성을 검증하는 것**이다.

---

## 프로젝트 핵심 개념

### Layer vs Universe

본 프로젝트는 **Layer**와 **Universe**를 명확히 분리하여 설계되었다.

* **Layer (Bronze → Silver → Gold)**
  → *데이터의 정제·가공 단계*
* **Universe (U0 → U1 → U2 → U3)**
  → *정제된 데이터를 입력으로 받아 판단 결과를 생성하는 계산 과정*

```text
Layer   : 데이터를 어떻게 만들 것인가 (HOW)
Universe: 어떤 대상에 대해 판단할 것인가 (WHAT)
```

Layer는 **안정적이고 재현 가능해야 하며**,
Universe는 **정책·전략에 따라 변경 가능한 계산 결과**로 취급된다.

---

## 프로젝트 목표

* 이질적인 시계열 데이터(EOD·Macro)를 **point-in-time 안전하게 정렬**
* Bronze → Silver 레이어 기반 **재현 가능한 Feature 생성**
* Airflow 기반 **운영 환경에 가까운 배치 파이프라인 구성**
* Universe 계산 로직을 분리하여 **전략 실험 가능성 확보**
* 향후 ML/LLM 적용을 전제로 한 **AI-ready 데이터 구조 설계**

---

## 현재 구현 범위

* 📊 **데이터 파이프라인 / Airflow ETL**

  * Bronze / Silver Layer
  * 롤링 재처리 + 파티션 overwrite 기반 멱등성
* 🧮 **거시 지표 기반 Macro Feature 생성**

  * FRED 연동
  * YoY / MoM / Rolling / Regime Feature
* 📈 **EOD 가격 기반 Feature 생성**

  * Return / Trend / Volatility / Momentum / Risk
* 📦 **운영 친화적 저장 구조**

  * Parquet + 연/월 파티션
* 🧪 **Pre-production 검증 중심 설계**

  * 로컬 실행 + DAG 기반 재현성 확보

> ❌ 자동매매, 모델 학습, 실시간 추론은 **현재 범위에 포함되지 않는다.**

---

## 1. 폴더 구조

[그림] 상위 폴더 구조

```text
pretrend_ai/
├─ docs/                     # 설계·환경·데이터 문서
├─ data/                     # Bronze / Silver 데이터
├─ dags/                     # Airflow DAG
├─ src/pretrend/
│  ├─ pipeline/              # Ingest → Feature 파이프라인
│  │  ├─ ingest/
│  │  └─ features/
│  ├─ universe/              # Universe 계산 로직 (예정)
│  ├─ signals/               # 전략/신호 (Out of scope)
│  ├─ llm/                   # LLM 연계 (Out of scope)
│  └─ utils/
├─ backend_api/              # Feature 조회용 API (예정)
└─ tests/
```

---

## 2. 데이터 레이어 구조 (Layer)

### 2.1 Bronze Layer — Macro Econ Indicators

* 데이터 소스: **FRED API**
* 목적: 원천 데이터 보존 + 재현성 확보

**비즈니스 키:** `(indicator_id, date)`
**멱등성:** 동일 기간 재실행 시 동일 Parquet overwrite

---

### 2.2 Silver Layer — Macro Features

* 입력: Bronze Macro
* 출력: 판단·모델 입력으로 사용 가능한 Macro Feature

주요 Feature:

* YoY / MoM / Rolling 통계
* Inflation / Labor / Rate / Yield Curve Regime

> Silver Layer는 **모델이 아닌 Feature 재사용성 관점**에서 설계됨

---

### 2.3 Bronze Layer — EOD Daily Prices

* 데이터 소스: **Yahoo Finance (yfinance)**
* 대상: Broad / Sector / Theme ETF (항상 수집)

**비즈니스 키:** `(symbol, trade_date)`
**멱등성:** 거래일 단위 overwrite

---

### 2.4 Silver Layer — EOD Price Features

* Return / Trend / Volatility / Risk
* 데이터 품질 플래그 포함

  * 결측 보정 여부
  * 부분 거래일
  * 이상치 여부

> EOD Silver Feature는
> **Universe 계산 및 Gold Layer 결합의 입력 데이터**로 사용됨

---

## 3. Universe 설계 개념

Universe는 **데이터 수집 여부를 제어하지 않는다.**
Universe는 **정제된 데이터를 기반으로 판단 결과를 생성**한다.

```text
Gold Macro / ETF Feature
        ↓
Universe Selection (U0 → U1 → U2 → U3)
        ↓
확장 대상(EOD 종목) 결정
```

* ETF / Macro 데이터: **항상 수집**
* 개별 종목 EOD 처리: **Universe 결과에 따라 확장**

---

## 4. 실행 방법

### 4.1 환경 준비

```bash
conda activate pretrend-dev
export FRED_API_KEY=YOUR_FRED_API_KEY
```

---

### 4.2 Bronze → Silver 실행 예시

```bash
PYTHONPATH=src python -m pretrend.pipeline.ingest.macro \
  --start 2010-01-01 \
  --end 2025-12-01
```

```bash
PYTHONPATH=src python -m pretrend.pipeline.features.macro_features \
  --start 2010-01-01 \
  --end 2025-12-01
```

---

### 4.3 Airflow 기반 실행 (권장)

* DAG:

  * `macro_pipeline_dag.py`
  * `eod_pipeline_dag.py`

* 특징:

  * 매 실행 시 **직전월 1일 ~ 전일 롤링 재처리**
  * 파티션 overwrite 기반 멱등성
  * Airflow는 대규모 운영 목적이 아니라, **배치 재현성과 파이프라인 경계 명확화**를 위해 사용

---

## 5. 문서

* 환경 구성: `/docs/environment.md`
* 데이터 설계:
  * `/docs/data_requirements.md`
  * `/docs/universe_design.md`
* 아키텍처: `/docs/architecture.md`
* 변경 이력: `/docs/changelog.md`

---

## 6. 향후 확장 로드맵 (Out of scope)

아래 항목은 **현재 구현 범위에는 포함되지 않으며**,
Layer 구조 검증 이후 단계에서 확장 예정이다.

* [x] **FRED Macro Bronze Ingest (CPI/UNRATE/FEDFUNDS/DGS10)**
* [x] **Macro Silver Feature 설계 (YoY/MoM/Rolling/Regime)**
* [x] **EOD Bronze Ingest (yfinance, SPY/QQQ/VOO)**
* [x] **EOD Silver Feature 설계 (Return / Vol / ATR / RSI)**
* [x] **Airflow DAG 기반 Macro/EOD Bronze → Silver 통합 파이프라인**
* [ ] Gold Layer (Macro + EOD Feature Mart)
* [ ] Universe U1~U3 스코어링 로직 구현
* [ ] 뉴스 / FOMC / 거시 리포트 텍스트 수집
* [ ] 전략/신호 생성 모듈 (Pre-Trend Value Score)
* [ ] Docker → Kubernetes 전환 / 배포 자동화
* [ ] Grafana 기반 모니터링 및 LLM 비용 리포팅 구축

---

> 📌 본 프로젝트는 **개인 연구 및 포트폴리오 용도**로, 
> **금융 데이터 파이프라인과 AI 시스템 구조를 설계·검증하기 위한 Pre-production 단계의 프로젝트**입니다.
>
> 향후 개인 학습 목적의 확장은 가능하나, 현재는 **실거래, 실자금 운용, 외부 서비스 제공을 전혀 수행하지 않습니다.**

---

## Interview Summary (1-minute)

- 본 프로젝트는 자동매매나 모델 성능을 다루지 않는다.
- AI 적용 이전 단계에서 데이터 파이프라인과 판단 구조를 검증하는 것이 목적이다.
- Layer와 Universe를 분리하여 재현성과 전략 실험 가능성을 동시에 확보했다.
