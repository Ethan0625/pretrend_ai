# 운영 장애 시나리오 카탈로그

Markers: testing, contract
Status: active

## 1. 목적

이 문서는 pytest를 "많은 테스트 모음"이 아니라 운영 장애를 미리 막는 수문장으로 만들기 위한 기준이다. 테스트를 추가할 때는 먼저 어떤 장애를 막을지 정하고, 그 장애를 재현하는 synthetic test data를 고정한 뒤, pytest가 그 데이터를 기반으로 운영 약속을 검증해야 한다.

테스트의 기본 질문은 다음과 같다.

- 이 테스트가 깨지면 실제 운영 흐름에서 무엇이 망가졌다고 볼 수 있는가?
- 장애를 재현하는 입력 데이터가 repo 안에 작고 결정적으로 고정되어 있는가?
- 외부 API, 실 DB dump, 현재 날짜, 운영자의 로컬 상태 없이 재현되는가?
- 실패 메시지가 깨진 운영 약속을 바로 설명하는가?

## 2. 작성 원칙

운영 장애 시나리오 테스트는 아래 순서로 작성한다.

1. 시나리오 ID를 정한다. 예: `OFS-001`.
2. 장애 조건을 한 문장으로 쓴다. 예: "과거 구간 backfill 후 Postgres sync가 최신 watermark 이후만 읽어 2003-2009 데이터가 serving DB에 들어가지 않는다."
3. synthetic fixture를 만든다. fixture는 `tests/fixtures/operational_scenarios/<scenario-id>/` 아래에 둔다. 데이터가 작으면 테스트 파일 안의 builder 함수로 두어도 되지만, docstring에 시나리오 ID를 반드시 남긴다.
4. 기대 불변조건을 assert한다. 예: historical start date가 지정되면 sync lower bound가 watermark보다 과거로 내려간다.
5. marker는 새 분류를 만들기보다 기존 `contract`, `invariant`, `db`, `dag`, `slow`를 사용한다.
6. gate를 정한다. 빠르고 외부 의존성이 없으면 `fast`, DB나 Docker runtime이 필요하면 `runtime`, Airflow task graph는 `dags`에 둔다.

fixture는 production dump를 축소한 사본이 아니라, 운영 장애를 최소 행으로 재현하는 데이터여야 한다. 외부 provider 응답을 그대로 저장하는 대신 필요한 column과 edge case만 남긴다.

## 3. 우선순위

| 우선순위 | 기준 |
| --- | --- |
| P0 | 이미 운영 중 맞았거나, 재현성/serving/API를 직접 깨뜨리는 장애. 기본적으로 다음 변경 전에 테스트로 고정한다. |
| P1 | 아직 장애는 아니지만 데이터 신뢰도, freshness, DAG 운영을 흔들 수 있는 장애. |
| P2 | 비용, 성능, 큰 통합 환경이 필요한 검증. 수동 운영 체크에서 pytest로 점진 이전한다. |

## 4. P0 시나리오

| ID | 장애 시나리오 | Synthetic data anchor | pytest anchor | Gate | 상태 |
| --- | --- | --- | --- | --- | --- |
| `OFS-001` | 2003-2009 같은 과거 구간을 뒤늦게 backfill했지만 Postgres sync가 최신 watermark 기준 일부 기간만 읽어 serving DB에 반영되지 않는다. | inline fixture 또는 `tests/fixtures/operational_scenarios/ofs_001_historical_backfill_sync/` | `tests/pipeline/sync/test_gold_postgres_sync_scope.py` | `fast`, `runtime` | 구현됨 |
| `OFS-002` | data lake가 비어 있고 bootstrap marker가 없는데 manual DAG가 정상 task부터 실행되어 raw/bronze/silver/gold가 없는 상태로 실패한다. | inline runner doubles 또는 `tests/fixtures/operational_scenarios/ofs_002_markerless_bootstrap/` | `tests/ops/test_backfill_once.py`, `tests/dags/test_data_lake_bootstrap_dag_contract.py`, `tests/dags/test_gold_postgres_sync_dag.py` | `fast`, `dags` | 구현됨 |
| `OFS-003` | 전략 리포트 payload에 `NaN`, `Inf`, `Decimal('NaN')`, `None` 계열 값이 포함되어 `requests.post(json=...)` 또는 FastAPI 응답이 500으로 깨진다. | inline payload 또는 `tests/fixtures/operational_scenarios/ofs_003_non_finite_report_payload/` | `tests/pipeline/strategy_engine/test_json_safety.py`, `tests/api/test_report.py` | `fast` | 구현됨 |
| `OFS-004` | EOD warmup 부족이나 상대강도 계산 불가능 상태에서 `relative_strength`가 null이 되고, downstream report가 이를 숫자로 가정해 실패한다. | inline DataFrame / compact payload | `tests/pipeline/strategy_engine/test_universe.py`, `tests/pipeline/strategy_engine/test_report_context_env.py` | `fast` | 구현됨 |
| `OFS-005` | Bronze/Silver/Gold 재실행 시 동일 grain에 중복 append가 남거나 partial snapshot이 노출된다. | inline DataFrame 또는 `tests/fixtures/operational_scenarios/ofs_005_idempotent_snapshot_write/` | `tests/pipeline/test_eod_silver_writer_idempotency.py`, `tests/pipeline/test_gold_eod_features.py` | `fast` | 구현됨 |
| `OFS-006` | Macro Gold 생성 시 release evidence가 어긋나 `selected_release_date >= trade_date`가 되어 미래 정보가 누출된다. 지켜야 할 invariant는 `selected_release_date < trade_date`이다. | inline calendar/macro rows 또는 `tests/fixtures/operational_scenarios/ofs_006_pit_release_guard/` | `tests/pipeline/test_gold_macro_feature_v1.py` | `fast` | 구현됨 |
| `OFS-007` | 새 clone 또는 새 머신에서 Docker compose, volume, `.env`, restore/backfill 절차가 문서와 달라 재현되지 않는다. | compose/env/doc contract text | `tests/ops/test_reproducible_runtime_contract.py` | `runtime` | 구현됨 |
| `OFS-008` | FastAPI 인증, schema, error contract가 바뀌어 dashboard/API client가 같은 endpoint를 더 이상 안전하게 읽지 못한다. | API client fixtures | `tests/api/*` | `fast`, `contracts` | 구현됨 |

