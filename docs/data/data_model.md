# 데이터 모델

Markers: architecture, contract
Status: active

**프로젝트:** Pretrend — Reproducible Market Data Platform  
**문서:** Data Model  
**버전:** 2026.05.16  
**목적:** Raw 수집 결과부터 Bronze/Silver/Gold Parquet SOT, Postgres serving mirror까지의 데이터 구조를 정의한다.

이 문서는 현재 운영 중인 market data platform의 저장 구조와 schema contract를 요약한다. 세부 계산식은 각 architecture contract에 두고, 여기서는 저장 위치, grain, key, partition, 주요 컬럼, serving table 관계를 고정한다.

참조:

- [`data_requirements.md`](data_requirements.md)
- [`data_ingest_datasources.md`](data_ingest_datasources.md)
- [`../architecture/gold_design_contract.md`](../architecture/gold_design_contract.md)
- [`../architecture/gold_postgres_schema.md`](../architecture/gold_postgres_schema.md)
- [`../architecture/pipeline_window_policy.md`](../architecture/pipeline_window_policy.md)
- [`../operation/reproducible_runtime_contract.md`](../operation/reproducible_runtime_contract.md)

---

## 1. 전체 흐름

현재 운영 구조는 다음 순서를 따른다.

```text
External raw source
  -> Bronze Parquet
  -> Silver Parquet
  -> Gold Parquet SOT
  -> Postgres serving mirror/cache
  -> FastAPI read-only API
```

원칙:

- Bronze는 외부 source의 원천 값을 보존하되, 파이프라인이 반복 처리할 수 있도록 최소 정규화한 layer다.
- Silver는 feature 계산과 품질 flag를 포함한 재사용 layer다.
- Gold는 point-in-time 안전한 feature layer의 Parquet SOT다.
- Postgres는 API serving mirror다. Gold Parquet을 대체하는 원천이 아니라 조회 최적화와 cache를 위한 runtime mirror다.
- `PRETREND_DATA_ROOT`와 container 내부 `/app/data`가 file data lake 기준 경로다.

---

## 2. Layer별 역할

| Layer | 저장소 | 역할 | 복구 기준 |
| --- | --- | --- | --- |
| External raw | FRED, yfinance 등 외부 API | source payload | 재수집 |
| Bronze | `data/bronze/...` | raw-preserving normalized Parquet | backfill 또는 rolling ingest |
| Silver | `data/silver/...` | feature/quality/calendar 정규화 | Bronze에서 재생성 |
| Gold | `data/gold/...` | PIT-safe feature Parquet SOT | Silver에서 재생성 |
| Postgres mirror | `pretrend_obs` | API serving, similarity, explainability cache | dump restore 우선, 필요 시 Gold sync |
| Metadata | `data/meta/...`, `airflow_pretrend/...` | backfill marker, job log, Airflow metadata | 런타임별 재생성 가능 |

---

## 3. Data Lake 디렉토리 구조

현재 운영 대상 경로:

```text
data/
├─ bronze/
│  ├─ macro/econ_indicators/year=YYYY/month=MM/{indicator_id}_YYYYMM.parquet
│  ├─ calendar/econ_events/year=YYYY/month=MM/econ_events_YYYYMM.parquet
│  ├─ calendar/fred_vintages/year=YYYY/month=MM/fred_vintages_YYYYMM.parquet
│  └─ eod/daily_prices/source=YF/theme=GENERIC/symbol=SPY/trade_date=YYYY-MM-DD/eod.parquet
├─ silver/
│  ├─ macro/macro_features/year=YYYY/month=MM/macro_features_YYYYMM.parquet
│  ├─ calendar/econ_events/year=YYYY/month=MM/econ_events_YYYYMM.parquet
│  ├─ calendar/fred_vintages/year=YYYY/month=MM/fred_vintages_YYYYMM.parquet
│  └─ eod/eod_features/symbol=SPY/year=YYYY/month=MM/eod_features_YYYYMM.parquet
├─ gold/
│  ├─ macro/macro_features/year=YYYY/month=MM/gold_macro_features_YYYYMM.parquet
│  └─ eod/eod_features/symbol=SPY/year=YYYY/month=MM/gold_eod_features_YYYYMM.parquet
└─ meta/
   ├─ macro_job_log.parquet
   └─ bootstrap_backfill_once.json
```

