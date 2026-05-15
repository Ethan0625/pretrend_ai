# P30-3 — Data Bootstrap & DB Restore Contract

## 0. 문서 메타

- Task ID: `P30-3`
- Title: `Data Bootstrap & DB Restore Contract`
- Status: `DONE`
- Phase: `P30 — Reproducible Runtime & Data Bootstrap`
- Parent: `P30`
- Source(anchor): `.agent/task/P30-3_data_bootstrap_db_restore_contract.md`
- Last Updated: `2026-05-15`
- Owner: `Codex`

### 병렬 실행 메타

- `parallel_safe`: `conditional`
- `depends_on`: `[P30-1]`
- `blocks`: `[P30-4]`
- `executor`: `local`
- `file_scope`:
  - 수정: [`docs/operation/reproducible_runtime_contract.md`, `docs/operation_guide.md`, `docs/environment.md`, `README.md`, `Makefile`, `scripts/`]
  - 읽기전용: [`dags/`, `src/pretrend/pipeline/`, `src/pretrend/observability/`, `migrations/`]
- `merge_strategy`: `review`

---

## 1. 목표

- 현재 문제: 신규 머신에서 serving DB를 restore할지 backfill할지, 어떤 순서로 복구할지 계약이 명확하지 않다.
- 이번 task의 목표: DB dump/restore를 운영 복구 1순위로 고정하고, backfill은 reconstruction fallback으로 문서화한다.
- 기대 효과: 정전/장비 교체/신규 clone 상황에서 데이터 복구 순서가 명확해진다.

---

## 2. 작업 범위

### 2.1 In-Scope

- `pg_dump -Fc` backup command 문서화.
- `pg_restore -l` catalog validation 문서화.
- 별도 DB/volume restore validation 절차 문서화.
- 기존 backfill/DAG/runner 조합 audit.
- sample/backfill mode 구분.

### 2.2 Out-of-Scope

- 운영 DB를 직접 restore로 덮어쓰기.
- full historical LLM explainability backfill.
- 새 backfill runner 선제 구현.
- external API key 실제 값 문서화.

### 2.3 수정 금지

- active `pretrend_obs` DB overwrite.
- `docker compose down -v`.
- explainability cache를 mock/full history로 채우는 작업.
- PIT/idempotent write 계약 변경.

---

## 3. 설계 불변식

- 운영 복구 1순위는 dump restore다.
- backfill은 dump가 없거나 오래된 경우의 reconstruction fallback이다.
- restore 검증은 별도 DB/volume에서 수행한다.
- explainability historical backfill은 scope/window/cache key 계약이 정해지기 전까지 수행하지 않는다.

---

## 4. 구현 요구사항

1. DB backup/restore runbook을 operation docs에 추가한다.
2. restore 검증용 별도 DB/volume 절차를 정의한다.
3. data lake bootstrap과 serving DB restore를 분리해 설명한다.
4. 기존 backfill entrypoint를 audit하고 새 runner 필요 여부를 기록한다.
5. README 신규 clone 절차에 restore-first/backfill-fallback 흐름을 추가한다.

---

## 5. 검증 방법

운영 DB에 쓰지 않는 dump catalog 검증:

```bash
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /backups/pretrend_test.dump'
docker compose exec -T postgres sh -c 'test -s /backups/pretrend_test.dump'
docker compose exec -T postgres sh -c 'pg_restore -l /backups/pretrend_test.dump' >/tmp/pretrend_test_restore.list
```

restore 검증은 별도 DB/volume 절차가 문서화된 뒤 수행한다.

---

## 6. 완료 기준

- [x] backup command가 문서화되어 있다.
- [x] dump catalog validation이 문서화되어 있다.
- [x] active DB를 덮어쓰지 않는 restore 검증 절차가 있다.
- [x] backfill은 fallback으로 명시되어 있다.
- [x] 신규 runner 생성 여부가 audit 근거와 함께 결정되어 있다.

## 7. 완료 기록

### 변경 요약

- `pg_dump -Fc` backup command와 `pg_restore -l` catalog validation 절차를 README / operation docs / runtime contract에 반영했다.
- active `pretrend_obs` DB를 덮어쓰지 않는 별도 DB/volume restore validation 절차를 문서화했다.
- data lake backfill과 serving DB restore를 분리했고, backfill은 dump가 없거나 stale한 경우의 reconstruction fallback으로 고정했다.
- 기존 bootstrap entrypoint를 audit했다.
  - Macro/EOD file data lake: `macro_job.py`, `eod_job.py`, `macro_pipeline_dag`, `eod_pipeline_dag`
  - Gold Parquet -> Postgres: `gold_postgres_sync_dag`, `sync_gold_macro`, `sync_gold_eod`
  - Similarity derived table: `similarity_build_dag`
  - Explainability cache: `explainability_build_dag` latest/on-demand only
  - Text observability: `text.backfill`, `gold_llm_backfill`
- P30-3에서는 새 runner를 만들지 않는 것으로 결정했다. 기존 DAG/function 조합을 문서화된 operator sequence로 사용하고, P30-4 이후 필요 시 `ops/worker` wrapper를 별도 task로 검토한다.

### 수정 파일

- `README.md`
- `docs/operation/reproducible_runtime_contract.md`
- `docs/operation_guide.md`
- `docs/environment.md`
- `.agent/task/P30-3_data_bootstrap_db_restore_contract.md`
- `.agent/task/P30_parent_reproducible_runtime.md`
- `.agent/TASK_QUEUE.md`

### 검증 결과

```bash
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /backups/pretrend_test.dump'
```

- PASS, exit code 0.
- `pg_dump` emitted a Timescale internal continuous aggregate circular foreign-key warning, but the custom dump was created successfully.

```bash
docker compose exec -T postgres sh -c 'test -s /backups/pretrend_test.dump'
```

- PASS.

```bash
docker compose exec -T postgres sh -c 'pg_restore -l /backups/pretrend_test.dump' >/tmp/pretrend_test_restore.list
```

- PASS.
- `/tmp/pretrend_test_restore.list`: 3664 lines.
- `.local/backups/pretrend_test.dump`: 54M.
- Catalog contains expected data entries:
  - `alembic_version`
  - `gold_macro_features`
  - `gold_eod_features`
  - `gold_market_state_similarity_feature`
  - `similarity_regime`
  - `similarity_gold`
  - `explainability_cache`

```bash
docker compose ps
```

- PASS.
- `pretrend-api`: healthy.
- `pretrend-postgres`: healthy.

### 남은 이슈

- 별도 DB/volume에 실제 restore를 수행하는 검증은 P30-4에서 처리한다.
- 기존 pipeline 구현은 `PRETREND_DATA_ROOT`를 사용한다. Docker runtime mount target인 `PRETREND_DATA_DIR=/app/data`와 같은 경로로 맞추는 호환 규칙을 문서화했으며, 코드/env 정식 통합은 별도 task가 필요하면 분리한다.