## 5. P1 시나리오

| ID | 장애 시나리오 | Synthetic data anchor | pytest anchor | Gate | 상태 |
| --- | --- | --- | --- | --- | --- |
| `OFS-101` | serving mirror의 row coverage나 max date가 Gold Parquet SOT보다 뒤처졌지만 health/API는 정상처럼 보인다. | inline freshness snapshots | `tests/ops/test_serving_freshness.py` | `fast`, `runtime` | 구현됨 |
| `OFS-102` | Airflow DAG task graph가 import는 되지만 bootstrap guard, sync 순서, report fail-open 순서가 바뀐다. | DAG task graph fixture | `tests/dags/test_data_lake_bootstrap_dag_contract.py`, `tests/dags/test_gold_postgres_sync_dag.py` | `dags` | 구현됨 |
| `OFS-103` | explanation/report text가 관측 설명을 넘어 예측, 추천, 매매 판단으로 변한다. | forbidden term fixture | `tests/observability/explainability/test_invariant_filter.py`, `tests/pipeline/text/test_text_failopen.py` | `fast`, `contracts` | 구현됨 |
| `OFS-104` | Calendar/FRED vintage coverage가 부족해 Gold Macro는 만들어지지만 evidence column이 비어 의미가 약해진다. | inline release calendar rows | `tests/pipeline/test_gold_macro_feature_v1.py` | `fast` | 구현됨 |

## 6. P2 시나리오

| ID | 장애 시나리오 | Synthetic data anchor | pytest anchor | Gate | 상태 |
| --- | --- | --- | --- | --- | --- |
| `OFS-201` | 별도 restore DB에서 dump가 복구되지 않거나 Alembic version/table contract가 깨진다. | shadow Postgres DB | `tests/ops/test_restore_shadow_db.py` | `runtime`, `slow`, `db` | 구현됨 |
| `OFS-202` | 개별 task 테스트는 통과하지만 market-state similarity feature -> similarity row -> explainability cache 연결에서 깨진다. | inline synthetic market-state rows | `tests/ops/test_observability_chain_smoke.py` | `runtime`, `slow`, `db` | 구현됨 |
| `OFS-203` | provider quota/rate limit/error 응답을 만났을 때 raw ingest가 실패 상태와 retry 가능 상태를 구분하지 못한다. | provider response fixtures | `tests/pipeline/test_ingest_macro.py`, `tests/pipeline/text/test_text_failopen.py` | `fast`, `runtime` | 구현됨 |
| `OFS-204` | migration/model 문서는 맞지만 격리된 test DB의 serving table이 최소 synthetic row를 insert/read하지 못한다. | isolated `pretrend_test*` DB synthetic rows | `tests/ops/test_db_synthetic_data_contract.py` | `runtime`, `slow`, `db` | 구현됨 |

## 7. 테스트 파일 규칙

운영 시나리오 테스트는 다음 중 하나를 만족해야 한다.

- 테스트 함수명 또는 class명에 시나리오 ID를 포함한다.
- docstring 첫 줄에 시나리오 ID와 막는 장애를 쓴다.
- fixture directory의 `README.md`에 시나리오 ID, 입력, 기대 출력, 실패 의미를 쓴다.

예:

```python
def test_ofs_001_historical_backfill_sync_lower_bound(...):
    """OFS-001: historical backfill은 최신 watermark보다 과거 구간도 sync해야 한다."""
```

새 테스트가 단순 함수 동작 확인인지 운영 장애 방어인지 헷갈리면, 먼저 이 문서에 시나리오를 추가하고 상태를 `후속`으로 둔다. 구현이 붙으면 pytest anchor와 상태를 갱신한다.

## 8. 변경 이력

- 2026-05-17: 운영 장애 시나리오 카탈로그와 synthetic fixture 기준 신설.
- 2026-05-17: P0/P1 fast·DAG 시나리오 anchor 구현 상태 반영.
- 2026-05-17: P2 shadow restore, observability chain smoke, provider error taxonomy anchor 구현 상태 반영.
- 2026-05-17: P2 DB synthetic row insert/read smoke anchor 추가.
