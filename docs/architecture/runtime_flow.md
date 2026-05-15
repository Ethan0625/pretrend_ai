# Runtime Flow

Markers: architecture, contract
Status: active

## 1. Daily Runtime Order

The Phase 2 runtime is a local, scheduled pipeline that produces read-only API data for a future dashboard.

Daily order, KST:

1. `eod_pipeline_dag` runs at 08:00 and updates Gold EOD Parquet.
2. `macro_pipeline_dag` runs at 09:00 and updates Gold macro Parquet.
3. `gold_postgres_sync_dag` runs at 11:00 and mirrors Gold Parquet into Postgres.
4. `similarity_build_dag` runs at 12:00 and writes regime/gold historical similarity outputs.
5. `explainability_build_dag` runs at 13:00 and writes cached explanation reports.
6. FastAPI reads Postgres serving tables.
7. Phase 3 Dashboard reads FastAPI.

The Personal Track `strategy_engine_dag` is a frozen legacy DAG and is not part of the Observability runtime dependency chain.

## 2. DAG Inventory

| DAG | Schedule | Input | Output | Failure Impact |
| --- | --- | --- | --- | --- |
| `eod_pipeline_dag` | `0 8 * * *` | Market source data | Gold EOD Parquet under `data/gold/eod/eod_features` | EOD API and gold similarity become stale after sync catches no new EOD data. |
| `macro_pipeline_dag` | `0 9 * * *` | FRED/source macro data | Gold macro Parquet under `data/gold/macro/macro_features` | Macro API and gold similarity macro features become stale. |
| `strategy_engine_dag` | `0 10 * * *` | Gold and Personal strategy inputs | Strategy snapshots and reports | Personal Track only. Should be paused by frozen-track policy. |
| `gold_postgres_sync_dag` | `0 11 * * *` | Gold macro/EOD Parquet | `gold_macro_features`, `gold_eod_features` | API reads stale mirror data; similarity can miss latest Gold values. |
| `similarity_build_dag` | `0 12 * * *` | Gold Postgres mirror and regime feature builders | `gold_market_state_similarity_feature`, `similarity_regime`, `similarity_gold` | Similarity API and related explanation panels become stale or unavailable. |
| `explainability_build_dag` | `0 13 * * *` | Postgres evidence tables | `explainability_cache` | Explain endpoints may return stale reports or 404 while raw data endpoints still work. |

Additional operational DAGs observed in P29:

| DAG | Schedule | Status note |
| --- | --- | --- |
| `text_pipeline_dag` | `30 9 * * *` | Text pipeline legacy/observer path, outside the 5 Observability DAG chain. |
| `paper_trading_dag` | `40 9 * * 1-5` when `.env.airflow` is sourced | Personal Track, should be paused/stopped by policy. |
| `broker_mock_trading_dag` | `40 9 * * 1-5` when `.env.airflow` is sourced | Personal Track, should be paused/stopped by policy and duplicates the paper slot. |

## 3. Data Freshness

Freshness is judged by the latest date visible in the layer that a consumer reads.

| Layer | Freshness field | Healthy expectation | Consumer impact when stale |
| --- | --- | --- | --- |
| Gold macro Parquet | latest partition / `trade_date` | Updated by `macro_pipeline_dag` rolling window | Postgres macro mirror cannot advance. |
| Gold EOD Parquet | latest partition / `trade_date` | Last complete US trading day | Postgres EOD mirror cannot advance. |
| `gold_macro_features` | `MAX(trade_date)` | Near latest Gold macro `trade_date` | `/api/v1/macro*` and gold similarity stale. |
| `gold_eod_features` | `MAX(trade_date)` | Near latest Gold EOD `trade_date` | `/api/v1/eod*` and gold similarity stale. |
| `gold_market_state_similarity_feature` | `MAX(trade_date)` | Near latest EOD/macro serving watermark | `/api/v1/regime` and regime similarity stale. |
| `similarity_regime` | `MAX(query_date)` | Near latest state feature date | Regime similarity view stale. |
| `similarity_gold` | `MAX(query_date)` | Near latest Gold mirror date | Gold similarity view stale. |
| `explainability_cache` | `MAX(query_date)` by `use_case` | Latest dashboard-visible date per use case | Explanation panels may 404 or show stale reports. |

