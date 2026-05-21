# Runtime Layout

Markers: architecture, contract
Status: active

> 🟢 **Market Data Platform 구현자용 레이아웃 참조**
>
> 본 문서는 구현자가 30초 안에 "어디에 둬야 하는가"를 판단하기 위한 구조 매트릭스다.
> 현재 운영 경계는 [`track_separation.md`](./track_separation.md)를 참조한다.

## 1. 목적

- 본 문서는 구현자용 단일 레이아웃 참조다.
- 결정 근거를 새로 정의하지 않고, 이미 확정된 구조를 한 곳에 모아 보여준다.
- `track_separation.md`는 현재 운영 영역과 보관된 실행 실험 영역의 boundary 원칙, 본 문서는 실제 디렉토리 위치 결정을 담당한다.

## 2. 전체 디렉토리 트리

```text
pretrend_ai/
├── src/pretrend/
│   ├── pipeline/             # Infrastructure (공유)
│   ├── observability/        # read-only 관측 표면
│   │   ├── regime/
│   │   │   └── axis/         # axis_features 추출 완료 (P18)
│   │   │   └── horizon/      # axis_horizon_state 추출 완료 (P19)
│   │   │   └── position/     # market_position 추출 완료 (P20)
│   │   │   └── rotation/     # group_transition 추출 완료 (P21)
│   │   │   └── transition/   # next_step 추출 완료 (P22)
│   │   ├── similarity/
│   │   └── explainability/   # legacy report + LLM explainability layer (P22/P27)
│   ├── models/               # serving model/schema
│   ├── config.py             # runtime config
│   ├── strategy_engine/      # legacy execution reference
│   ├── backtest/             # legacy execution reference
│   ├── paper/                # legacy execution reference
│   └── broker/               # legacy execution reference
├── apps/
│   └── web/                  # React + Vite dashboard
├── migrations/               # Alembic schema migration
├── dags/                     # data platform / archived execution DAG 명시
├── tests/                    # gate와 domain별 위치 분리
├── docs/
├── .agent/
├── docker/
├── requirements/
├── docker-compose.yml
└── pyproject.toml
```

## 3. 책임 매트릭스