파티션 overwrite가 기본 멱등성 전략이다. EOD는 `(symbol, year, month)` 또는 `trade_date` 단위 partition을 사용하고, Macro/Calendar는 `(year, month)` partition을 사용한다.

처리/재처리 윈도우는 데이터 구조와 별도 운영 계약이다. Scheduled pipeline은 [`../architecture/pipeline_window_policy.md`](../architecture/pipeline_window_policy.md)의 윈도우를 기준으로 파일 후보를 먼저 partition 단계에서 좁힌 뒤 parquet를 읽는다.

Canonical root:

| Dataset | Root |
| --- | --- |
| Macro Bronze | `data/bronze/macro/econ_indicators` |
| Calendar econ events Bronze | `data/bronze/calendar/econ_events` |
| Calendar FRED vintages Bronze | `data/bronze/calendar/fred_vintages` |
| EOD Bronze | `data/bronze/eod/daily_prices` |
| Macro Silver | `data/silver/macro/macro_features` |
| Calendar econ events Silver | `data/silver/calendar/econ_events` |
| Calendar FRED vintages Silver | `data/silver/calendar/fred_vintages` |
| EOD Silver | `data/silver/eod/eod_features` |
| Macro Gold | `data/gold/macro/macro_features` |
| EOD Gold | `data/gold/eod/eod_features` |

---

## 4. Grain과 Key

| Dataset | Layer | Grain | Key 또는 dedup 기준 |
| --- | --- | --- | --- |
| `macro/econ_indicators` | Bronze | 지표-관측일 | `(indicator_id, date)` |
| `macro/macro_features` | Silver | 지표-관측일 | `(indicator_id, date)` |
| `calendar/econ_events` | Bronze/Silver | 지표-관측월 release evidence | `(indicator_id, observation_date)` |
| `calendar/fred_vintages` | Bronze | FRED series-관측일-vintage | `(series_id, observation_date, vintage_date)` |
| `calendar/fred_vintages` | Silver | 지표-관측일-vintage | `(indicator_id, observation_date, vintage_date)` |
| `eod/daily_prices` | Bronze | 심볼-거래일 | `(source, theme, symbol, trade_date)` |
| `eod/eod_features` | Silver/Gold | 심볼-거래일 | `(symbol, trade_date)` |
| `gold/macro/macro_features` | Gold | 지표-거래일 as-of snapshot | `(indicator_id, trade_date)` |
| `gold/eod/eod_features` | Gold | 심볼-거래일 fact mart | `(symbol, trade_date)` |
| `gold_market_state_similarity_feature` | Postgres | 거래일별 고정폭 similarity feature | `trade_date` |
| `similarity_regime`, `similarity_gold` | Postgres | query-neighbor pair | `(query_date, neighbor_date)` |
| `explainability_cache` | Postgres | use case별 report cache | `(use_case, query_date, model_id, prompt_version)` |

---

## 5. Bronze Schema

### 5.1 Macro Bronze

경로:

```text
data/bronze/macro/econ_indicators/year=YYYY/month=MM/{indicator_id}_YYYYMM.parquet
```

주요 컬럼:

| 컬럼 | 의미 |
| --- | --- |
| `indicator_id` | 내부 지표 ID |
| `date` | FRED observation date |
| `value` | numeric value |
| `unit` | 단위 |
| `source` | source name, 기본 `FRED` |
| `run_id` | ingest 실행 ID |
| `ingestion_ts` | ingest timestamp |

현재 기본 지표:

| FRED series | 내부 `indicator_id` |
| --- | --- |
| `CPIAUCSL` | `CPI_US_ALL_ITEMS_SA` |
| `CPILFESL` | `CPI_US_CORE_SA` |
| `UNRATE` | `US_UNEMPLOYMENT_RATE` |
| `FEDFUNDS` | `US_FED_FUNDS_RATE` |
| `DGS10` | `US_TREASURY_10Y_YIELD` |

### 5.2 Calendar Bronze

`econ_events` 경로:

```text
data/bronze/calendar/econ_events/year=YYYY/month=MM/econ_events_YYYYMM.parquet
```

컬럼:

```text
indicator_id, observation_date, release_ts_utc, release_date_local,
source, run_id, ingestion_ts
```

`fred_vintages` 경로:

```text
data/bronze/calendar/fred_vintages/year=YYYY/month=MM/fred_vintages_YYYYMM.parquet
```

컬럼:

