# Pretrend Data Pipeline

### Market & Macro Data Feature Platform (AI-ready)

v.26.02.21

본 프로젝트는 모델 성능 향상이 아닌, **AI/ML 판단 이전 단계에서 데이터 정합성과 재현성을 확보하는 것**을 최우선 목표로 설계된 **개인 연구 프로젝트**이다.

> ⚠️ 본 Repository는 **모델 학습·추론·자동매매를 직접 구현하지 않는다.**
> 본 프로젝트의 목적은 **AI/ML·LLM 모델이 적용되기 전 단계에서
> 데이터 정합성·재현성·확장성을 검증하는 것**이다.

---

## 프로젝트 핵심 개념

### Layer vs Strategy Engine

본 프로젝트는 **Layer**와 **Strategy Engine**을 명확히 분리하여 설계되었다.

* **Layer (Bronze → Silver → Gold)**
  → *데이터의 정제·가공 단계*
* **Strategy Engine**
  → *정제된 Gold snapshot을 입력으로 받아 WHAT/EXPOSURE/SELL 경계를 생성하는 계산 과정*

```text
Layer          : 데이터를 어떻게 만들 것인가 (HOW)
StrategyEngine : 입력 snapshot으로 무엇을/얼마나/어떻게 실행할 것인가 (WHAT/EXPOSURE/SELL)
```

Layer는 **안정적이고 재현 가능해야 하며**,
Strategy Engine은 **정책·전략 상태에 따라 변경 가능한 계산 결과**로 취급된다.

---

## 프로젝트 목표

* 이질적인 시계열 데이터(EOD·Macro)를 **point-in-time 안전하게 정렬**
* Bronze → Silver 레이어 기반 **재현 가능한 Feature 생성**
* Airflow 기반 **운영 환경에 가까운 배치 파이프라인 구성**
* Universe-ETF 계산 로직을 분리하여 **전략 실험 가능성 확보**
* 향후 ML/LLM 적용을 전제로 한 **AI-ready 데이터 구조 설계**

---

## 현재 구현 범위

* 📊 **데이터 파이프라인 / Airflow ETL**

  * Bronze / Silver Layer
  * 롤링 재처리 + 파티션 overwrite 기반 멱등성
* 🗓️ **Calendar Pipeline (Release Evidence)**

  * Bronze/Silver Calendar (`econ_events`, `fred_vintages`) 구현 완료
  * Gold PIT-safe 조인을 위한 release evidence 제공
* 🥇 **Gold Macro Feature v1**

  * Silver Macro + Silver Calendar 기반 Gold Macro Feature 생성
  * `macro_job.py` 1회 실행으로 Bronze → Silver → Gold 동기화
* 🥇 **Gold EOD Feature v1**

  * Silver EOD Feature 기반 Gold EOD Fact Mart 생성
  * `gold_eod_features.py` CLI 및 `eod_job.py` E2E(Bronze → Silver → Gold) 실행 지원
  * `eod_pipeline_dag.py`에서 Bronze → Silver → Gold 체인으로 동작
* 🧭 **Risk-Control 전략 문서 구조(v0)**

  * 전략 흐름: `Layer -> Market Structure(4축) -> Composer -> Universe-ETF -> Allocation Engine -> Weekly Report`
  * 상태 기반 Allocation 중심으로 문서/계약 구조 재정의
  * v0는 총 투자 비율(`invested_ratio`) 조절만 수행, Universe-ETF 내부 가중치 조절은 제외
* 🧠 **Strategy Engine v0 구현**

  * Gold Macro + Gold EOD snapshot을 입력으로 7단계 파이프라인 실행
  * 단계: Axis Features(4축) → Axis×Horizon(12-slot) → Market Position → Policy Selector → Universe-ETF → Allocation → Sell Planner
  * 출력 경계: WHAT_TO_HOLD / HOW_MUCH_EXPOSURE / HOW_MUCH_TO_SELL
  * `decision_date` snapshot 저장 및 재현성(멱등 overwrite) 보장
  * Long Engine v1: `delta_6m` rolling z-score 정규화 + `z_threshold=0.3` 운영
