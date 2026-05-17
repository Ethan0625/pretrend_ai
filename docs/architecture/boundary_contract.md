# 경계 계약

Markers: architecture, contract
Status: active

## 1. 영역 분류

이 문서는 현재 아키텍처의 dependency boundary contract다.

### Shared Infrastructure

Shared Infrastructure는 Observability Runtime과 보관된 strategy experiment가 함께 읽을 수 있는 공통 기반이다.

| Path | 책임 |
| --- | --- |
| `src/pretrend/pipeline/ingest/` | Bronze source ingestion |
| `src/pretrend/pipeline/features/` | Silver/Gold feature builder |
| `src/pretrend/pipeline/calendar/` | Release calendar와 PIT evidence |
| `src/pretrend/pipeline/config/` | 명시적으로 공유된 universe/config 정의 |
| `data/bronze/`, `data/silver/`, `data/gold/` | Parquet data layer |
| `dags/eod_pipeline_dag.py` | Shared EOD data DAG |
| `dags/macro_pipeline_dag.py` | Shared macro data DAG |

### Observability Runtime

Observability Runtime은 market structure observation, historical comparison, explanation, serving DB schema, API, dashboard surface를 소유한다.

| Path | 책임 |
| --- | --- |
| `src/pretrend/observability/regime/` | Regime observation module |
| `src/pretrend/observability/similarity/` | Historical similarity builder와 input |
| `src/pretrend/observability/explainability/` | Evidence-bound report generation과 cache |
| `src/pretrend/api/` | Read-only FastAPI runtime |
| `src/pretrend/models/` | Postgres SQLAlchemy/Pydantic model |
| `src/pretrend/config.py` | Observability runtime settings |
| `src/pretrend/pipeline/sync/` | Gold Parquet to Postgres sync |
| `migrations/` | Postgres/TimescaleDB schema revision |
| `dags/gold_postgres_sync_dag.py` | Gold mirror sync |
| `dags/similarity_build_dag.py` | Similarity build |
| `dags/explainability_build_dag.py` | Explainability cache build |
| `docker/Dockerfile.api`, `requirements/api.txt`, `docker-compose.yml` `api` service | API runtime integration |
| `apps/web/` | Phase 3 dashboard |

### 보관된 Strategy Execution

초기 investing experiment asset은 보관하되, 기본 운영 service로 취급하지 않는다.

| Path | 책임 |
| --- | --- |
| `src/pretrend/pipeline/strategy_engine/{allocation, policy_selector, sell_advisor, universe}` | Investing decision logic |
| `src/pretrend/backtest/` | Backtest와 walk-forward asset |
| `src/pretrend/paper/` | Paper trading |
| `src/pretrend/broker/` | Broker mock/live adapter |
| `dags/strategy_engine_dag.py` | Strategy snapshot DAG |
| `dags/paper_trading_dag.py` | Paper trading DAG |
| `dags/broker_mock_trading_dag.py` | Broker mock DAG |
| `tests/archive/personal/` | Archived regression tests |
| `scripts/telegram_*` | Telegram orchestration asset |

`src/pretrend/pipeline/strategy_engine/*` 아래 compatibility shim은 이동된 Observability module을 re-export하는 임시 호환 asset이다. 신규 strategy feature ownership으로 해석하지 않는다.

## 2. 허용 dependency

허용되는 dependency 방향:

```text
Observability Runtime -> Shared Infrastructure
보관된 전략 실행 -> Shared Infrastructure
```

허용 예시:

- API router는 `pretrend.models`와 Observability query helper를 import할 수 있다.
- Similarity builder는 Postgres mirror data와 shared Gold feature definition을 읽을 수 있다.
- Gold Postgres sync는 Gold Parquet feature contract를 읽는다.
- Archived regression test는 보관된 strategy module을 회귀 검증 목적으로 import할 수 있다.

Observability Runtime이 읽을 수 있는 것:

- `pretrend.pipeline.features.*`
- `pretrend.pipeline.calendar.*`
- 명시적으로 shared로 정의된 `pretrend.pipeline.config.*`
- `pretrend.models.*`
- `pretrend.config`

보관된 strategy execution이 계속 읽을 수 있는 것:

- Shared Gold Parquet feature.
- Existing strategy snapshot과 ledger.
- Archived test fixture.

## 3. 금지 dependency

금지되는 code dependency:

- `src/pretrend/observability/`는 `pretrend.backtest`, `pretrend.paper`, `pretrend.broker`를 import하면 안 된다.
- `src/pretrend/observability/`는 `pretrend.pipeline.strategy_engine.*`의 decision module을 import하면 안 된다.
- `src/pretrend/api/`는 allocation, paper, broker, backtest, strategy decision module을 import하면 안 된다.
- 보관된 strategy execution module은 `pretrend.observability`, `pretrend.models`, API runtime module을 import하면 안 된다.
- Dashboard code는 archived strategy endpoint를 호출하거나 archived strategy snapshot을 읽으면 안 된다.

금지되는 product semantic:

- FastAPI는 allocation, order, buy, sell, hold, target price, target return guidance를 반환하면 안 된다.
- Similarity는 future prediction을 주장하면 안 된다.
- Explainability는 investment decision text를 생성하면 안 된다.
- Dashboard는 historical similarity를 future outcome처럼 표시하면 안 된다.
- LLM output은 observer-only로 남아야 하며 strategy input이 되면 안 된다.

금지되는 schema drift:

- Postgres mirror table은 contract와 migration task 없이 grain/key를 바꾸면 안 된다.
- `explainability_cache`는 explanation scope/window를 구분할 수 없는 cache key로 historical full LLM backfill을 받으면 안 된다.

P29 hotfix 반영:

- Shared snapshot load/write helper는 `src/pretrend/pipeline/utils/snapshot.py`에 둔다.
- Runtime Observability module은 `pretrend.pipeline.backtest._utils` 대신 shared snapshot IO를 import한다.
- One-off historical `what_to_hold` backfill helper는 runtime Observability 밖인 `src/pretrend/pipeline/research/similarity_what_to_hold_backfill.py`로 이동했다.
- `tests/observability/test_boundary_imports.py`가 AST import check로 이 경계를 보호한다.

## 4. 보관 영역 규칙

보관된 strategy execution 규칙:

- 신규 feature를 추가하지 않는다.
- 기본 service enablement를 하지 않는다.
- 신규 dashboard surface를 만들지 않는다.
- 신규 API dependency를 만들지 않는다.
- Archived regression test를 삭제하지 않는다.
- Compatibility fix는 active Observability 또는 CI safety에 필요할 때만 허용한다.

운영 규칙:

- `strategy_engine_dag`, `paper_trading_dag`, `broker_mock_trading_dag`는 paused 또는 disabled 상태를 유지한다.
- Operational audit에서 archived DAG가 unpaused 상태로 발견되면 drift로 기록하고 별도 operational hotfix로 고친다.
- 기존 `state/`, `data/strategy/`, `data/paper/`, `data/broker/` 아래 data는 보존한다.

Review checklist:

- Observability가 archived strategy code를 import했는가?
- 보관된 strategy code가 Observability code를 import했는가?
- API가 decision field를 노출했는가?
- LLM output이 strategy input이 되었는가?
- Postgres table key/grain이 contract 없이 바뀌었는가?
- Archived DAG가 scheduled 또는 unpaused 상태가 되었는가?

## 5. 변경 이력

- 2026-05-15: 초안 작성. P29-3.
- 2026-05-15: P29 hotfix에서 shared snapshot IO 추출 및 historical backfill helper 이동으로 runtime Observability boundary exception 해결.
- 2026-05-16: 문서 기준 언어를 한국어로 정리.
