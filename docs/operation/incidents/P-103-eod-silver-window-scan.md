Markers: operation
Status: active

# P-103 — EOD Silver Incremental Backfill의 Bronze 전체 스캔

## 1. 요약

- ID: `P-103`
- 날짜: 2026-05-27
- 영역: EOD Pipeline
- 심각도: High
- 상태: Resolved
- 관련 커밋: P32 runtime hardening work
- 관련 테스트:
  - `tests/pipeline/test_eod_silver_writer_idempotency.py`
  - `tests/pipeline/test_gold_eod_features.py`
  - `tests/pipeline/sync/test_gold_postgres_sync_scope.py`
- 관련 계약 문서:
  - `docs/architecture/pipeline_window_policy.md`

---

## 2. 깨진 계약

Scheduled/incremental path에서는 parquet를 읽기 전에 대상 partition 후보를 먼저 좁혀야 한다.

```text
전체 rglob 후 read/filter 금지
target date window -> source partition 후보 -> read
```

---

## 3. 증상

`2026-05-21`부터 `2026-05-26`까지 짧은 증분 backfill을 실행했는데, 작업 시간이 전체 backfill처럼 길어졌다.

처음 실행한 one-off 컨테이너는 1시간 timeout에 걸렸고, `pretrend_ai_backfill-once_run_...` 컨테이너가 계속 실행 중이었다.

---

## 4. 기대 동작

증분 backfill은 출력 구간과 rolling lookback에 필요한 Bronze partition만 읽어야 한다.

---

## 5. 근본 원인

- 코드 경로: `src/pretrend/pipeline/features/eod_features.py`
- 데이터 경로: `data/bronze/eod/daily_prices`
- 문서/계약 경로: `pipeline_window_policy`의 partition pruning 원칙
- 누락된 검증: symbol 미지정 상태에서 EOD Silver가 old corrupt partition을 읽지 않는 테스트 부재
- 잘못된 가정: 날짜 필터를 DataFrame read 이후에 적용해도 운영 규모에서 충분하다고 가정

`_list_bronze_eod_files()`가 `target_symbols`가 없을 때 전체 `bronze_root.rglob("eod.parquet")`를 수행했다.

---

## 6. 수정

- 실행 중인 one-off backfill 컨테이너를 중지했다.
- EOD Silver Bronze loader를 `load_start_date~feature_end_date` 날짜 window 기반 glob로 수정했다.
- symbol 미지정 상태에서도 `symbol=*`와 날짜 partition 후보만 읽도록 변경했다.
- old corrupt partition 방어 테스트를 추가했다.

---

## 7. 검증

- `conda run -n pretrend_pytest pytest tests/pipeline/test_eod_silver_writer_idempotency.py -q --tb=short` -> `4 passed`
- EOD window + Gold EOD + sync scope 관련 테스트 -> `19 passed`
- Docker `backfill-once` 재실행 결과:
  - range: `2026-05-21` ~ `2026-05-26`
  - EOD Bronze/Silver/Gold rows: `124`
  - Postgres EOD watermark: `2026-05-26`
  - Postgres Macro watermark: `2026-05-26`

---

## 8. 예방 / 가드

- `tests/pipeline/test_eod_silver_writer_idempotency.py::test_load_bronze_eod_scopes_to_requested_dates_without_symbol_filter`
- `docs/architecture/pipeline_window_policy.md`에 관련 테스트 추가
- 증분 backfill 시 `PRETREND_BACKFILL_START_DATE`, `PRETREND_BACKFILL_END_DATE`, `PRETREND_GOLD_SYNC_START_DATE`를 함께 지정

---

## 9. 남은 부채

- 큰 범위 historical backfill은 여전히 오래 걸릴 수 있다.
- 향후 full historical path와 scheduled incremental path를 command level에서 더 명확히 분리할 수 있다.

---

## 10. 메모

출력 범위는 처음부터 제한되어 있었지만, 입력 read 비용이 전체 스캔에 가까웠던 것이 핵심 문제였다.
