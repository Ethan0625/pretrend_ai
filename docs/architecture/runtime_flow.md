# Runtime Flow

Markers: architecture, contract
Status: active

## 1. 일일 runtime 순서

Phase 2 runtime은 향후 dashboard가 읽을 API data를 만드는 로컬 scheduled pipeline이다.

KST 기준 일일 순서:

1. `eod_pipeline_dag`가 08:00에 실행되어 Gold EOD Parquet을 갱신한다.
2. `macro_pipeline_dag`가 09:00에 실행되어 Gold macro Parquet을 갱신한다.
3. `gold_postgres_sync_dag`가 11:00에 실행되어 Gold Parquet을 Postgres로 mirror한다.
4. `similarity_build_dag`가 12:00에 실행되어 regime/gold historical similarity output을 쓴다.
5. `explainability_build_dag`가 13:00에 실행되어 cached explanation report를 쓴다.
6. FastAPI는 Postgres serving table을 읽는다.
7. Phase 3 Dashboard는 FastAPI를 읽는다.

`strategy_engine_dag`는 optional archived strategy-report DAG이며, Observability runtime dependency chain의 일부가 아니다.

## 2. DAG 목록

| DAG | Schedule | 입력 | 출력 | 실패 영향 |
| --- | --- | --- | --- | --- |
| `eod_pipeline_dag` | `0 8 * * *` | Market source data | `data/gold/eod/eod_features` 아래 Gold EOD Parquet | Sync가 새 EOD data를 못 잡으면 EOD API와 gold similarity가 stale 상태가 된다. |
| `macro_pipeline_dag` | `0 9 * * *` | FRED/source macro data | `data/gold/macro/macro_features` 아래 Gold macro Parquet | Macro API와 gold similarity macro feature가 stale 상태가 된다. |
| `strategy_engine_dag` | `0 10 * * *` | Gold와 archived strategy input | Strategy snapshot과 report | 보관된 strategy-report 용도. 기본 paused 유지. |
| `gold_postgres_sync_dag` | `0 11 * * *` | Gold macro/EOD Parquet | `gold_macro_features`, `gold_eod_features` | API가 stale mirror data를 읽고, similarity가 최신 Gold 값을 놓칠 수 있다. |
| `similarity_build_dag` | `0 12 * * *` | Gold Postgres mirror와 regime feature builder | `gold_market_state_similarity_feature`, `similarity_regime`, `similarity_gold` | Similarity API와 관련 explanation panel이 stale 또는 unavailable 상태가 된다. |
| `explainability_build_dag` | `0 13 * * *` | Postgres evidence table | `explainability_cache` | Explain endpoint가 stale report 또는 404를 반환할 수 있다. Raw data endpoint는 계속 동작한다. |

추가 운영 DAG:

| DAG | Schedule | 상태 메모 |
| --- | --- | --- |
| `text_pipeline_dag` | `30 9 * * *` | Text pipeline observer path. 5개 Observability DAG chain 밖에 있다. |
| `paper_trading_dag` | `.env.airflow` 적용 시 `40 9 * * 1-5` | 보관된 execution DAG. 기본 paused 유지. |
| `broker_mock_trading_dag` | `.env.airflow` 적용 시 `40 9 * * 1-5` | 보관된 execution DAG. 기본 paused 유지. |

## 3. Data freshness

Freshness는 consumer가 읽는 layer에서 보이는 최신 날짜로 판단한다.

| Layer | Freshness field | Healthy expectation | Stale 상태 영향 |
| --- | --- | --- | --- |
| Gold macro Parquet | latest partition / `trade_date` | `macro_pipeline_dag` rolling window로 갱신 | Postgres macro mirror가 전진하지 못한다. |
| Gold EOD Parquet | latest partition / `trade_date` | 마지막 완료 US trading day | Postgres EOD mirror가 전진하지 못한다. |
| `gold_macro_features` | `MAX(trade_date)` | 최신 Gold macro `trade_date` 근처 | `/api/v1/macro*`와 gold similarity가 stale. |
| `gold_eod_features` | `MAX(trade_date)` | 최신 Gold EOD `trade_date` 근처 | `/api/v1/eod*`와 gold similarity가 stale. |
| `gold_market_state_similarity_feature` | `MAX(trade_date)` | 최신 EOD/macro serving watermark 근처 | `/api/v1/regime`과 regime similarity가 stale. |
| `similarity_regime` | `MAX(query_date)` | 최신 state feature date 근처 | Regime similarity view가 stale. |
| `similarity_gold` | `MAX(query_date)` | 최신 Gold mirror date 근처 | Gold similarity view가 stale. |
| `explainability_cache` | `use_case`별 `MAX(query_date)` | Dashboard에 보이는 최신 날짜 | Explanation panel이 404 또는 stale report를 표시할 수 있다. |

P29는 audit 당시 common repaired/backfilled serving date였던 `2026-05-13` 기준으로 serving freshness를 검증했다.

## 4. Failure propagation

| 실패 | 즉시 영향 | Downstream 영향 | 예상 API behavior |
| --- | --- | --- | --- |
| EOD DAG 실패 | Gold EOD Parquet stale | Gold Postgres sync가 fresh EOD를 mirror하지 못함 | EOD endpoint는 마지막 mirror date를 반환하거나 missing date에 404. |
| Macro DAG 실패 | Gold macro Parquet stale | Macro mirror와 gold similarity stale | Macro endpoint는 마지막 mirror date를 반환하거나 missing date에 404. |
| Gold sync DAG 실패 | Parquet이 fresh여도 Postgres mirror stale | API, similarity, explainability가 stale mirror로 동작 | `/api/v1/meta` watermark가 stale 상태를 드러냄. |
| Similarity DAG 실패 | Similarity table stale 또는 incomplete | Similarity API와 explain cache stale | Similarity endpoint는 stale date, 404, 또는 이전 Top-N 반환. |
| Explainability DAG 실패 | 최신 date/use case cache 미생성 | Explain endpoint miss, raw endpoint는 동작 | Explain endpoint는 cache miss에서 404. |
| API container 실패 | Dashboard가 runtime data를 읽지 못함 | Dashboard unavailable | `/health` unavailable. |
| Postgres container 실패 | API와 builder job이 serving table을 읽거나 쓰지 못함 | Runtime unavailable | `/health` 또는 data endpoint 실패. |

