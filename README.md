# Pretrend AI

### Market Structure Observability Runtime

v.26.05.12 (Observability Track 재정의)

Pretrend AI는 **과거와 현재의 시장 상태(state)를 구조적으로 설명 가능하게(reproducible + explainable) 관측(observable)하는 production-grade observability runtime**이다. 초점은 미래 예측(prediction)이 아니라, "당시 시장에서 실제로 알 수 있었던 구조"를 재현 가능하게 고정하는 것에 있다.

> 이 저장소는 **투자 추천/AI 매매 신호/수익률 예측 시스템이 아니다.**
> Bronze → Silver → Gold 데이터 레이어 위에서, ETF/Macro의 시장 구조를 관측·설명하는 시스템이다.

**핵심 목표**: production-grade runtime ownership 경험 — ingestion reliability, observability, reproducibility, deployment discipline.

---

## Why this exists

투자 영역에서는 "거시경제 흐름이 중요하다"는 말을 자주 하지만, 실제로 거시 이벤트와 시장 구조 변화가 어떤 방식으로 연결되는지를 반복적으로 확인할 수 있는 개인용 도구는 많지 않다. 저는 투자 전망을 제시하기보다, 무료로 접근 가능한 거시·ETF 데이터를 기반으로 시장 상태를 구조화하고, 특정 시점의 시장 구조가 과거 어떤 구간과 유사하거나 다른지를 재현 가능한 방식으로 관측하는 시스템을 만들고자 했다.

## Why this transition

초기 Pretrend는 로컬 기반 매매 실험 구조였으나, 프로젝트 목적을 예측에서 시장 구조 관측으로 전환하면서 공개 운영 가능한 데이터 시스템으로 재설계하고 있다.

이에 따라 로컬 의존 배치 구조를 정리하고, 자동화된 스케줄러 기반 수집, Bronze/Silver/Gold 데이터 레이어, market state feature 생성, dashboard serving, freshness monitoring 구조로 전환하고 있다.

---

## Two-Track 운영 원칙

본 프로젝트는 두 트랙을 명시적으로 분리한다. 자세한 boundary 규칙은 [`docs/architecture/track_separation.md`](docs/architecture/track_separation.md) 참조.

### Observability Track (메인, 신규)
- 시장 구조 관측 시스템 (regime / similarity / explainability)
- FastAPI + React Dashboard + Postgres/TimescaleDB
- 모든 신규 작업의 본진
- 상세 계획: [`.agent/REFACTOR_2026Q2.md`](.agent/REFACTOR_2026Q2.md)

### Personal Track (Investing, **동결 + 운영 중단**)
- 기존 6개월 작업한 Strategy Engine / Backtest / Paper / Broker
- **운영 중단 (2026-05-12~)**: Telegram bot systemd disable, paper/broker/strategy DAG paused
- 코드는 보존, 신규 기능 추가 영구 금지
- 외부에 "투자 시스템"으로 포지셔닝하지 않음

---

## What This Project Is

- **Market structure observability runtime**: ETF/Macro 데이터로 시장 상태를 관측하고 설명한다.
- **재현 가능한 시계열 데이터 파이프라인**: Bronze → Silver → Gold 레이어 기반 PIT-safe snapshot.
- **Layered data architecture**: 원본 보존(Bronze), 정합성 보정(Silver), 관측 입력 준비(Gold)를 책임별로 분리.
- **Historical similarity (Phase 1 신규)**: 현재 시장 구조와 과거 시기의 구조적 유사성 관측 — 예측 아닌 설명.
- **Explainability layer**: LLM은 관측 결과 설명에만 사용. 예측/추천 금지.

## Why This Exists

- 시계열 데이터를 바로 모델이나 전략으로 연결하면 `release_date`, `trade_date`, snapshot 기준이 섞이면서 재현성과 설명 가능성이 무너진다.
- 거시/가격 데이터는 같은 "날짜"를 갖고 있어도 실제로는 가용 시점이 다르므로, 판단 이전에 point-in-time 기준을 먼저 고정해야 한다.
- 배치 재실행이나 백필이 자주 일어나는 데이터 파이프라인에서는 overwrite, atomic write, lineage가 없으면 partial state와 schema drift가 누적된다.
- 전략 성능 실험보다 먼저, **동일 입력이면 동일 결과가 나오는 데이터 기반**을 만드는 것이 운영적으로 더 중요하다고 보고 설계했다.

