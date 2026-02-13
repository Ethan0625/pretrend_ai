# 📄 Pre-Trend Value AI 시스템

# 프로젝트 마일스톤 문서 (Milestones)

**Version:** 2025.12\
**Period:** 2025.12 ~ 2026.11\
**Scope:** 거시 → 테마 → 종목 Universe 기반 AI 자동매매 리서치 시스템

---

# 1. Overview

본 문서는 Pre-Trend Value 기반 자동매매 `AI 시스템의 연간 개발 로드맵 (12개월)`을 정의한다.

프로젝트는 다음의 6개 마일스톤(M0~M6)으로 이루어지며,
각 마일스톤은 명확한 목표, 작업 범위, 산출물을 포함한다.

기본 전략 방향은 다음과 같다:

* 한국 시장 제외 → **미국/글로벌 종목 중심** Universe
* 전 종목 수집이 아닌 → **U0~U3 파이프라인 기반 최적 Universe만 추적**
* EOD·펀더멘털·거시·테마 신호를 결합한 AI 분석 시스템 설계
* vLLM 기반 리서치 모듈 + FastAPI 백엔드 + Data Lake Architecture

---

# 2. Milestones Summary (표)

| 코드     | 기간    | 목표                        | 핵심 산출물                         |
| ------ | ----- | ------------------------- | ------------------------------ |
| **M0** | 2주    | 환경 세팅 & 문서 구조 확립          | Repo 구조, Docs, CI              |
| **M1** | 4~6주  | Step 0: 데이터 소스 수집 레이어 구축  | Macro/Theme/Stock 인입 파이프라인     |
| **M2** | 6~8주  | Universe 생성 파이프라인(U0~U3)  | Macro→Theme→Stock Universe 자동화 |
| **M3** | 4~6주  | EOD 파이프라인(Step 1)         | U3 Universe 기반 EOD 수집          |
| **M4** | 6~8주  | Silver/Gold Feature Layer | 성장성/수급/모멘텀 시계열 피처              |
| **M5** | 8~12주 | 전략 신호 & 백테스트              | Pre-Trend Value Score 모델       |
| **M6** | 8~12주 | MLOps / 서빙 / 자동화          | Docker/K8s/MLflow/Airflow      |

---

# 3. Milestone Details

---

## **M0. 프로젝트 기반 구성 (2025.12 ~ 2주)**

### 🎯 목표

* 개발 환경, 레포 구조, 문서 체계 정비
* 프로젝트의 기반 설계 확립

### 📌 주요 작업

* Ubuntu + RTX4090 서버 환경 설정
* VS Code Remote SSH 구성
* Conda env: `pretrend-dev`
* vLLM 서버 & FastAPI API 서버 초기 구동
* GitHub main/dev 브랜치 규칙, Actions(pytest) 설정
* 문서 기본 구조 작성 (`docs/architecture.md`, `docs/dev_plan.md` 등)

### 📦 산출물

* 프로젝트 디렉토리 구조 완성
* CI 기반 테스트 자동화
* 초기 문서 세트 및 Versioned changelog

---

## **M1. ETL Step 0 — 데이터소스 인입 레이어 구축 (4~6주)**

### 🎯 목표

Universe 구축 전에 필요한 **Macro → Theme → Stock** 데이터 원천 확보.

### 📌 주요 작업

* Macro Ingest: Fed Funds Rate, CPI, PPI, PMI, 고용지표, 뉴스 헤드라인
* Theme Ingest: 테마 ETF 리스트, ETF 구성 종목, 성과(1M/3M/6M), Flow 데이터
* Stock Fundamentals Ingest: Revenue, EPS, FCF, ROE/ROIC, 시총, 섹터
* 데이터 저장(브론즈): Parquet + 메타데이터 저장
* 멱등성 및 스케줄러 구조 설계

### 📦 산출물

* `docs/data_ingest_step0.md`
* `src/pretrend/pipeline/step0_*`
* `/data/bronze/{macro,theme,fundamental}`
* 테스트 코드(`tests/pipeline/test_step0_*.py`)

---

## **M2. Universe Pipeline(U0~U3) 구현 (6~8주)**

### 🎯 목표

정책/거시 신호 기반 **테마 → 종목 Universe 자동 생성 시스템** 구축.

### 📌 주요 작업

* U0: Macro Signal Detector

  * 거시 이벤트 라벨링
  * 뉴스 기반 키워드 스코어링
* U1: Theme Prioritization

  * ETF 성과·유입 기반 테마 스코어
  * 테마 후보 자동 선정
* U2: Theme Universe Builder

  * 테마별 핵심 종목 자동 생성
* U3: Growth & Flow Filtering

  * 성장성 + 수급 proxy + 모멘텀 기반 최종 Universe 산출

### 📦 산출물

* `src/pretrend/universe/*`
* Universe 업데이트 스케줄러
* `tests/universe/test_*.py`

---

## **M3. Step 1 EOD Data Pipeline (4~6주)**

