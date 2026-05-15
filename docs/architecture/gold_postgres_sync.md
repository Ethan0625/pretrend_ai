# Gold Postgres Sync Contract

Markers: architecture, contract
Status: active

## 1. 목적 / 범위

본 문서는 Gold Parquet layer를 Postgres + TimescaleDB mirror로 동기화하는 정책 SOT다.

- Parquet Gold는 SOT다.
- Postgres는 API, similarity, dashboard 조회를 위한 mirror다.
- P25는 `gold_macro_features`, `gold_eod_features` 두 테이블 동기화만 다룬다.
- schema 기준은 `docs/architecture/gold_postgres_schema.md`다.
- Bronze/Silver/text Gold sync, API, similarity, view/materialized view는 범위 밖이다.

## 2. 워터마크 정책

워터마크는 Postgres mirror 테이블의 `MAX(trade_date)`다.

```sql
SELECT MAX(trade_date) FROM gold_macro_features;
SELECT MAX(trade_date) FROM gold_eod_features;
```

- Macro watermark: `SELECT MAX(trade_date) FROM gold_macro_features`
- EOD watermark: `SELECT MAX(trade_date) FROM gold_eod_features`
- `MAX(trade_date) IS NULL`이면 첫 실행으로 간주하고 전체 Parquet partition을 backfill한다.

의사코드:

```python
watermark = SELECT MAX(trade_date) FROM gold_*_features
if watermark is None:
    lower_bound = None  # 전체 partition scan
else:
    lower_bound = watermark - lookback_days
```

## 3. Lookback Window

### 3.1 Macro

- Lookback: 35일
- SQL 의미: `trade_date > MAX(trade_date) - INTERVAL '35 days'`
- 이유: `macro_pipeline_dag.py`는 최근 35일 rolling rebuild를 수행한다. Postgres sync도 같은 범위만 재읽으면 Parquet에서 실제로 재작성될 수 있는 revision을 흡수한다.
- 운영 결합: macro DAG rebuild window가 향후 확장되면 본 sync lookback도 lockstep으로 확장해야 한다.
- BLS 연간 재기준화처럼 35일을 넘는 revision은 macro pipeline rebuild window 확장 의제이며 P25 범위 밖이다.

### 3.2 EOD

- Lookback: 0일
- SQL 의미: `trade_date > MAX(trade_date)`
- 이유: EOD Gold는 split/dividend adjusted close를 사용하고, 일반 운영에서는 이미 적재된 과거 row가 rolling rebuild로 재작성되지 않는다.

## 4. Parquet 스캔 전략

### 4.1 Macro

- Root: `data/gold/macro/macro_features`
- Partition pattern: `year=YYYY/month=MM/*.parquet`
- 첫 실행: 전체 partition scan.
- 이후 실행: `watermark - 35 days`가 포함된 month부터 현재까지의 year/month partition만 읽는다.

### 4.2 EOD

- Root: `data/gold/eod/eod_features`
- Partition pattern: `symbol=XXX/year=YYYY/month=MM/*.parquet`
- 첫 실행: 전체 partition scan.
- 이후 실행: watermark 이후 날짜가 포함될 수 있는 year/month partition만 읽는다.

두 경로 모두 파일별로 읽은 뒤 `trade_date` 기준 최종 필터를 적용한다.

## 5. UPSERT SQL 명세

### 5.1 Macro

Macro full column list:

```text
indicator_id, trade_date, selected_observation_date, selected_value,
selected_release_date, delta_1m, delta_3m, delta_6m, direction, regime,
zscore_12m, release_source, is_assumption_based
```

Macro UPSERT target:

```sql
INSERT INTO gold_macro_features (
  indicator_id,
  trade_date,
  selected_observation_date,
  selected_value,
  selected_release_date,
  delta_1m,
  delta_3m,
  delta_6m,
  direction,
  regime,
  zscore_12m,
  release_source,
  is_assumption_based
)
VALUES (
  :indicator_id,
  :trade_date,
  :selected_observation_date,
  :selected_value,
  :selected_release_date,
  :delta_1m,
  :delta_3m,
  :delta_6m,
  :direction,
  :regime,
  :zscore_12m,
  :release_source,
  :is_assumption_based
)
ON CONFLICT (indicator_id, trade_date) DO UPDATE SET
  selected_observation_date = EXCLUDED.selected_observation_date,
  selected_value = EXCLUDED.selected_value,
  selected_release_date = EXCLUDED.selected_release_date,
  delta_1m = EXCLUDED.delta_1m,
  delta_3m = EXCLUDED.delta_3m,
  delta_6m = EXCLUDED.delta_6m,
  direction = EXCLUDED.direction,
  regime = EXCLUDED.regime,
  zscore_12m = EXCLUDED.zscore_12m,
  release_source = EXCLUDED.release_source,
  is_assumption_based = EXCLUDED.is_assumption_based;
```