## Architecture At A Glance

```text
Bronze -> Silver -> Gold -> Strategy Engine

Bronze          : raw ingest and source preservation
Silver          : normalization, dedup, contract-aligned features
Gold            : PIT-safe, strategy-ready snapshots
Strategy Engine : Gold read-only consumer for WHAT / EXPOSURE / SELL
```

- **Layer**는 데이터를 어떻게 만들고 저장하는가에 대한 책임을 가진다.
- **Strategy Engine**은 정제된 Gold snapshot을 읽어 실행 경계를 계산하는 별도 계층이다.
- 이 분리는 데이터 재현성과 전략 실험의 변경 주기를 분리하기 위한 설계다.

## Operating Principles

- **Contract-first**: 구현보다 `docs/architecture/*_contract.md`의 grain, key, invariant를 우선한다.
- **Point-in-time safety**: Gold는 `selected_release_date < trade_date` 규칙을 지켜 미래 정보 누출을 막는다.
- **Snapshot reproducibility**: 결과는 `decision_date` 및 파티션 기준으로 저장하고, 동일 입력 재실행 시 overwrite로 동일 산출물을 남긴다.
- **Atomic and idempotent writes**: `_tmp_run` 경유 후 atomic rename, 동일 파티션 overwrite를 기본 원칙으로 둔다.
- **Fail-open with explicit UNKNOWN**: 결측이 있어도 schema는 유지하고 downstream에는 `UNKNOWN`을 전달한다.
- **Observability and validation**: lineage, evidence columns, contract tests로 "왜 이 값이 나왔는지"를 추적 가능하게 유지한다.
- **Layer / strategy separation**: 전략 로직은 Gold를 read-only로 소비하며 상위 데이터 레이어를 다시 쓰지 않는다.

## Explicit Non-Goals

- 투자 추천 / 매수·매도 신호 / 수익률 예측 시스템
- LLM 기반 매매 판단 또는 자동 전략 추천
- 초반부터 Kubernetes / microservice / event bus 등 과설계
- 거대한 범용 플랫폼 / multi-agent orchestration
- 자동매매 시스템 자체를 실서비스로 운용하는 것
- 모델 예측 성능이나 수익률 경쟁을 프로젝트 핵심 가치로 내세우는 것

---

## 현재 구현 범위

> ⚠️ 아래 항목은 대부분 **Personal Track (동결)** 자산이다. Observability Track 신규 작업은 [`.agent/REFACTOR_2026Q2.md`](.agent/REFACTOR_2026Q2.md)의 Phase 1~3 일정에 따라 진행된다. Infrastructure(Bronze/Silver/Gold, Calendar)는 두 트랙 공통이다.

* 📊 **데이터 파이프라인 / Airflow ETL** *(Infrastructure — 공유)*

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
  * 단계: Axis Features(4축) → Axis×Horizon(3-state 집약 + detail) → Market Position → Policy Selector → Universe-ETF → Allocation → Sell Advisor
  * 출력 경계: WHAT_TO_HOLD / HOW_MUCH_EXPOSURE / HOW_MUCH_TO_SELL
  * `decision_date` snapshot 저장 및 재현성(멱등 overwrite) 보장
  * Telegram 보고:
    - SIGNAL: `시장 컨텍스트` + `다음 스텝 가설(5/10/20/60/120D bias+hazard+expected)` + `시장 근거 4축` + `전술 그룹 다음 스텝`
    - PAPER_RESULT: `모의계좌 체결 요약 + PnL + 포지션 + 게이트/강도(effective_bias, hard_gate, tactical_strength)` + `전술 적용 근거(그룹 게이트)`
  * Telegram 표기 별칭:
    - `중기 성향` = `mid_regime`
    - `단기 공황 여부` = `is_panic = not risk_gate`
    - `전술 실행` = `run_universe (허용/제한)`
  * Long Engine v1: `delta_6m` rolling z-score 정규화 + `z_threshold=0.3` 운영
  * Mid Engine v1.1: breadth 계산을 `iwm/spy ratio`에서 `iwm-spy spread`로 교체(음수 SPY 구간 부호 반전 버그 수정)
  * Short Engine 보강: `smallcap_stress(iwm_spy_vol_spread > 0.005)` 추가, secondary PANIC 4신호 체계 적용
