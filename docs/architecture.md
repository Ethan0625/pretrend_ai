# Pretrend 아키텍처 문서 (reference)

Markers: architecture, legacy
Status: reference

**프로젝트:** Pretrend — Reproducible Market Data Platform\
**문서:** architecture reference\
**버전:** 2026.05.16\

> ⚠️ **참고 문서**
>
> 본 문서는 초기 아키텍처와 데이터 파이프라인 설계 의도를 보존한 reference입니다.
> 현재 공개 진입점은 [`docs/system_overview.md`](system_overview.md)이며, 현재 운영 구조는
> [`docs/architecture/system_map_2026q2.md`](architecture/system_map_2026q2.md)와
> [`docs/architecture/runtime_flow.md`](architecture/runtime_flow.md)를 우선합니다.
>
> 이 문서 안의 strategy/backtest/paper-trading 서술은 historical implementation context로 읽고,
> 현재 공개 운영 표면이나 투자 시스템 설명으로 해석하지 않습니다.

본 문서는 현재 구현된 **Macro/EOD/Calendar 파이프라인 및 Gold Feature Mart(Macro/EOD)**를 중심으로 설명하고,
초기 전략 실험 구조를 함께 기록한다. 현재 플랫폼의 운영 컴포넌트(`observability/`, `src/pretrend/api`, `apps/web`)는 위 신규 문서를 참조한다.

---

## 1. 아키텍처 개요

### 1.1 시스템 구성 요소

[표] 전체 구성요소 개요

| 레이어       | 컴포넌트                         | 설명 |
|-------------|-----------------------------------|------|
| 데이터       | Bronze / Silver / Meta           | 외부 데이터 수집, 정규화, Feature 생성 |
| 파이프라인   | `pretrend.pipeline.*`            | Ingest, Feature 변환, Calendar 증거 파이프라인, (향후) Label/Train |
| 전략 상태판단 | Market Structure (Long/Mid/Short + Composer) | 4축 상태 해석 및 실행 게이트 생성 |
| 전략 실행엔진 | Strategy Engine v0 | WHAT/EXPOSURE/SELL 경계 출력 생성 |
| 시뮬레이션 | Backtest Engine (v0/v1/v2 preset) | Strategy Engine 출력 기반 주간 실행 시뮬레이션(DCA + staged sell) |
| 실행 제어    | Universe-ETF + Allocation Engine  | 후보 선별 및 총 투자 비율 조절(`invested_ratio`) |
| API         | `src/pretrend/api/` (FastAPI)    | 시장 구조 관측 API와 report 분석 endpoint 제공 |
| LLM/분석 호출 | 외부 API 또는 Codex binary        | 설명문/report text 생성. 기본 Docker runtime의 필수 GPU 의존성은 아님 |
| 오케스트레이션 | Airflow DAG | Macro/EOD 등 ETL 파이프라인 스케줄링 및 재처리 |
| 배포/운영    | Docker / (향후) Kubernetes / CI  | 컨테이너화, CI/CD, 모니터링/로깅 |

---

### 1.2 상위 아키텍처 다이어그램

[그림] 상위 시스템 아키텍처

