# Gold Postgres Schema Contract

## 1. 목적 / 범위

본 문서는 Gold Parquet layer를 SQL 조회 surface로 mirror하기 위한 Postgres + TimescaleDB schema 계약이다.

- Parquet Gold는 SOT다.
- Postgres는 API, similarity, dashboard 조회를 위한 Gold-only mirror다.
- 데이터 적재와 동기화는 P25 범위다.
- Bronze/Silver/text Gold schema는 본 문서 범위 밖이다.

## 2. 공통 원칙

- Parquet 컬럼명과 SQL 컬럼명은 1:1로 동일하게 유지한다.
- SQL 타입은 Parquet dtype과 계약 의미를 기준으로 정한다.
- Hypertable time axis는 양 테이블 모두 `trade_date`다.
- Hypertable `chunk_time_interval`은 `INTERVAL '1 month'`로 고정한다. 기존 Parquet year/month partition 운영과 정렬되고, 초기 로컬 운영에서 과도한 chunk 생성을 피하기 위한 기본값이다.
- SQLAlchemy/Alembic은 table/index 생성에 Python API를 사용하되, TimescaleDB hypertable 생성은 `op.execute("SELECT create_hypertable(...)")`를 사용한다.
- Postgres ENUM은 사용하지 않고 `TEXT` + `CHECK` constraint를 사용한다. 향후 source/regime 값 확장 시 Alembic enum 변경 비용을 피하기 위함이다.

## 3. `gold_macro_features` 명세

### 3.1 Grain / Key

- Grain: `(indicator_id, trade_date)`
- Primary key: `(indicator_id, trade_date)`
- Hypertable axis: `trade_date`
- Chunk interval: `INTERVAL '1 month'`

### 3.2 컬럼 매핑

| Parquet column | SQL type | Nullability | 의미 / 출처 |
| --- | --- | --- | --- |
| `indicator_id` | `TEXT` | `NOT NULL` | Macro indicator identifier. PK part. Gold contract §10.4 / MF1 |
| `trade_date` | `DATE` | `NOT NULL` | Gold 소비 기준 날짜. PK part / hypertable axis. Gold contract §10.4 / MF1 |
| `selected_observation_date` | `DATE` | `NULL` | 선택된 관측 기준일. Monthly/Daily 의미는 Gold contract §10.3 |
| `selected_value` | `DOUBLE PRECISION` | `NULL` | 선택된 level 값. Gold contract §10.4 |
| `selected_release_date` | `DATE` | `NULL` | 선택된 값의 사용 가능 날짜. Gold contract §10.4 / MF2 |
| `delta_1m` | `DOUBLE PRECISION` | `NULL` | 1M delta 또는 daily row-offset 근사. Gold contract §10.5 |
| `delta_3m` | `DOUBLE PRECISION` | `NULL` | 3M delta 또는 daily row-offset 근사. Gold contract §10.5 |
| `delta_6m` | `DOUBLE PRECISION` | `NULL` | 6M delta 또는 daily row-offset 근사. Gold contract §10.5 |
| `direction` | `TEXT` | `NULL` | `up` / `down` / `flat`. 값 결측 시 NULL 허용. Gold contract MF6 |
| `regime` | `TEXT` | `NULL` | `tightening` / `easing` / `neutral`. 값 결측 시 NULL 허용. Gold contract MF7 |
| `zscore_12m` | `DOUBLE PRECISION` | `NULL` | 12M/252D z-score. 히스토리 부족, 값 NULL, std=0이면 NULL. Gold contract MF10 |
| `release_source` | `TEXT` | `NULL` | `econ_events` / `fred_vintages` / `assumed_t_plus_1`. Calendar source |
| `is_assumption_based` | `BOOLEAN` | `NOT NULL` | Calendar assumption 여부. Gold contract §10.4 |

### 3.3 Constraints

- `PRIMARY KEY (indicator_id, trade_date)`
- `CHECK (selected_release_date < trade_date)`
  - `selected_release_date`는 기존 Gold contract와 동일하게 NULL 허용이다.
  - PostgreSQL CHECK는 NULL이면 통과하므로, MF2는 값이 존재하는 행에 대해 강제된다.
- `CHECK (direction IN ('up', 'down', 'flat'))`
- `CHECK (regime IN ('tightening', 'easing', 'neutral'))`
- `CHECK (release_source IN ('econ_events', 'fred_vintages', 'assumed_t_plus_1'))`