* 🧪 **Backtest Engine v2 + Walk-Forward**

  * Preset v2(`long_phase × mid_regime` 2D lookup) 지원
  * Walk-Forward 분석 CLI(`window-years`, `step-years`) 및 parquet/json 저장 지원
  * 결과 지표 JSON(`*_metrics.json`) 저장 지원
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
├─ data/                     # Bronze / Silver / Gold / Meta 데이터
├─ dags/                     # Airflow DAG
├─ src/pretrend/
│  ├─ pipeline/              # Ingest → Feature 파이프라인
│  │  ├─ config/             # Observability SOT 등 공통 설정
│  │  ├─ ingest/
│  │  ├─ features/
│  │  └─ calendar/           # Calendar release evidence 파이프라인
│  ├─ universe/              # Universe-ETF 계산 로직 (현재 구현)
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
* 대상: **Observability SOT 32개 ETF (Always-on)**
* 분류 라벨(`asset_group`, `asset_name`, `asset_subtype`)은 Bronze에서 1회 확정

**비즈니스 키:** `(symbol, trade_date)`
**멱등성:** 거래일 단위 overwrite

---

### 2.4 Silver Layer — EOD Price Features

* Return / Trend / Volatility / Risk
* Bronze에서 확정된 분류 라벨(`asset_group`, `asset_name`, `asset_subtype`)을 수정 없이 pass-through
* 데이터 품질 플래그 포함

  * 결측 보정 여부
  * 부분 거래일
  * 이상치 여부

> EOD Silver Feature는
> **Universe-ETF 계산 및 Gold Layer 결합의 입력 데이터**로 사용됨

---

### 2.5 Gold Layer — EOD Feature v1 Fact Mart

* 입력: Silver EOD Features
* Grain: `(symbol, trade_date)` (중복 제거 후 1행 보장)
* 라벨 전파: `asset_group`, `asset_name`, `asset_subtype` carry-forward
* Lineage: `run_id_gold`, `ingestion_ts_gold`
* 저장 경로:
  - `data/gold/eod/eod_features/symbol=XXX/year=YYYY/month=MM/gold_eod_features_YYYYMM.parquet`

---

## 3. Strategy Engine 설계 개념

Strategy Engine은 **데이터 수집 여부를 제어하지 않는다.**
Strategy Engine은 **정제된 Gold snapshot을 기반으로 실행 경계 출력**을 생성한다.

```text
Gold Macro / Gold EOD Snapshot
        ↓
Strategy Engine (Axis×Horizon → Policy → Universe-ETF → Allocation → Sell)
        ↓
WHAT_TO_HOLD / HOW_MUCH_EXPOSURE / HOW_MUCH_TO_SELL
```

* ETF / Macro 데이터: **항상 수집**
* Strategy Engine은 `decision_date` 단위 snapshot 결과를 저장

---

## 4. 실행 방법

### 4.0 Universe 용어 기준

| 용어 | 의미 | 상태 |
| --- | --- | --- |
| Universe-ETF (Execution Universe) | Strategy Engine에서 Observability ETF 후보를 선별하는 현재 실행 모듈 | 구현/운영 중 |
| Universe-Stock (Research Universe, U0~U3) | Macro→Theme→Stock 파이프라인 기반 종목 유니버스 | 로드맵(미착수) |

현재 시스템 성격:
- 현재 운용은 **ETF 실행 유니버스(= Universe-ETF)** 중심이다.
- 종목 선택 파이프라인 **Universe-Stock(U0~U3)**는 `docs/milestones.md` 기준으로 확장한다.

### 4.1 빠른 시작 (개발/테스트)

```bash
# 의존성 설치 (editable)
python -m pip install -e .
# Parquet 엔진이 없으면 선택적으로 설치
pip install pyarrow  # 또는 fastparquet
```

테스트 실행:

```bash
pytest -q
# 특정 케이스만
pytest -q tests/pipeline/test_eod_silver_writer_idempotency.py
pytest -q tests/pipeline/test_macro_silver_writer.py
```

### 4.2 환경 준비

```bash
conda activate pretrend-dev
export FRED_API_KEY=YOUR_FRED_API_KEY
```

### 4.3 Strategy Engine 실행

```bash
# Strategy Engine 단일 실행
PYTHONPATH=src python -m pretrend.pipeline.strategy_engine.strategy_job --date 2024-06-03 --invested-ratio 0.10

# z-threshold 지정 실행
PYTHONPATH=src python -m pretrend.pipeline.strategy_engine.strategy_job --date 2024-06-03 --invested-ratio 0.10 --z-threshold 0.3

# 전체 테스트
conda run -n pytest-pretrend pytest tests/ -v
```

검증 기준(2026-02-21 세션):
- 테스트: `305 passed, 1 skipped`
- Strategy snapshots: `2009-03-09`, `2024-06-03` 기준 스모크 검증 완료