| 경로 | 영역 | 책임 | 상태 |
|---|---|---|---|
| `src/pretrend/pipeline/ingest/` | Infrastructure | Bronze 수집 | 운영 |
| `src/pretrend/pipeline/features/` | Infrastructure | Silver/Gold feature | 운영 |
| `src/pretrend/pipeline/calendar/` | Infrastructure | Release evidence | 운영 |
| `src/pretrend/pipeline/sync/` | Observability | Gold Parquet → Postgres mirror sync | Phase 2 — P25 완료 |
| `src/pretrend/observability/regime/` | Observability | 시장 상태 관측 | Phase 1 추출 진행 |
| `src/pretrend/observability/regime/axis/` | Observability | axis_features 관측 지표 | Phase 1 추출 완료 (2026-05-13) |
| `src/pretrend/observability/regime/horizon/` | Observability | axis_horizon_state 관측 엔진 | Phase 1 추출 완료 (2026-05-13) |
| `src/pretrend/observability/regime/position/` | Observability | market_position 관측 상태 벡터 | Phase 1 추출 완료 (2026-05-13) |
| `src/pretrend/observability/regime/rotation/` | Observability | group_transition tactical group rotation 관측 | Phase 1 추출 완료 (2026-05-13). 코드 심볼은 group_transition 유지 |
| `src/pretrend/observability/regime/transition/` | Observability | next_step 5/10/20/60/120D sojourn / transition hazard 관측 | Phase 1 추출 완료 (2026-05-13). 기존 위치는 shim 유지 |
| `src/pretrend/observability/similarity/` | Observability | multi-view market structure similarity (regime view + gold view) | Phase 2 — P26 완료 |
| `src/pretrend/observability/explainability/legacy_report/` | Observability legacy | legacy Telegram bot report_context / report analyzer 경로 | P22 사전 추출, P27-0 package split 완료. root 파일은 shim 유지 |
| `src/pretrend/observability/explainability/llm_client.py` | Observability | LLM provider 추상화 (`VSCodeCodexProvider`) + invariant filter | Phase 2 — P27 완료 |
| `src/pretrend/observability/explainability/{similarity,regime,macro}_explainer.py` | Observability | similarity / regime / macro 3 use case 설명 report builder | Phase 2 — P27 완료 |
| `src/pretrend/observability/explainability/cache.py` | Observability | `explainability_cache` lookup / UPSERT / invalidate | Phase 2 — P27 완료 |
| `src/pretrend/api/` | Observability | FastAPI 골격, 설정, auth, async DB session, Pydantic schema | Phase 2 — P28 완료 |
| `src/pretrend/api/routers/` | Observability | 7 router(health, meta, regime, similarity, macro, eod, explain) | Phase 2 — P28 완료 |
| `tests/api/` | Observability | API auth / health / router 단위 테스트 | Phase 2 — P28 완료 |
| `apps/web/src/main.tsx` | Observability | Vite + React + TypeScript dashboard entry | Phase 3 — P31 완료 |
| `apps/web/src/api/` | Observability | TypeScript API client + TanStack Query hooks | Phase 3 — P31 완료 |
| `apps/web/src/components/` | Observability | Topbar / Sidebar / Toolbar / primitive UI | Phase 3 — P31 완료 |
| `apps/web/src/pages/` | Observability | Overview / Regime / Similarity / Macro / EOD / Explain / Lineage / DAGs 8 screen | Phase 3 — P31 완료 |
| `apps/web/src/charts/` | Observability | Recharts timeline / score chart components | Phase 3 — P31 완료 |
| `src/pretrend/models/` | Observability | SQLAlchemy + Pydantic | Phase 2 — Gold mirror (P24 완료) |
| `src/pretrend/config.py` | Observability | 환경/DB 설정 | Phase 0 |
| `postgres:gold_macro_features` | Observability | Gold Macro Postgres + TimescaleDB hypertable mirror | Phase 2 — P24 완료 |
| `postgres:gold_eod_features` | Observability | Gold EOD Postgres + TimescaleDB hypertable mirror | Phase 2 — P24 완료 |
| `postgres:gold_market_state_similarity_feature` | Observability | regime similarity canonical fixed-width feature table | Phase 2 — P26 완료 |
| `postgres:similarity_regime` | Observability | regime view historical similarity Top-N 결과 | Phase 2 — P26 완료 |
| `postgres:similarity_gold` | Observability | gold view historical similarity Top-N 결과 | Phase 2 — P26 완료 |
| `postgres:explainability_cache` | Observability | similarity/regime/macro LLM 설명 JSON cache | Phase 2 — P27 완료 |
| `src/pretrend/pipeline/strategy_engine/axis_features/` | Observability compat shim | 기존 import path backward compat | shim 유지 |
| `src/pretrend/pipeline/strategy_engine/axis_horizon_state/` | Observability compat shim | 기존 import path backward compat | shim 유지 |
| `src/pretrend/pipeline/strategy_engine/market_position/` | Observability compat shim | 기존 import path backward compat | shim 유지 |
| `src/pretrend/pipeline/strategy_engine/group_transition/` | Observability compat shim | 기존 import path backward compat | shim 유지 |
| `src/pretrend/pipeline/strategy_engine/next_step/` | Observability compat shim | 기존 import path backward compat | shim 유지 |
| `src/pretrend/pipeline/strategy_engine/report_context*.py`, `report_analyzer.py` | Observability compat shim | 기존 import path backward compat | shim 유지 |
| `src/pretrend/pipeline/strategy_engine/{allocation, policy_selector, sell_advisor, universe}` | Legacy execution | 투자 판단 실험 | 동결 |
| `src/pretrend/backtest/` | Legacy execution | 백테스트 | 동결 |
| `src/pretrend/paper/`, `src/pretrend/broker/` | Legacy execution | 페이퍼/브로커 | 동결 |
| `apps/web/` | Observability | React Dashboard | Phase 3 — P31 완료 |
| `docker/Dockerfile.api` | Observability | FastAPI container image | Phase 2 — P28 완료 |
| `docker/Dockerfile.web` | Observability | Frontend container image (Node build → nginx serve) | Phase 3 — P31 완료 |
| `requirements/api.txt` | Observability | FastAPI container 전용 최소 Python runtime dependency | Phase 2 — P28 완료 |
| `docker-compose.yml` (`api` 서비스) | Observability | 로컬 FastAPI 운영 컨테이너 | Phase 2 — P28 완료 |
| `docker-compose.yml` (`web`, `web-node` 서비스) | Observability | dashboard 운영/개발 컨테이너 | Phase 3 — P31 완료 |
| `migrations/` | Observability | Alembic | Phase 2 — Gold schema revision 0002 (P24 완료) |
| `dags/paper_trading_dag.py`, `dags/broker_mock_trading_dag.py` | Legacy execution | 페이퍼/모의 거래 DAG | 동결 |
| `dags/macro_pipeline_dag.py`, `dags/eod_pipeline_dag.py` | Infrastructure | 데이터 수집 DAG | 운영 |
| `dags/gold_postgres_sync_dag.py` | Observability | Postgres mirror sync DAG (11:00 KST) | Phase 2 — P25 완료 |
| `dags/similarity_build_dag.py` | Observability | Similarity build DAG (12:00 KST) | Phase 2 — P26 완료 |
| `dags/explainability_build_dag.py` | Observability | Explainability build DAG (13:00 KST) | Phase 2 — P27 완료 |
| `dags/strategy_engine_dag.py` | Legacy execution | Strategy snapshot DAG | 동결 |