* 🧪 **Backtest Engine v2 + Walk-Forward**

  * Preset v2(`long_phase × mid_regime` 2D lookup) 지원
  * Walk-Forward 분석 CLI(`window-years`, `step-years`) 및 parquet/json 저장 지원
  * 결과 지표 JSON(`*_metrics.json`) 저장 지원
  * v3 확장: `next_step_signal snapshot` 기반 soft gate allocation 지원
  * v3.1: monthly bias lock 운영
  * v3.2: monthly lock + shock override(PANIC/RISK_OFF streak, cooldown) 운영
  * v3.3: v3.2 + hazard-aware override gate(`transition_hazard_10d`) 운영
  * v3.4: v3.3 + tactical group transition gate(`group_transition_signal`) 운영
  * v3.4.1: v3.4 + recovery-aware re-entry gate(`WEAK>=2` 진입, `RELIEF 2연속`/`MID=RISK_ON` 해제)
  * v3.4.2-phase: v3.4.1 + phase-aware bias state machine(`RECOVERY -> RISK_ON_BIAS`, 월요일 판정, cooldown=5)
  * v3.4.2a: v3.4.2-phase + 체류 규칙 완화(조건부 cooldown 압축 + hard-gate exit assist)
  * 실행 기준 bias는 `bias_20d` 단일 경로 사용(`1m/3m` alias 미사용)
  * 운영 기본 preset: `v3.4.1` (`v3.4.2-phase`, `v3.4.2a`는 실험군)
* 🧾 **Paper Engine (stateful EOD simulation)**
  * `src/pretrend/pipeline/paper/` 모듈에서 운용 시뮬레이션 실행
  * `next_step_signal` 기반 tactical 강도 조절(soft gate) + 하드게이트 우선 적용
  * 운영 입력(KRW: 초기자금/DCA)은 KIS 환율(`fx_usdkrw`) 우선, 결측 시 `PAPER_FX_USDKRW` fallback으로 USD 환산 후 체결 계산
* ♻️ **재현성 저장 체계 (Feature Snapshot + Result Registry)**
  * `next_step_history`(year/month partition, key=`trade_date+decision_date_ref`)로 전이예측 feature 선저장
  * backtest/walk-forward/paper 결과를 표준 아티팩트 + registry(parquet partition)로 저장
  * 동일 조건 비교를 “재실행 없이 조회” 가능하도록 운영
* 📝 **Text Pipeline + LLM Observer**
  * `text_pipeline_dag`: `Bronze -> Silver -> Gold(rule) -> Gold LLM` 4단계 운영
  * Gold LLM은 Ollama 로컬 기반 observer-only 계층이며 `text_annotation_v2` taxonomy 구조를 사용
  * 백필 경로:
    - FOMC Archive / SEC Index Bronze 백필
    - `gold_llm_backfill.py`로 FOMC/SEC Gold LLM 백필
  * SEC EDGAR adapter는 `filings.recent` + `filings.files`를 모두 순회해 과거 filing coverage를 확장
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
> ❌ Text LLM feature는 현재 **Strategy/Paper/Backtest 실행 입력에 직접 연결되지 않는다**. 이 경계는 영구 observer-only 원칙으로 유지한다.
> ❌ 이 저장소는 "AI 투자 에이전트"를 전면에 내세우는 프로젝트가 아니라, 그 이전 단계의 데이터 기반과 운영 계약을 다루는 프로젝트다.

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
Strategy Engine (Axis×Horizon 3-state → Policy → Universe-ETF → Allocation → Sell)
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
pytest -q tests/pipeline/text/
pytest -q tests/pipeline/test_macro_silver_writer.py
```

## 테스트와 CI가 보호하는 약속

이 저장소의 테스트와 CI는 "pytest가 돌아간다"는 사실보다, **데이터 파이프라인의 운영 약속이 깨지지 않았는지**를 확인하는 장치에 가깝다.

- 재실행 시 동일 파티션에 중복 append가 남지 않도록 **idempotent overwrite**를 보호한다.
- Calendar/Gold 계층에서 `selected_release_date < trade_date`가 무너지지 않도록 **point-in-time 규칙**을 보호한다.
- contract test로 레이어별 grain, key, required columns가 흔들리지 않도록 **schema / contract drift**를 막는다.
- `_tmp_run` 이후 atomic rename 패턴이 깨져 partial snapshot이 남지 않도록 **snapshot write safety**를 점검한다.
- Strategy/Paper/Backtest 입력이 Gold snapshot 계약을 벗어나지 않도록 **downstream input boundary**를 보호한다.
- `.github/workflows/ci.yaml`은 `main`, `dev`에 대한 push / pull request 시 `pytest -q`를 실행해 위 회귀를 기본선에서 감시한다.

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
PYTHONPATH=src python -m pretrend.pipeline.strategy_engine.strategy_job --date 2024-06-03 --invested-ratio 0.10 --long-z-threshold 0.3

# 전체 테스트
conda run -n pytest-pretrend pytest tests/ -v
```