### 3.4 Index

- `BRIN (trade_date)` — 시간 범위 조회 최적화.
- `BTREE (indicator_id)` — 단일 indicator 조회 최적화.
- `release_source` 보조 index는 P24에서 만들지 않는다. P25 이후 실제 조회 패턴을 보고 추가한다.

### 3.5 Lineage 결정

Macro Parquet `GOLD_MACRO_FEATURE_COLUMNS`에는 `run_id_gold`, `ingestion_ts_gold`가 없다. P24는 Parquet mirror 작업이므로 `gold_macro_features`에는 새 lineage 컬럼을 추가하지 않는다.

## 4. `gold_eod_features` 명세

### 4.1 Grain / Key

- Grain: `(symbol, trade_date)`
- Primary key: `(symbol, trade_date)`
- Hypertable axis: `trade_date`
- Chunk interval: `INTERVAL '1 month'`

### 4.2 컬럼 매핑

| Parquet column | SQL type | Nullability | 의미 / 출처 |
| --- | --- | --- | --- |
| `symbol` | `TEXT` | `NOT NULL` | Observability symbol. PK part |
| `trade_date` | `DATE` | `NOT NULL` | EOD 거래 기준 날짜. PK part / hypertable axis |
| `open` | `DOUBLE PRECISION` | `NULL` | 일봉 open |
| `high` | `DOUBLE PRECISION` | `NULL` | 일봉 high |
| `low` | `DOUBLE PRECISION` | `NULL` | 일봉 low |
| `close` | `DOUBLE PRECISION` | `NULL` | 일봉 close |
| `adj_close` | `DOUBLE PRECISION` | `NULL` | Yahoo split/dividend adjusted close. PIT vintage 컬럼 없음 |
| `volume` | `BIGINT` | `NULL` | 거래량 |
| `currency` | `TEXT` | `NULL` | 통화 코드. 현재 USD 중심이나 mirror에서는 TEXT 유지 |
| `prev_adj_close` | `DOUBLE PRECISION` | `NULL` | 이전 거래일 adjusted close |
| `ret_1d` | `DOUBLE PRECISION` | `NULL` | 1D return. warmup/결측 시 NULL |
| `log_ret_1d` | `DOUBLE PRECISION` | `NULL` | 1D log return. warmup/결측 시 NULL |
| `ret_5d` | `DOUBLE PRECISION` | `NULL` | 5D return. warmup/결측 시 NULL |
| `ret_20d` | `DOUBLE PRECISION` | `NULL` | 20D return. warmup/결측 시 NULL |
| `vol_20d` | `DOUBLE PRECISION` | `NULL` | 20D volatility. warmup/결측 시 NULL |
| `vol_60d` | `DOUBLE PRECISION` | `NULL` | 60D volatility. warmup/결측 시 NULL |
| `ma_5` | `DOUBLE PRECISION` | `NULL` | 5D moving average |
| `ma_20` | `DOUBLE PRECISION` | `NULL` | 20D moving average |
| `ma_60` | `DOUBLE PRECISION` | `NULL` | 60D moving average |
| `ma_120` | `DOUBLE PRECISION` | `NULL` | 120D moving average |
| `ma_ratio_5_20` | `DOUBLE PRECISION` | `NULL` | `ma_5 / ma_20` 계열 ratio |
| `atr_14` | `DOUBLE PRECISION` | `NULL` | 14D ATR |
| `rsi_14` | `DOUBLE PRECISION` | `NULL` | 14D RSI |
| `intraday_range` | `DOUBLE PRECISION` | `NULL` | 일중 range |
| `gap_open` | `DOUBLE PRECISION` | `NULL` | open gap |
| `volume_zscore_20d` | `DOUBLE PRECISION` | `NULL` | 20D volume z-score |
| `is_trading_day` | `BOOLEAN` | `NOT NULL` | 거래일 여부 |
| `is_missing_imputed` | `BOOLEAN` | `NOT NULL` | 결측 보간 여부 |
| `is_outlier` | `BOOLEAN` | `NOT NULL` | 이상치 여부 |
| `is_partial_day` | `BOOLEAN` | `NOT NULL` | 부분 거래일 여부 |
| `asset_group` | `TEXT` | `NOT NULL` | EOD observability 대분류. `eod_observability_contract.md` §6.2 |
| `asset_name` | `TEXT` | `NOT NULL` | 사람이 읽을 수 있는 canonical 이름. `eod_observability_contract.md` §6.2 |
| `asset_subtype` | `TEXT` | `NULL` | 세부 분류. `eod_observability_contract.md` §6.2 |
| `run_id_gold` | `TEXT` | `NOT NULL` | Gold EOD build run id |
| `ingestion_ts_gold` | `TIMESTAMPTZ` | `NOT NULL` | Gold EOD build ingestion timestamp |