### 3.1 P29 Stage Gate 문서 색인

P29 이후 신규 세션은 아래 문서를 우선 참조한다.

| 문서 | 책임 |
|---|---|
| `docs/architecture/system_map_2026q2.md` | 전체 시스템 지도와 P24~P28 SOT 색인 |
| `docs/architecture/runtime_flow.md` | DAG 실행 순서, freshness, failure propagation, manual recovery |
| `docs/architecture/boundary_contract.md` | dependency / archived execution boundary contract |
| `docs/api/observability_api_contract.md` | Phase 3 dashboard용 read-only API contract |
| `docs/testing/operational_invariant_test_contract.md` | pytest marker와 운영 invariant 검증 contract |

### 3.2 API 환경 변수

| 변수 | 필수 여부 | 책임 |
|---|---|---|
| `PRETREND_API_KEY` | 필수 | `/api/v1/*` 요청의 `X-API-Key` 인증 기준값. `/health`는 인증 예외 |
| `PRETREND_API_CORS_ORIGINS` | 선택 | Phase 3 dashboard 대비 CORS origin 목록 |
| `PRETREND_API_TRUSTED_HOSTS` | 선택 | FastAPI TrustedHostMiddleware 허용 host 목록 |
| `WEB_HOST_PORT` | 선택 | nginx 기반 dashboard host port. 기본 `3000` |
| `WEB_DEV_HOST_PORT` | 선택 | Vite dev server host port. 기본 `5173` |
| `VITE_API_URL` | 선택 | Vite build/dev API base URL. 운영 `web`은 빈 값으로 두고 nginx same-origin proxy 사용 |
| `VITE_API_KEY` | 선택 | Vite dev server 직접 API 호출 시에만 사용. 운영 `web` bundle에는 굽지 않음 |
| `VITE_API_PROXY_TARGET` | 선택 | `web-node` dev proxy 대상. 기본 `http://api:8000` |
| `PRETREND_WEB_TAG` | 선택 | `pretrend-web` image tag. 기본 `local` |

## 4. Import 규칙

- Observability Runtime 모듈은 `pretrend.strategy_engine`, `pretrend.backtest`, `pretrend.paper`, `pretrend.broker`를 import 하지 않는다.
- Legacy execution 모듈은 `pretrend.observability`, `pretrend.config`, `pretrend.models`를 import 하지 않는다.
- Infrastructure(`pretrend.pipeline`)는 현재 운영 영역과 legacy reference가 read-only로 import 가능하다.
- 신규 파일 추가 시 아래 검증 명령을 사용한다.

```bash
grep -rn "from pretrend.strategy_engine\|from pretrend.backtest\|from pretrend.paper\|from pretrend.broker" \
  src/pretrend/observability/ src/pretrend/models/ src/pretrend/config.py apps/
# 출력 0줄이어야 함
```

## 5. tests/ 디렉토리 매핑