```mermaid
flowchart LR
    subgraph External[외부 데이터 소스]
        FRED[FRED Macro API]
        EOD[주가 EOD / ETF / 종목기본]
        NEWS[뉴스/공시/정책 데이터]
    end

    subgraph DataLayer[데이터 레이어]
        BZ[Bronze\n(Raw 정규화)]
        SV[Silver\n(Feature 변환)]
        BC[Bronze Calendar\n(release evidence)]
        SC[Silver Calendar\n(PIT evidence)]
        GD[Gold / Mart\n(Macro/EOD v1 구현)]
    end

    subgraph Pipeline[파이프라인 코드]
        INGEST[pretrend.pipeline.ingest.*]
        FEAT[pretrend.pipeline.features.*]
        MS[Market Structure\nlong/mid/short + composer]
        UNI[Universe-ETF]
        ALLOC[Allocation Engine v0]
        BT[Backtest Engine]
    end

    subgraph App[애플리케이션 레이어]
        API[FastAPI Backend\nsrc/pretrend/api]
        LLM[LLM/Codex analyzer\noptional]
    end

    subgraph Orchestration[오케스트레이션/배포]
        AF[Airflow DAG]
        CI[GitHub Actions\nCI/CD]
        DC[Docker / K8s]
    end

    External --> INGEST --> BZ
    BZ --> FEAT --> SV
    INGEST --> BC --> SC --> GD
    GD --> MS --> UNI --> ALLOC --> API
    ALLOC --> BT
    UNI --> BT
    LLM --> API

    AF --> INGEST
    AF --> FEAT
    API --> DC
    LLM --> DC
    CI --> DC
````

Calendar Pipeline(v1) 설명:
- `pretrend.pipeline.calendar.*`는 Gold PIT-safe 조인을 위한 release evidence 레이어를 제공한다.
- 구현 모듈: `config.py`, `econ_events.py`, `fred_vintages.py`, `runner.py`
- 저장 흐름: `data/bronze/calendar/*` → `data/silver/calendar/*`

EOD Observability Set(v1) 설명:
- EOD 관측용 ETF 세트는 시장 상태를 읽기 위한 Always-on 센서 입력으로 유지한다.
- Universe-ETF/Universe-Stock(U0~U3) 대상과 분리하여 고정 수집/고정 라벨 정책을 적용한다.
- 분류 라벨(`asset_group`, `asset_name`, `asset_subtype`)은 Bronze에서 확정하고 Silver/Gold로 전파한다.
- 상세 계약 문서: `docs/architecture/eod_observability_contract.md`

EOD Gold Feature v1 설명:
- `pretrend.pipeline.features.gold_eod_features`가 Silver EOD를 Gold Fact Mart로 변환한다.
- `pretrend.pipeline.eod_job`은 Bronze → Silver → Gold를 1회 실행으로 동기화한다.
- `eod_pipeline_dag`는 `run_eod_bronze_ingest` → `run_eod_silver_features` → `run_eod_gold_features` 체인으로 동작한다.

Risk-Control 전략 구조(v0) 설명:
- 전략 흐름은 `Layer -> Market Structure(4축) -> Composer -> Universe-ETF -> Allocation Engine -> Weekly Report`를 따른다.
- Allocation Engine v0는 총 투자 비율(`invested_ratio`)만 조절하며, Universe-ETF 내부 가중치 조절은 수행하지 않는다.
- Strategy Engine v0는 Gold snapshot 입력을 기준으로 WHAT/EXPOSURE/SELL 경계 출력을 생성한다.
- 관련 문서:
  - `docs/architecture/strategy_architecture.md`
  - `docs/architecture/strategy_engine_design.md`
  - `docs/architecture/market_structure_long_contract.md`
  - `docs/architecture/market_structure_mid_contract.md`
  - `docs/architecture/market_structure_short_contract.md`
  - `docs/architecture/market_structure_composer_contract.md`
  - `docs/architecture/universe_contract.md`
  - `docs/architecture/allocation_engine_contract.md`
  - `docs/data/market_structure_data_inventory.md`

Backtest Engine(v0/v1/v2) 설명:
- `pretrend.pipeline.backtest.*`는 Strategy Engine 출력과 Gold snapshot을 입력으로 포트폴리오 시뮬레이션을 수행한다.
- Preset 기반 동작:
  - v0: range-maintenance
  - v1: target-seeking
  - v2: 2D target-seeking(`long_phase × mid_regime`)
- 실행 규칙:
  - 월 첫 거래일 DCA 자금 투입(`monthly_addition`)
  - 월요일(T-1 신호 평가) → 화요일(INCREASE 실행) → 금요일(DECREASE 단계 매도)
  - `risk_gate=false(PANIC)` 시 DECREASE 생성/진행을 동결하고 INCREASE는 허용
- 구현 모듈: `config.py`, `portfolio.py`, `rebalancer.py`, `runner.py`, `metrics.py`, `report.py`

---

## 2. 디렉토리 구조 및 레이어 정의

### 2.1 코드 / 데이터 디렉토리 구조

[그림] 코드 및 데이터 디렉토리 구조

```text
pretrend_ai/
├─ data/
│  ├─ bronze/
│  │  ├─ macro/
│  │      └─ econ_indicators/
│  │          └─ year=YYYY/month=MM/*.parquet
│  │  └─ calendar/
│  │      ├─ econ_events/
│  │      │   └─ year=YYYY/month=MM/*.parquet
│  │      └─ fred_vintages/
│  │          └─ year=YYYY/month=MM/*.parquet
│  ├─ silver/
│  │  ├─ macro/
│  │      └─ macro_features/
│  │          └─ year=YYYY/month=MM/*.parquet
│  │  └─ calendar/
│  │      ├─ econ_events/
│  │      │   └─ year=YYYY/month=MM/*.parquet
│  │      └─ fred_vintages/
│  │          └─ year=YYYY/month=MM/*.parquet
│  └─ meta/
│
├─ src/
│  └─ pretrend/
│      ├─ pipeline/
│      │   ├─ ingest/
│      │   │   ├─ base.py        # IngestContext / BaseFetcher / BaseNormalizer / BaseWriter
│      │   │   └─ macro.py       # FRED Macro Bronze Ingest (+ Calendar Bronze ingest)
│      │   ├─ features/
│      │       ├─ macro_features.py  # Macro Silver Feature 변환
│      │       ├─ eod_features.py  # EOD Silver Feature 변환
│      │       ├─ gold_macro_features.py  # Gold Macro Feature v1 변환
│      │       └─ gold_eod_features.py  # Gold EOD Feature v1 변환
│      │   └─ calendar/
│      │       ├─ config.py          # CalendarConfig / schema constants / mappings
│      │       ├─ econ_events.py     # Calendar econ_events Silver 변환
│      │       ├─ fred_vintages.py   # Calendar fred_vintages Silver 변환
│      │       └─ runner.py          # Calendar Silver runner CLI
│      │   └─ eod_job.py             # EOD Bronze→Silver→Gold E2E runner
│      │   └─ strategy_engine/       # Strategy Engine v0 (Axis/Horizon→Policy→Universe-ETF→Allocation→Sell)
│      │       ├─ strategy_job.py    # Strategy Engine runner CLI
│      │       ├─ config.py          # Strategy policy/profile config
│      │       ├─ io.py              # snapshot load/write
│      │       └─ ...                # axis_features / horizon_state / composer / universe / allocation / sell
│      │   └─ backtest/              # Backtest Engine (v0/v1/v2 preset, DCA/weekly execution)
│      │       ├─ config.py          # BacktestPreset / PRESET_REGISTRY / from_preset
│      │       ├─ portfolio.py       # Position/Trade/Portfolio
│      │       ├─ rebalancer.py      # target weights / rebalance day / tactical rotation
│      │       ├─ runner.py          # BacktestRunner CLI
│      │       ├─ metrics.py         # CAGR/MDD/Sharpe/Sortino/Calmar
│      │       └─ report.py          # 구간별 리포트 출력
│      ├─ signals/               # 전략/신호 모듈 (향후)
│      ├─ llm/                   # LLM/RAG 모듈 (향후)
│      ├─ config/                # 설정/스키마 (향후)
│      └─ utils/                 # 공통 유틸 (향후)
│
├─ docker/                       # 역할별 Dockerfile
├─ requirements/                 # 역할별 Python 의존성
├─ docker-compose.yml            # 기본 로컬 runtime 진입점
└─ tests/                        # 운영 계약/단위 테스트
```

---

### 2.2 데이터 레이어 정의

[표] 데이터 레이어 정의

| 레이어    | 목적                             | 예시 데이터                           | 저장 위치                |
| ------ | ------------------------------ | -------------------------------- | -------------------- |
| Bronze | 외부 데이터 수집 후 *표준 스키마*로 정규화된 Raw | FRED Macro, EOD, 뉴스 Raw          | `data/bronze/...`    |
| Silver | 전략/모델 입력용 Feature 세트           | Macro Feature (YoY/MoM/Regime 등) | `data/silver/...`    |
| Gold   | 특정 전략/리포트에 최적화된 Mart           | Macro Gold Feature v1 (구현), 전략별 시그널/백테스트(확장) | `data/gold/...` |
| Meta   | Job 실행 메타데이터, Lineage          | run_id, ingestion_ts, 로그 등       | `data/meta/...`      |

현재 구현 상태:

* ✅ Bronze: Macro (FRED 기반 econ_indicators)
* ✅ Silver: Macro Features (macro_features)
* ✅ Bronze/Silver: Calendar release evidence (`econ_events`, `fred_vintages`)
* ✅ Gold: Macro Feature v1 (Silver Macro + Calendar 기반)
* ✅ Gold: EOD Feature v1 Fact Mart (Silver EOD 기반)
* ⏳ Gold 확장: 전략별 Mart

---

### 2.3 Data Storage Strategy

- 현재 구현 단계에서는 파일 기반 스토리지(Parquet)를 사용한다.
- 데이터 레이어별 저장 전략:
  - Bronze: Raw 데이터 보존용 Parquet
  - Silver: Feature 재생성 가능 Parquet (멱등 overwrite)
  - Gold: 전략별 Mart (초기에는 Parquet, 향후 DB 전환)
- 파일 스토리지는:
  - 파이프라인 중간 산출물
  - 재처리 및 백필(backfill) 용도
  로 사용된다.

향후 확장:
- Gold Layer는 DB(예: PostgreSQL / ClickHouse) 기반으로 이전 가능하도록 설계한다.
- Silver Feature는 Feature Store로 전환 가능성을 열어둔다.

---

## 3. Macro Bronze Ingest 아키텍처

### 3.1 IngestContext & Base 추상화

[코드] IngestContext & Base 클래스 요약

```python
@dataclass
class IngestContext:
    domain: str                 # macro / theme / stock / ...
    dataset: str                # econ_indicators / ...
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    output_root: Path = Path("data/bronze")
    meta_root: Path = Path("data/meta")
    ingestion_ts: pd.Timestamp = field(default_factory=pd.Timestamp.utcnow)
```

* `BaseFetcher`: 외부 API/파일에서 Raw DataFrame 수집
* `BaseNormalizer`: Raw → 표준 스키마 변환
* `BaseWriter`: Parquet 저장 + 메타 기록

이 패턴은 다른 데이터 소스(EOD/뉴스/섹터 등)에도 재사용된다.

---

### 3.2 FRED Macro Fetcher/Normalizer/Writer

[그림] Macro Bronze Ingest 플로우

```mermaid
flowchart LR
    C[IngestContext\n(domain=macro, dataset=econ_indicators)]
    F[MacroFetcher\n(FRED API)]
    N[MacroNormalizer\n표준 스키마 변환]
    W[MacroWriter\nParquet 저장]

    C --> F --> N --> W

    subgraph FRED_API[외부: FRED API]
        S1[CPIAUCSL]
        S2[CPILFESL]
        S3[UNRATE]
        S4[FEDFUNDS]
        S5[DGS10]
    end

    FRED_API --> F
```

#### 3.2.1 Fetcher

* 클래스: `MacroFetcher`

* 설정: `FredMacroConfig.from_env_with_defaults()`

* 수집 대상 시리즈:

  * `CPIAUCSL` → `CPI_US_ALL_ITEMS_SA`
  * `CPILFESL` → `CPI_US_CORE_SA`
  * `UNRATE` → `US_UNEMPLOYMENT_RATE`
  * `FEDFUNDS` → `US_FED_FUNDS_RATE`
  * `DGS10` → `US_TREASURY_10Y_YIELD`

* Fetch 결과 스키마 (Raw):

```text
date: str
value: str
indicator_id: str
unit: str
source: str = "FRED"
series_id: str              # FRED 원본 series_id
```

#### 3.2.2 Normalizer

* 클래스: `MacroNormalizer`
* 역할: 타입 정리 + 표준 스키마 매핑

변환 후 스키마:

```text
indicator_id: str           # 내부 지표 ID
date: date
value: float
unit: str
source: str
run_id: str
ingestion_ts: timestamp
```

#### 3.2.3 Writer

* 클래스: `MacroWriter`
* 저장 경로:

```text
{output_root}/{domain}/{dataset}/year=YYYY/month=MM/{indicator_id}_YYYYMM.parquet

예) data/bronze/macro/econ_indicators/year=2015/month=01/CPI_US_ALL_ITEMS_SA_201501.parquet
```

* 파티션 키: `(year, month, indicator_id)`
* **멱등성**:

  * 비즈니스 키: `(indicator_id, date)`
  * 동일 `(domain, dataset, start_date, end_date)`로 재실행 시
    → 해당 기간의 연/월 Parquet 파일이 덮어쓰기 되므로, 데이터 내용은 논리적으로 동일 유지.

---

## 4. Macro Silver Feature Layer 아키텍처

### 4.1 목적

Bronze Macro 지표(`econ_indicators`)를 기반으로:

* 전략/시그널에서 바로 사용할 수 있는 **Macro Feature 세트** 생성
* 예: 인플레이션 레짐, 노동시장 레짐, 금리 사이클, 장단기 금리 역전 여부 등

---

### 4.2 Silver Feature 구성

[표] Macro Feature 요약

| Indicator     | Feature                                                            | 설명                                             |
| ------------- | ------------------------------------------------------------------ | ---------------------------------------------- |
| CPI, Core CPI | `yoy`, `mom`, `rolling_3m`, `rolling_12m`, `regime`                | 인플레이션 레짐 (high/elevated/moderate/disinflation) |
| UNRATE        | `level`, `delta_3m`, `regime`                                      | 노동시장 타이트/완화 상태                                 |
| FEDFUNDS      | `level`, `delta_3m`, `delta_12m`, `regime`                         | 금리 사이클 (hiking/cutting/paused)                 |
| DGS10         | `level`, `spread_to_fedfunds`, `is_yield_curve_inverted`, `regime` | 장단기 금리 역전/정상 상태                                |

공통 Feature:

* `yoy` = `value / value_12m_ago - 1`
* `mom` = `value / value_1m_ago - 1`
* `rolling_3m` = 3개월 이동평균
* `rolling_12m` = 12개월 이동평균

---

### 4.3 Silver Pipeline 구성

[그림] Bronze → Silver Macro Feature 파이프라인

```mermaid
flowchart LR
    subgraph Bronze[Bronze Layer]
        BZ[(econ_indicators\nindicator_id, date, value, ...)]
    end

    subgraph SilverPipeline[Silver Macro Feature Pipeline]
        R[load_bronze_macro\n(Bronze Reader)]
        CF[add_common_features\n(yoy, mom, rolling)]
        IR[apply_inflation_regime]
        UR[apply_unrate_features]
        FR[apply_fedfunds_features]
        DG[apply_dgs10_features]
        WR[write_silver_macro_features]
    end

    subgraph Silver[Silver Layer]
        SV[(macro_features\nFeature set)]
    end

    BZ --> R --> CF --> IR --> UR --> FR --> DG --> WR --> SV
```

* 모듈: `src/pretrend/pipeline/features/macro_features.py`
* 실행 컨텍스트: `MacroFeatureRunContext`

  * `start_date`, `end_date`, `run_id`, `ingestion_ts`, `cfg`
  * `lookback_months`: YoY / rolling feature 계산을 위한 과거 로드 기간 (기본 12개월)

**Silver 저장 구조**

```text
data/silver/macro/macro_features/
└─ year=YYYY/
   └─ month=MM/
      └─ macro_features_YYYYMM.parquet
```

* 파티션 키: `(year, month)`
* 하나의 파일에 해당 월의 **모든 indicator row** 포함

---

### 4.4 Silver 멱등성 전략

* 논리적 키: `(indicator_id, date)`
* 실행 파라미터: `--start`, `--end`
* 절차:

  1. Bronze에서 `[start_date, end_date]` 범위의 데이터 로드
  2. Feature 계산 후, 이 데이터가 포함하는 `(year, month)` 파티션 집합 계산
  3. 각 파티션에 대해:

     * 임시 디렉토리(`_tmp_run=...`)에 Parquet 저장
     * 기존 `macro_features_YYYYMM.parquet` 삭제
     * 임시 파일을 최종 파일로 rename
  4. 동일 파라미터로 재실행 시, 동일 파티션이 **완전히 교체**되므로 항상 동일 결과 유지

  * 이 전략을 통해 일시적 수집 실패나 실행 누락이 발생하더라도, 이후 실행에서 동일 기간을 재처리함으로써 데이터 정합성을 복구할 수 있다.

---

### 4.5 실행 예시

[코드] Silver Macro Feature 생성

```bash
# Bronze Macro가 이미 생성되어 있어야 함
PYTHONPATH=src python -m pretrend.pipeline.features.macro_features \
  --start 2010-01-01 \
  --end 2025-12-01
```

---

## 5. 애플리케이션 / LLM / 오케스트레이션 (개요)

### 5.1 FastAPI 백엔드

* 경로: `backend_api/app/main.py`
* 역할:

  * 시장 구조 관측 API
  * report 분석 요청 endpoint
  * 프론트엔드/대시보드(향후) 연동용 BFF 역할

---

### 5.2 LLM/분석 호출

기본 Docker runtime은 GPU 추론 서버를 포함하지 않는다. Report 분석은 외부 API 또는 Codex binary 호출 방식으로 연결한다.

* 역할:

  * Macro/EOD 데이터를 기반으로 한 explanation/report text 생성
  * 관측 결과 요약과 자연어 해석

---

### 5.3 오케스트레이션 / 배포 (계획)

* Airflow DAG:

  * `macro_pipeline_dag`: Macro Bronze → Silver 통합 파이프라인
  * 매일 트리거 + 롤링 재처리 정책 적용
* CI/CD:

  * GitHub Actions (`.github/workflows/ci.yml`)
  * 테스트 / Lint / Docker Build 수행
* 배포:

  * 1단계: Docker Compose 기반 단일 노드 배포
  * 2단계: Kubernetes 전환 검토(API / Airflow / 선택적 분석 worker 분리)

---

## 6. 관측 런타임 아키텍처

본 섹션은 현재 운영 표면인 market data platform과 read-only 관측 API의 아키텍처를 요약한다.
상세 운영 구조는 [`architecture/system_map_2026q2.md`](architecture/system_map_2026q2.md),
[`architecture/runtime_flow.md`](architecture/runtime_flow.md),
[`operation/reproducible_runtime_contract.md`](operation/reproducible_runtime_contract.md)를 우선한다.

### 6.1 신규 컴포넌트

```
src/pretrend/
├── pipeline/                # Infrastructure (공유, 본 문서 §1~§5 참조)
├── observability/           # 신규 — 시장 관측 자료
│   ├── regime/              # axis_features, market_position 등 market state features
│   ├── similarity/          # 과거 시장 구조 유사도
│   └── explainability/      # LLM 설명 layer (관측 only)
├── models/                  # SQLAlchemy + Pydantic Base
└── config.py                # 환경 / DB 설정 중앙화

apps/                        # 신규
├── api/                     # FastAPI
└── web/                     # React + Vite

migrations/                  # Alembic + TimescaleDB schema
docker-compose.yml           # Postgres + API + Airflow profiles
docker/                      # API/dev/Airflow Dockerfile
requirements/                # API/CI/Airflow requirements
```

### 6.2 데이터 흐름 (Observability)

```
Bronze/Silver/Gold (Parquet)  ─┐
                              │  Parquet → Postgres sync DAG
                              ▼
                  PostgreSQL + TimescaleDB
                              │
                              ▼
                          FastAPI
                              │
                              ▼
                     React Dashboard
                              │
                              ▼
                  Dashboard / external access if needed
```

### 6.3 로드맵 상태

- **P17 Foundation**: Docker Compose Postgres + TimescaleDB, `config.py`, `models/`, Alembic 베이스라인, 레이아웃 문서 완료
- **P18-P22 Regime modules**: `observability/regime/` 중심 market state modules 정리 완료
- **P24-P29 Serving layer**: Postgres schema, sync DAG, similarity, explainability, FastAPI, stage gate 완료
- **P30 Runtime preflight**: Docker runtime, Airflow 2 profile, volume/restore/backfill contract 완료
- **Phase 3**: React Dashboard (heatmap, regime timeline, similarity replay)
- **Phase 4 (가정)**: 외부 사용자 / 가용성 요구 발생 시 managed DB/runtime 검토

### 6.4 보관된 전략 실험 맥락

본 문서 §1~§5가 설명하는 Strategy Engine / Backtest / Paper / Broker 영역은 초기 실험 구현의 기록이다.
현재 공개 운영 표면은 재현 가능한 market data platform이며, archived strategy module은 운영 목표나 투자 성과 주장으로 해석하지 않는다.

---

## 7. 결론

본 프로젝트는 **재현 가능한 market data platform**이다.
- **Infrastructure(Bronze/Silver/Gold) 데이터 레이어**: PIT-safe feature SOT를 제공한다.
- **관측 표면**: 시장 상태를 구조적으로 관측·설명하는 read-only API와 dashboard를 제공한다.
- **보관된 전략 실험**: 초기 구현 맥락으로 보존되며 현재 공개 운영 목표가 아니다.

진짜 목표는 "수익률 경쟁"이 아니라 **"production-grade runtime ownership 경험"** 학습이며, 모든 아키텍처 결정은 이 우선순위에 따라 정렬된다.