P29 repair 이전의 historical scheduled failure는 이후 manual run 성공과 serving table invariant 통과가 있으면 현재 baseline으로 보지 않는다.

## 5. Manual recovery

모든 Airflow CLI check는 project Airflow environment variable을 사용해야 한다. Plain `airflow`는 기본 `~/airflow` metadata DB를 가리켜 false negative를 만들 수 있다.

권장 environment prefix:

```bash
env \
  AIRFLOW_HOME=$PWD/airflow_pretrend \
  PYTHONPATH=$PWD/src \
  AIRFLOW__CORE__DAGS_FOLDER=$PWD/dags \
  AIRFLOW__CORE__LOAD_EXAMPLES=False \
  AIRFLOW__CORE__DEFAULT_TIMEZONE=Asia/Seoul \
  conda run -n airflow-pretrend airflow dags list
```

Runtime window를 놓친 뒤 recovery 순서:

1. Container 상태 확인.

```bash
docker compose ps
```

2. Airflow registration/import 확인.

```bash
env AIRFLOW_HOME=$PWD/airflow_pretrend \
  PYTHONPATH=$PWD/src \
  AIRFLOW__CORE__DAGS_FOLDER=$PWD/dags \
  AIRFLOW__CORE__LOAD_EXAMPLES=False \
  AIRFLOW__CORE__DEFAULT_TIMEZONE=Asia/Seoul \
  conda run -n airflow-pretrend airflow dags list-import-errors
```

3. Parquet이 stale이면 upstream data job 실행.

```bash
env AIRFLOW_HOME=$PWD/airflow_pretrend \
  PYTHONPATH=$PWD/src \
  AIRFLOW__CORE__DAGS_FOLDER=$PWD/dags \
  AIRFLOW__CORE__LOAD_EXAMPLES=False \
  AIRFLOW__CORE__DEFAULT_TIMEZONE=Asia/Seoul \
  conda run -n airflow-pretrend airflow dags trigger eod_pipeline_dag

env AIRFLOW_HOME=$PWD/airflow_pretrend \
  PYTHONPATH=$PWD/src \
  AIRFLOW__CORE__DAGS_FOLDER=$PWD/dags \
  AIRFLOW__CORE__LOAD_EXAMPLES=False \
  AIRFLOW__CORE__DEFAULT_TIMEZONE=Asia/Seoul \
  conda run -n airflow-pretrend airflow dags trigger macro_pipeline_dag
```

4. Gold를 Postgres로 mirror.

```bash
env AIRFLOW_HOME=$PWD/airflow_pretrend \
  PYTHONPATH=$PWD/src \
  AIRFLOW__CORE__DAGS_FOLDER=$PWD/dags \
  AIRFLOW__CORE__LOAD_EXAMPLES=False \
  AIRFLOW__CORE__DEFAULT_TIMEZONE=Asia/Seoul \
  conda run -n airflow-pretrend airflow dags trigger gold_postgres_sync_dag
```

5. Target date 또는 range에 대해 similarity rebuild.

```bash
env AIRFLOW_HOME=$PWD/airflow_pretrend \
  PYTHONPATH=$PWD/src \
  AIRFLOW__CORE__DAGS_FOLDER=$PWD/dags \
  AIRFLOW__CORE__LOAD_EXAMPLES=False \
  AIRFLOW__CORE__DEFAULT_TIMEZONE=Asia/Seoul \
  conda run -n airflow-pretrend airflow dags trigger similarity_build_dag \
  --conf '{"query_start":"YYYY-MM-DD","query_end":"YYYY-MM-DD"}'
```

6. Explanation scope/window contract가 명확할 때만 explainability를 rebuild한다. Idempotency 또는 local smoke 목적이면 mock provider를 강제한다.

```bash
env AIRFLOW_HOME=$PWD/airflow_pretrend \
  PYTHONPATH=$PWD/src \
  AIRFLOW__CORE__DAGS_FOLDER=$PWD/dags \
  AIRFLOW__CORE__LOAD_EXAMPLES=False \
  AIRFLOW__CORE__DEFAULT_TIMEZONE=Asia/Seoul \
  conda run -n airflow-pretrend airflow dags trigger explainability_build_dag \
  --conf '{"query_date":"YYYY-MM-DD","provider":"mock"}'
```

7. Serving table 확인.

```sql
SELECT COUNT(*), MAX(trade_date) FROM gold_macro_features;
SELECT COUNT(*), MAX(trade_date) FROM gold_eod_features;
SELECT COUNT(*), MAX(trade_date) FROM gold_market_state_similarity_feature;
SELECT COUNT(*), MAX(query_date) FROM similarity_regime;
SELECT COUNT(*), MAX(query_date) FROM similarity_gold;
SELECT use_case, COUNT(*), MAX(query_date) FROM explainability_cache GROUP BY 1;
```

## 6. 변경 이력

- 2026-05-15: 초안 작성. P29-3.
- 2026-05-16: 문서 기준 언어를 한국어로 정리.