- `tests/pipeline/` — Infrastructure
- `tests/observability/` — read-only 관측 표면
- `tests/test_config.py`, `tests/test_models_base.py` — Phase 0 신규
- 기존 `tests/pipeline/strategy_engine/`, `tests/pipeline/backtest/`, `tests/pipeline/paper/` — legacy execution reference
- `tests/observability/regime/axis/` — axis_features 테스트 (P18 추출 완료)
- `tests/observability/regime/horizon/` — axis_horizon_state 테스트 (P19 추출 완료)
- `tests/observability/regime/rotation/` — group_transition 테스트 (P21 추출 완료)
- `tests/observability/regime/transition/` — next_step 테스트 (P22 추출 완료)
- `tests/observability/explainability/` — legacy report analyzer + P27 LLM explainability 테스트
- `tests/observability/similarity/` — multi-view similarity / canonical feature / backfill 테스트 (P26 완료)
- Phase 1 후속 추출 시 남은 `tests/pipeline/strategy_engine/test_axis_*`는 해당 Observability 위치로 함께 이전한다.

## 6. 위치 결정 빠른 가이드

- Q: 새 시장 관측 지표 추가
  A: `src/pretrend/observability/regime/`
- Q: 새 매수/매도 로직 추가
  A: 추가 금지. legacy execution 영역은 동결 상태다.
- Q: 새 LLM 설명 prompt 추가
  A: `src/pretrend/observability/explainability/`
- Q: 새 dashboard 페이지 추가
  A: `apps/web/`와 `apps/api/routers/`
- Q: 새 DB 테이블 추가
  A: `src/pretrend/models/<domain>.py`와 `migrations/versions/<n>_<name>.py`
- Q: 새 Airflow DAG 추가
  A: `dags/`에 `observability_*_dag.py`처럼 domain prefix를 명확히 둔다.
- Q: 새 환경 변수 추가
  A: `src/pretrend/config.py` 필드 추가 후 `.env.example`를 함께 갱신한다.

## 7. 변경 이력 갱신 규칙

- 신규 디렉토리 추가 시 본 문서 §2, §3을 함께 갱신한다.
- 운영 영역 이동 시 본 문서 §3의 상태를 갱신한다.
- 갱신 시 `docs/changelog.md`에 한 줄 남긴다.

## 8. 참조 문서

- [docs/architecture/track_separation.md](track_separation.md)
- [README.md](../../README.md)

## 9. 변경 이력

- 2026-05-12: P17-5로 초안 작성.
- 2026-05-13: P18로 `axis_features`를 `src/pretrend/observability/regime/axis/`로 추출하고 테스트 위치를 갱신.
- 2026-05-13: P19로 `axis_horizon_state`를 `src/pretrend/observability/regime/horizon/`으로 추출하고 테스트 위치를 갱신.
- 2026-05-13: P20으로 `market_position`을 `src/pretrend/observability/regime/position/`으로 추출.
- 2026-05-13: P21로 `group_transition`을 `src/pretrend/observability/regime/rotation/`으로 추출하고 테스트 위치를 갱신.
- 2026-05-13: P22로 `next_step`을 `src/pretrend/observability/regime/transition/`으로 추출하고, `report_context_*`/`report_analyzer`를 `src/pretrend/observability/explainability/`로 사전 추출.
- 2026-05-13: P24로 Gold layer Postgres mirror schema(`gold_macro_features`, `gold_eod_features`)와 SQLAlchemy 모델/Alembic revision 0002를 도입.
- 2026-05-13: P25로 Gold Parquet → Postgres mirror sync runner와 `gold_postgres_sync_dag`를 도입.
- 2026-05-14: P26으로 `src/pretrend/observability/similarity/`, similarity Postgres schema, canonical market-state feature producer, `similarity_build_dag`, historical `what_to_hold` backfill을 도입.
- 2026-05-14: P27로 `src/pretrend/observability/explainability/` LLM layer, `explainability_cache`, `explainability_build_dag`를 도입.
- 2026-05-14: P28로 `src/pretrend/api/` FastAPI read-only API, API key auth, 로컬 docker-compose `api` 서비스를 도입. Phase 2 코드/데이터 layer를 완료하고 외부 노출 운영은 Phase 3 dashboard 이후 별도 task로 분리.
- 2026-05-21: P31로 `apps/web/` React dashboard, 8 screen, Recharts chart, docker-compose `web`/`web-node` 서비스를 도입. Phase 3 코드/UI layer를 완료하고 외부 노출 운영은 별도 task로 유지.