P29 verified serving freshness against `2026-05-13`, the latest common repaired/backfilled serving date at audit time.

## 4. Failure Propagation

| Failure | Immediate effect | Downstream effect | Expected API behavior |
| --- | --- | --- | --- |
| EOD DAG fails | Gold EOD Parquet stale | Gold Postgres sync cannot mirror fresh EOD | EOD endpoints return last mirrored date or 404 for missing date. |
| Macro DAG fails | Gold macro Parquet stale | Macro mirror and gold similarity stale | Macro endpoints return last mirrored date or 404 for missing date. |
| Gold sync DAG fails | Postgres mirror stale even if Parquet is fresh | API, similarity, and explainability operate on stale mirror | `/api/v1/meta` watermarks reveal stale state. |
| Similarity DAG fails | Similarity tables stale or incomplete | Similarity API and similarity explain cache stale | Similarity endpoints return stale date, 404, or prior successful Top-N. |
| Explainability DAG fails | Cache not populated for latest date/use case | Explain endpoints may miss while raw endpoints work | Explain endpoints return 404 on cache miss; raw data endpoints remain usable. |
| API container fails | Dashboard cannot read runtime data | Dashboard unavailable | `/health` unavailable. |
| Postgres container fails | API and builder jobs cannot read/write serving tables | Runtime unavailable | `/health` or data endpoints fail. |

Historical scheduled failures before P29 repair are not considered the current baseline if a subsequent manual run succeeds and serving table invariants pass.

## 5. Manual Recovery

Use project Airflow environment variables for all Airflow CLI checks. Plain `airflow` may point to the default `~/airflow` metadata DB and report false negatives.

Recommended environment prefix:

```bash
env \
  AIRFLOW_HOME=/home/redtable/Desktop/ethan/pretrend/pretrend_ai/airflow_pretrend \
  PYTHONPATH=/home/redtable/Desktop/ethan/pretrend/pretrend_ai/src \
  AIRFLOW__CORE__DAGS_FOLDER=/home/redtable/Desktop/ethan/pretrend/pretrend_ai/dags \
  AIRFLOW__CORE__LOAD_EXAMPLES=False \
  AIRFLOW__CORE__DEFAULT_TIMEZONE=Asia/Seoul \
  conda run -n airflow-pretrend airflow dags list
```

Recovery order after a missed runtime window:

1. Confirm containers:

```bash
docker compose ps
```

2. Confirm Airflow registration/import:

```bash
env AIRFLOW_HOME=/home/redtable/Desktop/ethan/pretrend/pretrend_ai/airflow_pretrend \
  PYTHONPATH=/home/redtable/Desktop/ethan/pretrend/pretrend_ai/src \
  AIRFLOW__CORE__DAGS_FOLDER=/home/redtable/Desktop/ethan/pretrend/pretrend_ai/dags \
  AIRFLOW__CORE__LOAD_EXAMPLES=False \
  AIRFLOW__CORE__DEFAULT_TIMEZONE=Asia/Seoul \
  conda run -n airflow-pretrend airflow dags list-import-errors
```

3. Run upstream data jobs if Parquet is stale:

