# Pipeline Window Policy

Markers: architecture, contract, operation
Status: active

## 1. 목적

이 문서는 scheduled pipeline이 어떤 기간을 다시 읽고, 다시 계산하고, Postgres mirror로 동기화하는지를 고정하는 운영 계약이다.

처리 윈도우는 단순 성능 최적화 값이 아니다. Feature dependency, source revision 가능성, partition isolation, 장애 복구 범위, old corrupt partition 방어를 함께 고려한 값이다.

## 2. 기본 원칙

1. Backfill과 scheduled incremental run은 다른 모드다.
   - Backfill은 빈 data lake 또는 historical prepend를 복구하기 위한 전체/장기 처리다.
   - Scheduled DAG는 운영 중 최신 구간을 안정적으로 갱신하기 위한 windowed incremental 처리다.

2. Bronze 수집 윈도우와 feature 계산 입력 윈도우는 다르다.
   - 수집은 target output을 만들기 위한 원천 데이터를 확보한다.
   - feature 계산은 rolling, lag, YoY, z-score처럼 과거 이력이 필요한 컬럼 때문에 더 긴 입력 구간을 읽을 수 있다.

3. Output write 범위는 target/output partition으로 제한한다.
   - 입력을 넓게 읽더라도 오래된 partition을 불필요하게 다시 쓰지 않는다.
   - 동일 기간 재실행 시 같은 partition을 overwrite해 멱등성을 유지한다.

4. Scheduled path에서는 parquet를 읽기 전에 partition 후보를 먼저 좁힌다.
   - 전체 `rglob` 후 read/filter 방식은 데이터가 커질수록 old corrupt partition 하나 때문에 최신 운영 run이 깨질 수 있다.
   - 대상 year/month/symbol partition을 먼저 산정한 뒤 필요한 파일만 읽는다.

5. Upstream rolling rebuild 범위가 바뀌면 downstream sync lookback도 같이 바꾼다.
   - 예를 들어 Macro Gold가 최근 35일을 다시 쓴다면 Postgres sync도 최소 같은 35일을 다시 읽어야 한다.

## 3. 현재 처리 윈도우

| 영역 | 코드 위치 | 현재 값 | 산정 기준 | 같이 확인할 값 |
| --- | --- | ---: | --- | --- |
| Macro DAG 수집/rebuild | `dags/macro_pipeline_dag.py` | 35일 | FRED/source macro data의 지연 반영과 근거리 revision을 daily run에서 흡수한다. | `WATERMARK_LOOKBACK_DAYS_MACRO` |
| Macro Bronze -> Silver feature input | `src/pretrend/pipeline/macro_job.py`, `src/pretrend/pipeline/features/macro_features.py` | 12개월 | `yoy`, `rolling_12m` 계산에 필요한 최소 이력이다. | macro feature 계산식 |
| Macro Silver/Calendar -> Gold input | `src/pretrend/pipeline/macro_job.py` | 18개월 | 12개월 rolling/z-score 입력에 `delta_6m` 및 PIT calendar 결합 여유를 더한다. | macro lookback, `delta_6m`, z-score 정의 |
| EOD DAG 수집 | `dags/eod_pipeline_dag.py` | 1 target trading day | 일일 EOD run은 마지막 완료 US trading day를 확정 수집한다. | trading calendar |
| EOD Bronze -> Silver feature input | `src/pretrend/pipeline/features/eod_features.py` | 130일 | `ma_120`에 주말/휴일 buffer를 더한 calendar-day lookback이다. `vol_60d`, RSI, ATR은 이 범위 안에 포함된다. | EOD rolling feature 정의 |
| EOD Silver -> Gold input | `src/pretrend/pipeline/features/gold_eod_features.py` | target date | Silver에서 계산된 feature를 Gold fact mart로 투영한다. 파일 read는 target symbol/month partition으로 제한한다. | symbol/month partition pruning |
| Gold -> Postgres Macro sync | `src/pretrend/pipeline/sync/gold_postgres.py` | 35일 | Macro Gold rolling rebuild와 같은 범위를 다시 읽어 mirror revision을 흡수한다. | Macro DAG rebuild window |
| Gold -> Postgres EOD sync | `src/pretrend/pipeline/sync/gold_postgres.py` | 0일 | 일반 scheduled EOD는 과거 row를 rolling rewrite하지 않는다. Corporate action 등 과거 대량 재작성은 명시적 backfill/full sync로 처리한다. | `PRETREND_GOLD_SYNC_FULL`, historical prepend 절차 |