### 4.3 Constraints

- `PRIMARY KEY (symbol, trade_date)`
- 별도 enum/check constraint는 P24에서 추가하지 않는다. Boolean quality flag는 SQL `BOOLEAN`으로 강제하고, label enum 확장은 기존 EOD contract와 P25 이후 validation에서 관리한다.

### 4.4 Index

- `BRIN (trade_date)` — 시간 범위 조회 최적화.
- `BTREE (symbol)` — 단일 symbol 조회 최적화.
- `asset_group` 보조 index는 P24에서 만들지 않는다. P25 이후 실제 API/dashboard 조회 패턴을 보고 추가한다.

### 4.5 Lineage 결정

EOD Parquet `GOLD_EOD_FEATURE_COLUMNS`에는 `run_id_gold`, `ingestion_ts_gold`가 포함되어 있다. Postgres mirror에도 두 컬럼을 포함하며, P25 sync DAG에서 Parquet run lineage 추적에 사용한다.

## 5. 공통 구현 결정

### 5.1 ENUM vs TEXT + CHECK

Postgres native ENUM은 사용하지 않는다. Macro의 고정 값 컬럼은 `TEXT` + `CHECK` constraint로 강제한다. 향후 source/regime 값이 추가될 때 enum type migration보다 단순하고, P24가 mirror schema 도입이라는 제한된 목적에 더 잘 맞는다.

### 5.2 Hypertable

두 테이블 모두 `trade_date`를 TimescaleDB hypertable axis로 사용한다.

```sql
SELECT create_hypertable(
  'gold_macro_features',
  'trade_date',
  chunk_time_interval => INTERVAL '1 month'
);

SELECT create_hypertable(
  'gold_eod_features',
  'trade_date',
  chunk_time_interval => INTERVAL '1 month'
);
```

### 5.3 Alembic 원칙

- `op.create_table`로 table, primary key, check constraint를 정의한다.
- TimescaleDB hypertable 변환은 `op.execute`로 수행한다.
- BRIN/B-tree index는 hypertable 생성 후 `op.create_index`로 생성한다.
- 데이터 적재 전 빈 테이블 상태에서 hypertable을 생성한다.

## 6. Nullability 결정 요약

- Macro는 기존 `gold_design_contract.md` §10.4를 따른다. `selected_observation_date`, `selected_value`, `selected_release_date`, `delta_*`, `direction`, `regime`, `zscore_12m`, `release_source`는 NULL 허용이다.
- EOD는 identity, quality flags, labels(`asset_group`, `asset_name`), lineage를 NOT NULL로 둔다. 가격/수익률/기술지표/`asset_subtype`은 결측과 warmup period를 허용한다.

## 7. Index 결정 요약

- P24에서는 필수 조회 경로만 만든다: time range(`trade_date`)와 entity lookup(`indicator_id`, `symbol`).
- `release_source`, `asset_group` 같은 보조 인덱스는 P25 이후 실제 sync/API/dashboard 조회 패턴을 보고 추가한다.

## 8. P24 후속 구현 기준

- P24-2 SQLAlchemy 모델은 본 문서의 컬럼 순서, 타입, nullability, PK, macro CHECK constraint를 그대로 따른다.
- P24-3 Alembic migration은 본 문서의 테이블 정의, hypertable axis, chunk interval, index 이름 정책을 구현한다.

## 9. Non-Goals

- Parquet contract 변경.
- Macro lineage 컬럼 신설.
- Parquet -> Postgres sync DAG.
- materialized view / continuous aggregate.
- compression / retention policy.
- Bronze/Silver/text Gold schema.

## 10. 변경 이력

- 2026-05-13: 초안 작성. P24-1.