```bash
env AIRFLOW_HOME=/home/redtable/Desktop/ethan/pretrend/pretrend_ai/airflow_pretrend \
  PYTHONPATH=/home/redtable/Desktop/ethan/pretrend/pretrend_ai/src \
  AIRFLOW__CORE__DAGS_FOLDER=/home/redtable/Desktop/ethan/pretrend/pretrend_ai/dags \
  AIRFLOW__CORE__LOAD_EXAMPLES=False \
  AIRFLOW__CORE__DEFAULT_TIMEZONE=Asia/Seoul \
  conda run -n airflow-pretrend airflow dags trigger eod_pipeline_dag

env AIRFLOW_HOME=/home/redtable/Desktop/ethan/pretrend/pretrend_ai/airflow_pretrend \
  PYTHONPATH=/home/redtable/Desktop/ethan/pretrend/pretrend_ai/src \
  AIRFLOW__CORE__DAGS_FOLDER=/home/redtable/Desktop/ethan/pretrend/pretrend_ai/dags \
  AIRFLOW__CORE__LOAD_EXAMPLES=False \
  AIRFLOW__CORE__DEFAULT_TIMEZONE=Asia/Seoul \
  conda run -n airflow-pretrend airflow dags trigger macro_pipeline_dag
```

4. Mirror Gold into Postgres:

```bash
env AIRFLOW_HOME=/home/redtable/Desktop/ethan/pretrend/pretrend_ai/airflow_pretrend \
  PYTHONPATH=/home/redtable/Desktop/ethan/pretrend/pretrend_ai/src \
  AIRFLOW__CORE__DAGS_FOLDER=/home/redtable/Desktop/ethan/pretrend/pretrend_ai/dags \
  AIRFLOW__CORE__LOAD_EXAMPLES=False \
  AIRFLOW__CORE__DEFAULT_TIMEZONE=Asia/Seoul \
  conda run -n airflow-pretrend airflow dags trigger gold_postgres_sync_dag
```

5. Rebuild similarity for the target date or range:

```bash
env AIRFLOW_HOME=/home/redtable/Desktop/ethan/pretrend/pretrend_ai/airflow_pretrend \
  PYTHONPATH=/home/redtable/Desktop/ethan/pretrend/pretrend_ai/src \
  AIRFLOW__CORE__DAGS_FOLDER=/home/redtable/Desktop/ethan/pretrend/pretrend_ai/dags \
  AIRFLOW__CORE__LOAD_EXAMPLES=False \
  AIRFLOW__CORE__DEFAULT_TIMEZONE=Asia/Seoul \
  conda run -n airflow-pretrend airflow dags trigger similarity_build_dag \
  --conf '{"query_start":"YYYY-MM-DD","query_end":"YYYY-MM-DD"}'
```

6. Rebuild explainability only after the explanation scope/window contract is clear. For idempotency or local smoke, force the mock provider:

```bash
env AIRFLOW_HOME=/home/redtable/Desktop/ethan/pretrend/pretrend_ai/airflow_pretrend \
  PYTHONPATH=/home/redtable/Desktop/ethan/pretrend/pretrend_ai/src \
  AIRFLOW__CORE__DAGS_FOLDER=/home/redtable/Desktop/ethan/pretrend/pretrend_ai/dags \
  AIRFLOW__CORE__LOAD_EXAMPLES=False \
  AIRFLOW__CORE__DEFAULT_TIMEZONE=Asia/Seoul \
  conda run -n airflow-pretrend airflow dags trigger explainability_build_dag \
  --conf '{"query_date":"YYYY-MM-DD","provider":"mock"}'
```

7. Verify serving tables:

```sql
SELECT COUNT(*), MAX(trade_date) FROM gold_macro_features;
SELECT COUNT(*), MAX(trade_date) FROM gold_eod_features;
SELECT COUNT(*), MAX(trade_date) FROM gold_market_state_similarity_feature;
SELECT COUNT(*), MAX(query_date) FROM similarity_regime;
SELECT COUNT(*), MAX(query_date) FROM similarity_gold;
SELECT use_case, COUNT(*), MAX(query_date) FROM explainability_cache GROUP BY 1;
```

## 6. Change History

- 2026-05-15: Initial draft. P29-3.