```text
series_id, observation_date, vintage_date, value, source, run_id, ingestion_ts
```

Calendar Bronze는 Gold Macro의 PIT-safe release evidence를 만들기 위한 raw evidence layer다.

### 5.3 EOD Bronze

경로:

```text
data/bronze/eod/daily_prices/source=YF/theme=GENERIC/symbol=SPY/trade_date=YYYY-MM-DD/eod.parquet
```

컬럼:

```text
symbol, theme, source, trade_date,
open, high, low, close, adj_close, volume, currency,
asset_group, asset_name, asset_subtype,
run_id, ingestion_ts
```

EOD Bronze는 yfinance OHLCV raw 값을 보존하고, Observability symbol SOT 기반 `asset_group`, `asset_name`, `asset_subtype` label을 함께 고정한다.

---

## 6. Silver Schema

### 6.1 Macro Silver

경로:

```text
data/silver/macro/macro_features/year=YYYY/month=MM/macro_features_YYYYMM.parquet
```

컬럼:

```text
indicator_id, date, value,
yoy, mom, rolling_3m, rolling_12m,
regime, level, delta_3m, delta_12m,
spread_to_fedfunds, is_yield_curve_inverted,
ingestion_ts
```

Macro Silver는 지표별 공통 변화율, rolling 값, regime 보조값을 계산한다.

### 6.2 Calendar Silver

`econ_events` 컬럼:

```text
indicator_id, observation_date, release_ts_utc, release_date_utc,
source, has_timestamp, run_id_silver, ingestion_ts_silver
```

`fred_vintages` 컬럼:

```text
indicator_id, observation_date, vintage_date, is_first_vintage,
source, run_id_silver, ingestion_ts_silver
```

Calendar Silver는 Gold Macro가 `release_date < trade_date` 조건을 적용할 수 있도록 release evidence를 정규화한다.

### 6.3 EOD Silver

경로:

```text
data/silver/eod/eod_features/symbol=SPY/year=YYYY/month=MM/eod_features_YYYYMM.parquet
```

컬럼 그룹:

| 그룹 | 컬럼 |
| --- | --- |
| identity/price | `symbol`, `trade_date`, `source`, `theme`, `open`, `high`, `low`, `close`, `adj_close`, `volume`, `currency` |
| Bronze lineage | `run_id`, `ingestion_ts` |
| returns | `prev_adj_close`, `ret_1d`, `log_ret_1d`, `ret_5d`, `ret_20d` |
| volatility/MA | `vol_20d`, `vol_60d`, `ma_5`, `ma_20`, `ma_60`, `ma_120`, `ma_ratio_5_20` |
| technical/micro | `atr_14`, `gain_1d`, `loss_1d`, `avg_gain_14`, `avg_loss_14`, `rsi_14`, `intraday_range`, `gap_open`, `volume_zscore_20d` |
| quality | `is_trading_day`, `is_missing_imputed`, `is_outlier`, `is_partial_day` |
| observability label | `asset_group`, `asset_name`, `asset_subtype` |
| Silver lineage | `run_id_silver`, `ingestion_ts_silver` |

---

## 7. Gold Parquet SOT

### 7.1 Gold Macro Feature

경로:

```text
data/gold/macro/macro_features/year=YYYY/month=MM/gold_macro_features_YYYYMM.parquet
```

Grain: `(indicator_id, trade_date)`

컬럼:

```text
indicator_id, trade_date,
selected_observation_date, selected_value, selected_release_date,
delta_1m, delta_3m, delta_6m,
direction, regime, zscore_12m,
release_source, is_assumption_based
```

PIT rule:

```text
selected_release_date < trade_date
```

Release evidence 우선순위:

1. `econ_events`
2. `fred_vintages`
3. `assumed_t_plus_1`

### 7.2 Gold EOD Feature

경로:

```text
data/gold/eod/eod_features/symbol=SPY/year=YYYY/month=MM/gold_eod_features_YYYYMM.parquet
```

Grain: `(symbol, trade_date)`

컬럼 그룹:

| 그룹 | 컬럼 |
| --- | --- |
| identity | `symbol`, `trade_date` |
| price | `open`, `high`, `low`, `close`, `adj_close`, `volume`, `currency` |
| returns | `prev_adj_close`, `ret_1d`, `log_ret_1d`, `ret_5d`, `ret_20d` |
| volatility/MA | `vol_20d`, `vol_60d`, `ma_5`, `ma_20`, `ma_60`, `ma_120`, `ma_ratio_5_20` |
| technical/micro | `atr_14`, `rsi_14`, `intraday_range`, `gap_open`, `volume_zscore_20d` |
| quality | `is_trading_day`, `is_missing_imputed`, `is_outlier`, `is_partial_day` |
| observability label | `asset_group`, `asset_name`, `asset_subtype` |
| lineage | `run_id_gold`, `ingestion_ts_gold` |

---

## 8. Postgres Serving Schema

Postgres는 `pretrend_obs` DB의 serving mirror/cache다. Migration 기준은 `migrations/versions/0002_gold_schema.py`, `0003_similarity_schema.py`, `0004_explainability_cache.py`다.

### 8.1 Gold mirror tables

| Table | Primary key | Source | 비고 |
| --- | --- | --- | --- |
| `gold_macro_features` | `(indicator_id, trade_date)` | `data/gold/macro/macro_features` | Timescale hypertable, `selected_release_date < trade_date` check |
| `gold_eod_features` | `(symbol, trade_date)` | `data/gold/eod/eod_features` | Timescale hypertable |

Gold sync는 `src/pretrend/pipeline/sync/gold_postgres.py`가 담당한다. `gold_postgres_sync_dag.py`에서 Macro/EOD를 sync하며, conflict 발생 시 key 기준 upsert한다.

### 8.2 Similarity tables

| Table | Primary key | 주요 컬럼 | 비고 |
| --- | --- | --- | --- |
| `gold_market_state_similarity_feature` | `trade_date` | fixed-width market state feature columns + `built_at` | regime-view similarity 입력 feature |
| `similarity_regime` | `(query_date, neighbor_date)` | `rank`, `score`, `gap_days`, `built_at` | query별 rank unique, score 0~1 |
| `similarity_gold` | `(query_date, neighbor_date)` | `rank`, `score`, `gap_days`, `built_at` | Gold feature 기반 similarity 결과 |

`gold_market_state_similarity_feature`는 long/mid/short state, transition hazard, tactical rotation state를 정수/실수 feature로 wide table화한다. 이 table은 API serving과 similarity 계산을 위한 runtime representation이며 raw data lake의 원천 layer가 아니다.

### 8.3 Explainability cache

| Table | Primary key | 주요 컬럼 |
| --- | --- | --- |
| `explainability_cache` | `(use_case, query_date, model_id, prompt_version)` | `report_json`, `output_hash`, `built_at` |

허용 `use_case`:

```text
similarity_regime, similarity_gold, regime, macro
```

LLM/Codex 분석 결과는 cache에 저장되지만, trading decision source로 사용하지 않는다.

---

## 9. DAG와 Backfill 연결

| DAG 또는 service | 생성/갱신 대상 |
| --- | --- |
| `backfill-once` | 빈 data lake에서 Macro/EOD Bronze → Silver → Gold, Gold → Postgres sync |
| `macro_pipeline_dag` | Macro Bronze/Silver/Gold + Calendar evidence |
| `eod_pipeline_dag` | EOD Bronze/Silver/Gold |
| `gold_postgres_sync_dag` | Gold Parquet → Postgres mirror |
| `similarity_build_dag` | similarity feature/result tables |
| `explainability_build_dag` | explanation report cache |

`macro_pipeline_dag`, `eod_pipeline_dag`, `gold_postgres_sync_dag`에는 bootstrap marker guard가 포함된다. Marker가 없으면 manual trigger 시 먼저 data lake bootstrap을 수행한 뒤 정상 task를 이어간다.

---

## 10. 운영 불변식

- Gold Macro의 `selected_release_date`는 항상 `trade_date`보다 과거여야 한다.
- Gold Macro/EOD Parquet과 Postgres mirror는 같은 grain/key를 공유한다.
- API는 Postgres mirror/cache를 읽고, raw Bronze 파일을 직접 serving하지 않는다.
- Docker runtime에서는 host `PRETREND_HOST_DATA_DIR`가 container `/app/data`에 mount되어야 한다.
- `docker compose down -v`는 Postgres data volume을 삭제할 수 있으므로 운영 데이터가 연결된 compose project에서 사용하지 않는다.
- 최신 DB dump가 있으면 Postgres는 restore를 우선하고, file data lake가 비어 있거나 오래된 경우에만 backfill을 수행한다.