PK 제외 update column은 11개다: `selected_observation_date`, `selected_value`, `selected_release_date`, `delta_1m`, `delta_3m`, `delta_6m`, `direction`, `regime`, `zscore_12m`, `release_source`, `is_assumption_based`.

### 5.2 EOD

EOD full column list:

```text
symbol, trade_date, open, high, low, close, adj_close, volume, currency,
prev_adj_close, ret_1d, log_ret_1d, ret_5d, ret_20d, vol_20d, vol_60d,
ma_5, ma_20, ma_60, ma_120, ma_ratio_5_20, atr_14, rsi_14,
intraday_range, gap_open, volume_zscore_20d, is_trading_day,
is_missing_imputed, is_outlier, is_partial_day, asset_group, asset_name,
asset_subtype, run_id_gold, ingestion_ts_gold
```

EOD UPSERT target:

```sql
INSERT INTO gold_eod_features (
  symbol,
  trade_date,
  open,
  high,
  low,
  close,
  adj_close,
  volume,
  currency,
  prev_adj_close,
  ret_1d,
  log_ret_1d,
  ret_5d,
  ret_20d,
  vol_20d,
  vol_60d,
  ma_5,
  ma_20,
  ma_60,
  ma_120,
  ma_ratio_5_20,
  atr_14,
  rsi_14,
  intraday_range,
  gap_open,
  volume_zscore_20d,
  is_trading_day,
  is_missing_imputed,
  is_outlier,
  is_partial_day,
  asset_group,
  asset_name,
  asset_subtype,
  run_id_gold,
  ingestion_ts_gold
)
VALUES (
  :symbol,
  :trade_date,
  :open,
  :high,
  :low,
  :close,
  :adj_close,
  :volume,
  :currency,
  :prev_adj_close,
  :ret_1d,
  :log_ret_1d,
  :ret_5d,
  :ret_20d,
  :vol_20d,
  :vol_60d,
  :ma_5,
  :ma_20,
  :ma_60,
  :ma_120,
  :ma_ratio_5_20,
  :atr_14,
  :rsi_14,
  :intraday_range,
  :gap_open,
  :volume_zscore_20d,
  :is_trading_day,
  :is_missing_imputed,
  :is_outlier,
  :is_partial_day,
  :asset_group,
  :asset_name,
  :asset_subtype,
  :run_id_gold,
  :ingestion_ts_gold
)
ON CONFLICT (symbol, trade_date) DO UPDATE SET
  open = EXCLUDED.open,
  high = EXCLUDED.high,
  low = EXCLUDED.low,
  close = EXCLUDED.close,
  adj_close = EXCLUDED.adj_close,
  volume = EXCLUDED.volume,
  currency = EXCLUDED.currency,
  prev_adj_close = EXCLUDED.prev_adj_close,
  ret_1d = EXCLUDED.ret_1d,
  log_ret_1d = EXCLUDED.log_ret_1d,
  ret_5d = EXCLUDED.ret_5d,
  ret_20d = EXCLUDED.ret_20d,
  vol_20d = EXCLUDED.vol_20d,
  vol_60d = EXCLUDED.vol_60d,
  ma_5 = EXCLUDED.ma_5,
  ma_20 = EXCLUDED.ma_20,
  ma_60 = EXCLUDED.ma_60,
  ma_120 = EXCLUDED.ma_120,
  ma_ratio_5_20 = EXCLUDED.ma_ratio_5_20,
  atr_14 = EXCLUDED.atr_14,
  rsi_14 = EXCLUDED.rsi_14,
  intraday_range = EXCLUDED.intraday_range,
  gap_open = EXCLUDED.gap_open,
  volume_zscore_20d = EXCLUDED.volume_zscore_20d,
  is_trading_day = EXCLUDED.is_trading_day,
  is_missing_imputed = EXCLUDED.is_missing_imputed,
  is_outlier = EXCLUDED.is_outlier,
  is_partial_day = EXCLUDED.is_partial_day,
  asset_group = EXCLUDED.asset_group,
  asset_name = EXCLUDED.asset_name,
  asset_subtype = EXCLUDED.asset_subtype,
  run_id_gold = EXCLUDED.run_id_gold,
  ingestion_ts_gold = EXCLUDED.ingestion_ts_gold;
```