## 4. Backfill과 historical prepend 예외

다음 경우는 위 scheduled window의 예외다.

- 새 개발환경 bootstrap 또는 빈 data lake 복구
  - `reproduce.py` 또는 `pretrend-backfill-once`가 Macro/EOD Bronze -> Silver -> Gold와 Gold -> Postgres sync를 1회 수행한다.
  - 기본 historical start는 운영 bootstrap 설정을 따른다.

- 과거 기간 추가 수집
  - 예: 2003-01-01부터 2009-12-31까지 historical prepend.
  - raw/bronze/silver/gold를 추가 생성한 뒤 `PRETREND_GOLD_SYNC_START_DATE`로 Postgres sync 시작일을 명시한다.

- 전체 mirror 재동기화
  - `PRETREND_GOLD_SYNC_FULL=1`은 Postgres mirror를 전체 Gold Parquet 기준으로 다시 upsert하는 one-off 운영 모드다.
  - scheduled default로 사용하지 않는다.

## 5. 변경 통제

처리 윈도우를 바꿀 때는 아래 순서를 따른다.

1. 변경하려는 feature dependency를 먼저 확인한다.
   - Macro: YoY, rolling, delta, z-score, PIT calendar 결합.
   - EOD: MA, volatility, RSI, ATR, symbol/date partition.

2. 코드 상수를 수정한다.
   - DAG rebuild window, feature lookback, sync lookback을 각각 필요한 위치에서 바꾼다.

3. Upstream output rewrite 범위가 바뀌면 downstream sync lookback도 같이 바꾼다.
   - Macro rebuild가 35일에서 60일로 늘면 Macro Postgres sync lookback도 60일 이상이어야 한다.

4. 이 문서를 업데이트한다.
   - 표의 현재 값, 산정 기준, 같이 확인할 값을 함께 갱신한다.

5. old corrupt partition 방어 테스트를 유지한다.
   - 변경된 윈도우 밖의 손상 partition이 scheduled run을 깨지 않아야 한다.

## 6. 관련 테스트

처리 윈도우와 partition pruning은 다음 테스트가 수문장 역할을 한다.

- `tests/pipeline/test_macro_features.py::test_load_bronze_macro_scopes_to_required_partitions`
- `tests/pipeline/test_gold_macro_feature_v1.py::test_load_silver_macro_scopes_to_requested_window`
- `tests/pipeline/test_gold_eod_features.py::test_ge5_load_silver_scopes_to_requested_window_and_symbols`
- `tests/pipeline/test_eod_silver_writer_idempotency.py::test_load_bronze_eod_scopes_to_requested_dates_and_symbols`
- `tests/pipeline/test_calendar.py`
- `tests/pipeline/sync/test_gold_postgres_sync_scope.py`

관련 변경 후에는 최소한 아래 범위를 실행한다.

```bash
conda run -n pretrend_pytest python -m pytest ^
  tests\pipeline\test_calendar.py ^
  tests\pipeline\test_macro_features.py ^
  tests\pipeline\test_gold_macro_feature_v1.py ^
  tests\pipeline\test_eod_silver_writer_idempotency.py ^
  tests\pipeline\test_gold_eod_features.py ^
  tests\pipeline\sync\test_gold_postgres_sync_scope.py ^
  -q
```