### 4.4 Backtest / Walk-Forward 실행

규칙 기반 전이예측(MVP):
- `5/10/20/60/120 거래일` 지평으로 `sojourn_prob`(지속확률) / `transition_hazard`(전환위험도) 산출
- ML 없이 snapshot 확장 필드(nullable)로 제공

```bash
# Backtest preset v2
PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v2

# Walk-Forward (4년 창, 2년 슬라이드)
PYTHONPATH=src python -m pretrend.pipeline.backtest.walk_forward --preset v2 --window-years 4 --step-years 2

# Backtest preset v3 (next_step soft gate)
PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3

# Backtest preset v3.1 (v3 + monthly bias lock)
PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.1

# Backtest preset v3.2 (v3.1 + shock override/cooldown)
PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.2

# Backtest preset v3.3 (v3.2 + hazard-aware override)
PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.3

# Backtest preset v3.4 (v3.3 + tactical group transition gate)
PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.4

# Backtest preset v3.4.1 (v3.4 + recovery-aware re-entry gate)
PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.4.1

# Walk-Forward 저장 (parquet + summary json)
PYTHONPATH=src python -m pretrend.pipeline.backtest.walk_forward --preset v2 --window-years 4 --step-years 2 --save

# Walk-Forward v3.3 (duration/transition diagnostics)
PYTHONPATH=src python -m pretrend.pipeline.backtest.walk_forward --preset v3.3 --window-years 4 --step-years 2
```

결과 저장/비교 원칙:
- `BacktestRunner().run()`만 호출하면 파일이 저장되지 않는다.
- 비교/재현성 용도는 `save_result()`를 포함한 실행으로 아티팩트를 저장해야 한다.
- 권장 경로: `result/backtest_compare/<window>_<YYYYMMDD-YYYYMMDD>/<preset>/`
- 표준 산출물:
  - `*_daily_nav.parquet`, `*_trades.parquet`, `*_summary_metrics.parquet/json`
  - `*_diagnostics.parquet`, `*_final_positions.parquet`, `*_config.json`
  - legacy: `*.parquet`, `*_metrics.json`
- registry:
  - `result/backtest/registry/pipeline=backtest/run_date=YYYY-MM-DD/registry.parquet`
  - `artifact_path`, `run_id`, 기간/버전 메타로 재실행 없이 비교 조회 가능

v2 preset 성과 비교(2006-01 ~ 2024-06, DCA $300/월):

| 엔진 | XIRR | MDD | Sharpe |
| --- | --- | --- | --- |
| v0 | +8.00% | -15.71% | 1.69 |
| v1 | +6.94% | -17.74% | 1.65 |
| v1.1 | +7.25% | -15.65% | 1.68 |

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
  * `strategy_engine_dag.py` (Telegram `SIGNAL`)
  * `paper_trading_dag.py` (Telegram `PAPER_RESULT`, EOD 1회)
  * `paper_trading_dag.py`는 옵션으로 KIS mock broker 실행 경로를 지원
    (`PAPER_BROKER_ENABLED=1`, 기본 `0`)

* 특징:

  * 매 실행 시 **직전월 1일 ~ 전일 롤링 재처리**
  * 파티션 overwrite 기반 멱등성
  * Airflow는 대규모 운영 목적이 아니라, **배치 재현성과 파이프라인 경계 명확화**를 위해 사용
  * Telegram은 동일 채널에서 `SIGNAL`/`PAPER_RESULT`를 `message_type`으로 구분
  * 운영 메시지의 next-step 값은 `next_step_signal snapshot` 단일소스를 사용
    (결측 시 `UNKNOWN/N/A` fail-open 표기)
  * 전이 지평은 거래일 기준 `5/10/20/60/120D`로 고정
  * SIGNAL/PAPER는 상태머신 메타(`bias_state_source/switch/reason/cooldown`)를 함께 표기해 전환 근거를 설명
  * Telegram 전송 실패는 fail-open (경고 로그 후 DAG 성공 유지)
  * Broker 실행 실패도 fail-open (paper 시뮬레이션/알림은 유지)