### 4.4 Backtest / Walk-Forward 실행

```bash
# Backtest preset v2
PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v2

# Walk-Forward (4년 창, 2년 슬라이드)
PYTHONPATH=src python -m pretrend.pipeline.backtest.walk_forward --preset v2 --window-years 4 --step-years 2

# Walk-Forward 저장 (parquet + summary json)
PYTHONPATH=src python -m pretrend.pipeline.backtest.walk_forward --preset v2 --window-years 4 --step-years 2 --save
```

---

### 4.3 Bronze → Silver 실행 예시

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

```bash
PYTHONPATH=src python -m pretrend.pipeline.calendar.runner --target all
```

```bash
PYTHONPATH=src python -m pretrend.pipeline.macro_job \
  --start 2024-01-01 \
  --end 2024-06-30
```

```bash
PYTHONPATH=src python -m pretrend.pipeline.features.gold_eod_features \
  --start 2024-01-01 \
  --end 2024-06-30
```

```bash
PYTHONPATH=src python -m pretrend.pipeline.eod_job \
  --start 2024-01-01 \
  --end 2024-06-30
```

---

### 4.4 Airflow 기반 실행 (권장)

* DAG:

  * `macro_pipeline_dag.py`
  * `eod_pipeline_dag.py`

* 특징:

  * 매 실행 시 **직전월 1일 ~ 전일 롤링 재처리**
  * 파티션 overwrite 기반 멱등성
  * Airflow는 대규모 운영 목적이 아니라, **배치 재현성과 파이프라인 경계 명확화**를 위해 사용

---

## 5. Codex 사용 정책 (Agent-assisted Dev)

- 모든 작업 전 `AGENTS.md` 규칙을 준수하고, 작은/검토 가능한 diff를 유지한다 (선호: ≤300 LOC).
- `dev`에서 분기한 `codex/<task>` 브랜치로 작업한다.
- 한 번에 하나의 작업만 포함하고, 실행 가능한 검증 명령(예: `pytest -q`, 단일 테스트 파일은 `pytest -q tests/pipeline/<file>.py`)을 제시한다.
- 안정성을 위해 가능하면 범위가 좁은 변경(예: tests-only, docs-only)으로 작업한다.

---

## 5. 문서

* 환경 구성: `/docs/environment.md`
* 데이터 설계:
  * `/docs/data_requirements.md`
  * `/docs/universe_design.md`
* 아키텍처: `/docs/architecture.md`
* 전략 설계/계약:
  * `/docs/strategy_architecture.md`
  * `/docs/architecture/market_structure_long_contract.md`
  * `/docs/architecture/market_structure_mid_contract.md`
  * `/docs/architecture/market_structure_short_contract.md`
  * `/docs/architecture/market_structure_composer_contract.md`
  * `/docs/architecture/universe_contract.md`
  * `/docs/architecture/allocation_engine_contract.md`
  * `/docs/market_structure_data_inventory.md`
* 변경 이력: `/docs/changelog.md`

---

## 6. 향후 확장 로드맵 (Out of scope)

아래 항목은 **현재 구현 범위에는 포함되지 않으며**,
Layer 구조 검증 이후 단계에서 확장 예정이다.

* [x] **FRED Macro Bronze Ingest (CPI/UNRATE/FEDFUNDS/DGS10)**
* [x] **Macro Silver Feature 설계 (YoY/MoM/Rolling/Regime)**
* [x] **EOD Bronze Ingest (yfinance, Observability SOT 32개 ETF)**
* [x] **EOD Silver Feature 설계 (Return / Vol / ATR / RSI)**
* [x] **EOD Observability Contract v1 (32 ETFs SOT + Bronze labels + Silver/Gold pass-through)**
* [x] **Airflow DAG 기반 Macro/EOD Bronze → Silver 통합 파이프라인**
* [x] **Calendar Pipeline v1 (Bronze/Silver: econ_events + fred_vintages)**
* [x] **Gold Macro Feature v1 (Macro + Calendar fallback cascade)**
* [x] Gold Layer (Macro + EOD Feature Mart)
* [x] **Risk-Control 전략 문서 분리 (Market Structure 4축 + Composer + Allocation v0 Contract)**
* [ ] Strategy Engine v1+ 확장(Stock/Text/LLM 포트 운영화)
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
- Layer와 Universe-ETF를 분리하여 재현성과 전략 실험 가능성을 동시에 확보했다.