### 🎯 목표

**U3 Universe 종목만** EOD 데이터를 Bronze 레이어에 수집.

### 📌 주요 작업

* Fetcher / Normalizer / Writer 아키텍처
* 멱등성: run_id, tmp-write → atomic move
* Partition: `source/theme/symbol/trade_date`
* Universe 변경 시 자동 종목 업데이트
* 메타데이터 저장(성공/행수/체크섬)

### 📦 산출물

* `src/pretrend/pipeline/step1_eod_ingest.py`
* `/data/bronze/eod/*`
* 테스트 세트

---

## **M4. Silver/Gold Layer + Feature Engineering (6~8주)**

### 🎯 목표

전략 신호 계산을 위한 **정규화 데이터(Silver)와 Feature Table(Gold)** 구축.

### 📌 주요 작업

* Silver Layer:

  * 결측치/이상치 처리
  * 조정주가/물가 보정
  * 테마/산업 라벨 매핑
* Gold Layer:

  * 성장성/수급/모멘텀 Feature 생성
  * 롤링 윈도우 기반 시계열 피처
  * Macro + Theme + Stock 종합 피처 구축

### 📦 산출물

* `/data/silver/*`, `/data/gold/*`
* `src/pretrend/features/*`

---

## **M5. Signal Modeling & Research (8~12주)**

### 🎯 목표

Pre-Trend Value 전략 신호 및 백테스트 시스템을 구축.

### 📌 주요 작업

* Composite Score Model (성장성 × 수급 × 테마 × 모멘텀)
* ML 기반 점수 모델(XGBoost 등)
* Backtesting 구조 설계 및 최소 전략 검증
* LLM 기반 산업/기업 리서치 요약 기능
* FastAPI 신호 조회 엔드포인트 작성

### 📦 산출물

* `src/pretrend/signals/*`
* `research/notebooks/*`
* API 엔드포인트 `/signals/*`

---

## **M6. MLOps / 서빙 / 운영 자동화 (8~12주)**

### 🎯 목표

전체 시스템을 운영 가능한 형태로 배포 및 자동화.

### 📌 주요 작업

* Dockerfile / docker-compose 구성
* vLLM 서버 최적화 및 템플릿 관리
* FastAPI 백엔드 통합
* Airflow(또는 Prefect)로 전체 파이프라인 오케스트레이션
* MLflow/W&B로 실험/모델 관리
* Grafana/Prometheus로 모니터링 구성

### 📦 산출물

* `/deploy/*` 배포 세트
* Airflow DAGs
* 운영 가이드 (`docs/operation_guide.md`)

---

# 4. 전체 타임라인(12개월)

```plaintext
M0 (2주): 환경/문서/구조 세팅
M1 (4~6주): 데이터 소스 인입 레이어 구축
M2 (6~8주): Universe 파이프라인(U0~U3)
M3 (4~6주): Step 1 EOD 수집 파이프라인
M4 (6~8주): Silver/Gold Feature Layer
M5 (8~12주): 전략 신호 + 백테스트 + 리서치
M6 (8~12주): MLOps + 서빙 + 자동화
```

---

# 5. 장기 개선 로드맵(향후 버전)

* Macro Detector를 LLM Fine-tuned 버전으로 강화
* ETF Flow + 뉴스 모멘텀 결합 테마 점수 고도화
* Named Entity 기반 테마-종목 연관도 모델
* 강화학습 기반 종목 스코어 최적화
* 실시간 데이터 스트림 기반 온라인 시그널
* Alpaca/IBKR API 기반 자동 매매 지원

---

# 6. 전략 아키텍처 로드맵 (Risk-Control)

## 6.1 목적
- 전략 모듈을 점수 튜닝이 아닌 상태 기반 구조로 고정한다.
- `Layer -> Market Structure -> Composer -> Universe -> Allocation Engine` 흐름을 기준으로 버전을 확장한다.

## 6.2 버전별 계획

| 버전 | 범위 | 상태 | 비고 |
| --- | --- | --- | --- |
| v0 | 총 투자 비율 조절 + `risk_gate` | 진행/초기 | Universe 내부 가중치 조절 금지, 심리는 proxy 기반 운용 |
| v1 | volatility-aware adjustment + VIX 편입 | 예정 | 직접 VIX vs term structure 범위 결정 필요 |
| v2 | regime-weighted allocation | 예정 | 레짐 반영 allocation 확장 |
| v3 | Universe 그룹별 동적 가중치 | 예정 | 그룹별 가중치 조절 허용 |

## 6.3 운영 주기 원칙
- Adjustment Cycle: 주 1회 (화요일)
- Portfolio Rebalance: 월 1회 (매달 마지막 주 금요일, 휴장 시 직전 영업일)
- 원칙: `Adjustment != Rebalance`

## 6.4 Non-Goals
- 수치 기반 가중치/컷오프 튜닝 정의
- v0 단계에서 그룹별 가중치 조절 허용