---

## 5. Codex 사용 정책 (Agent-assisted Dev)

- 모든 작업 전 `AGENTS.md` 규칙을 준수하고, 작은/검토 가능한 diff를 유지한다 (선호: ≤300 LOC).
- `dev`에서 분기한 `codex/<task>` 브랜치로 작업한다.
- 한 번에 하나의 작업만 포함하고, 실행 가능한 검증 명령(예: `pytest -q`, 단일 테스트 파일은 `pytest -q tests/pipeline/<file>.py`)을 제시한다.
- 안정성을 위해 가능하면 범위가 좁은 변경(예: tests-only, docs-only)으로 작업한다.

---

## 5. 문서

* **방향성 / 트랙 분리**: `/docs/architecture/track_separation.md`
* **리팩토링 계획 (Phase 0~3)**: `/.agent/REFACTOR_2026Q2.md`
* 프로젝트 요약: `/docs/project_summary.md`
* 시스템 요약(legacy, Personal Track 운영 중심): `/docs/system_overview.md`
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
  * `/docs/architecture/paper_execution_ledger_contract.md`
  * `/docs/architecture/paper_trading_alert_contract.md`
  * `/docs/market_structure_data_inventory.md`
* 변경 이력: `/docs/changelog.md`

---

## 6. 로드맵

### Observability Track (신규, Phase 0~3)
상세: [`.agent/REFACTOR_2026Q2.md`](.agent/REFACTOR_2026Q2.md)

* [ ] **Phase 0**: PostgreSQL + TimescaleDB 도입, `docker-compose.yml`, `src/pretrend/models/`, Alembic 초기화
* [ ] **Phase 1**: `axis_features` → `observability/regime/axis/` 추출 (첫 타깃), `axis_horizon_state`, `market_position` 이전
* [ ] **Phase 2**: `observability/similarity/` 신설, `observability/explainability/` 신설, `apps/api/` (FastAPI), Parquet → Postgres sync DAG, **Cloudflare Tunnel** (로컬 외부 노출)
* [ ] **Phase 3**: `apps/web/` React Dashboard (heatmap, regime timeline, similarity replay)
* [ ] **Phase 4 (가정)**: 외부 사용자/가용성 요구 시 AWS RDS / Fargate 재이주 검토

### Infrastructure (공유, 완료)
* [x] FRED Macro Bronze Ingest
* [x] Macro Silver Feature
* [x] EOD Bronze Ingest (Observability SOT 32 ETFs)
* [x] EOD Silver Feature
* [x] Calendar Pipeline v1 (econ_events + fred_vintages)
* [x] Gold Macro Feature v1
* [x] Gold EOD Feature v1
* [x] Airflow DAG 기반 통합 파이프라인

### Personal Track (동결, 운영 중단)
* [x] Strategy Engine v0/v1/v2/v3.x
* [x] Backtest Engine + Walk-Forward
* [x] Paper Engine + KIS mock broker

### 명시적 Out-of-Scope
* Kubernetes / microservice / event bus
* 자동매매 실서비스 운용
* AI 매수/매도 추천

---

> 📌 본 프로젝트는 **개인 연구 및 production-grade runtime ownership 학습용**입니다.
> **시장 구조를 관측·설명하는 observability runtime을 운영하기 위한 프로젝트**이며,
> **실거래, 실자금 운용, 외부 서비스 제공을 수행하지 않습니다.**

---

## Interview Summary (1-minute)

- 본 프로젝트는 자동매매나 모델 성능을 전면에 두지 않는다.
- 핵심은 시장 구조를 production-grade로 관측·설명하는 **observability runtime**을 운영하는 것이다.
- 두 트랙 분리: Observability Track(신규, 본진) + Personal Track(기존 자산, 동결).
- 우선순위: ingestion reliability → reproducibility → observability → runtime stability → explainability → dashboard → AI summary (AI는 항상 후순위).