PK 제외 update column은 33개다: `open`, `high`, `low`, `close`, `adj_close`, `volume`, `currency`, `prev_adj_close`, `ret_1d`, `log_ret_1d`, `ret_5d`, `ret_20d`, `vol_20d`, `vol_60d`, `ma_5`, `ma_20`, `ma_60`, `ma_120`, `ma_ratio_5_20`, `atr_14`, `rsi_14`, `intraday_range`, `gap_open`, `volume_zscore_20d`, `is_trading_day`, `is_missing_imputed`, `is_outlier`, `is_partial_day`, `asset_group`, `asset_name`, `asset_subtype`, `run_id_gold`, `ingestion_ts_gold`.

## 6. DAG 트리거 정책

- DAG ID: `gold_postgres_sync_dag`
- Schedule: `0 11 * * *`
- Timezone: `Asia/Seoul` (KST 11:00)
- `catchup=False`
- `max_active_runs=1`
- `retries=3`
- `retry_delay=10 minutes`
- `TriggerDagRunOperator` / `ExternalTaskSensor` 사용 안 함.

운영 DAG 시간대 정합:

| DAG | Schedule | Timezone | 역할 |
| --- | --- | --- | --- |
| `eod_pipeline_dag` | `0 8 * * *` | Asia/Seoul | EOD Parquet Gold 생성 |
| `macro_pipeline_dag` | `0 9 * * *` | Asia/Seoul | Macro Parquet Gold 생성 |
| `strategy_engine_dag` | `0 10 * * *` | Asia/Seoul | Personal Track, 동결 |
| `gold_postgres_sync_dag` | `0 11 * * *` | Asia/Seoul | Postgres mirror sync |

11:00 KST는 기존 10:00 strategy slot 뒤 1시간 buffer다. 기존 macro/eod DAG와 chain을 만들지 않고 독립 스케줄로 운영해 누락분은 다음 sync run에서 워터마크 기반으로 흡수한다.

## 7. 실패 핸들링

- Runner는 `sync_gold_macro()`와 `sync_gold_eod()`로 분리한다.
- Airflow task도 `sync_macro`, `sync_eod`로 분리한다.
- 두 task는 dependency를 두지 않아 한쪽 실패가 다른쪽 실행을 막지 않는다.
- 트랜잭션 경계는 테이블 단위 단일 트랜잭션이다.
- 실패 시 DB transaction은 rollback된다.
- retry는 Airflow level에서만 수행한다.
- runner는 UPSERT 기반이라 동일 입력 재실행에 idempotent하다.

## 8. Lineage 컬럼 처리

- EOD `run_id_gold`, `ingestion_ts_gold`는 Parquet 원본 값을 그대로 전파한다.
- Sync 실행 시각은 로그로만 남긴다.
- P25에서는 Postgres table에 `synced_at`, `sync_run_id` 같은 새 컬럼을 추가하지 않는다.
- Macro Parquet에는 lineage 컬럼이 없으므로 Macro mirror에도 새 lineage를 만들지 않는다.

## 9. 검증 명령

Row count:

```sql
SELECT COUNT(*) FROM gold_macro_features;
SELECT COUNT(*) FROM gold_eod_features;
```

Watermark:

```sql
SELECT MAX(trade_date) FROM gold_macro_features;
SELECT MAX(trade_date) FROM gold_eod_features;
```

Duplicate check:

```sql
SELECT indicator_id, trade_date, COUNT(*)
FROM gold_macro_features
GROUP BY 1, 2
HAVING COUNT(*) > 1;

SELECT symbol, trade_date, COUNT(*)
FROM gold_eod_features
GROUP BY 1, 2
HAVING COUNT(*) > 1;
```

Macro PIT CHECK 위반 확인:

```sql
SELECT *
FROM gold_macro_features
WHERE selected_release_date >= trade_date;
```

모든 duplicate / CHECK 위반 쿼리는 0행을 기대한다.

## 10. 변경 이력

- 2026-05-13: 초안 작성. P25-1.
