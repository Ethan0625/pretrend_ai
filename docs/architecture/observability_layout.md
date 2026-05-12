# Observability Layout

> 🔄 **Observability Track 구현자용 레이아웃 참조**
>
> 본 문서는 2026Q2 방향 재정의 이후 구현자가 30초 안에 "어디에 둬야 하는가"를 판단하기 위한 구조 매트릭스다.
> 트랙 분리 원칙은 [`track_separation.md`](./track_separation.md), 단계 계획은 [`.agent/REFACTOR_2026Q2.md`](../../.agent/REFACTOR_2026Q2.md)를 우선 참조한다.

## 1. 목적

- 본 문서는 구현자용 단일 레이아웃 참조다.
- 결정 근거를 새로 정의하지 않고, 이미 확정된 구조를 한 곳에 모아 보여준다.
- `track_separation.md`는 트랙 boundary 원칙, `REFACTOR_2026Q2.md`는 phase 계획, 본 문서는 실제 디렉토리 위치 결정을 담당한다.

## 2. 전체 디렉토리 트리

```text
pretrend_ai/
├── src/pretrend/
│   ├── pipeline/             # Infrastructure (공유)
│   ├── observability/        # Observability Track (신규)
│   │   ├── regime/
│   │   ├── similarity/
│   │   └── explainability/
│   ├── models/               # Observability Track 신규
│   ├── config.py             # Observability Track 신규
│   ├── strategy_engine/      # Personal Track (동결)
│   ├── backtest/             # Personal Track (동결)
│   ├── paper/                # Personal Track (동결)
│   └── broker/               # Personal Track (동결)
├── apps/                     # Observability Track (Phase 2~3)
│   ├── api/                  # FastAPI
│   └── web/                  # React + Vite
├── migrations/               # Observability Track (Alembic)
├── dags/                     # Mixed (track별 명시)
├── tests/                    # Mixed (track별 위치 분리)
├── docs/
├── .agent/
├── docker-compose.yml
└── pyproject.toml
```

## 3. 트랙별 책임 매트릭스

| 경로 | 트랙 | 책임 | 상태 |
|---|---|---|---|
| `src/pretrend/pipeline/ingest/` | Infrastructure | Bronze 수집 | 운영 |
| `src/pretrend/pipeline/features/` | Infrastructure | Silver/Gold feature | 운영 |
| `src/pretrend/pipeline/calendar/` | Infrastructure | Release evidence | 운영 |
| `src/pretrend/observability/regime/` | Observability | 시장 상태 관측 | Phase 1 추출 예정 |
| `src/pretrend/observability/similarity/` | Observability | 유사도 비교 | Phase 2 신설 |
| `src/pretrend/observability/explainability/` | Observability | LLM 설명 layer | Phase 2 신설 |
| `src/pretrend/models/` | Observability | SQLAlchemy + Pydantic | Phase 0 |
| `src/pretrend/config.py` | Observability | 환경/DB 설정 | Phase 0 |
| `src/pretrend/strategy_engine/{axis_features, axis_horizon_state, market_position}` | Observability 이전 예정 | 관측 로직 추출 | 동결 → 이전 |
| `src/pretrend/strategy_engine/{allocation, policy_selector, sell_advisor, universe}` | Personal | 투자 판단 | 동결 |
| `src/pretrend/backtest/` | Personal | 백테스트 | 동결 |
| `src/pretrend/paper/`, `src/pretrend/broker/` | Personal | 페이퍼/브로커 | 동결 |
| `apps/api/` | Observability | FastAPI | Phase 2 |
| `apps/web/` | Observability | React Dashboard | Phase 3 |
| `migrations/` | Observability | Alembic | Phase 0 |
| `dags/paper_trading_dag.py`, `dags/broker_mock_trading_dag.py` | Personal | 페이퍼/모의 거래 DAG | 동결 |
| `dags/macro_pipeline_dag.py`, `dags/eod_pipeline_dag.py` | Infrastructure | 데이터 수집 DAG | 운영 |
| `dags/strategy_engine_dag.py` | Personal | Strategy snapshot DAG | 동결 |

## 4. Import 규칙

- Observability Track 모듈은 `pretrend.strategy_engine`, `pretrend.backtest`, `pretrend.paper`, `pretrend.broker`를 import 하지 않는다.
- Personal Track 모듈은 `pretrend.observability`, `pretrend.config`, `pretrend.models`를 import 하지 않는다.
- Infrastructure(`pretrend.pipeline`)는 양쪽 트랙이 read-only로 import 가능하다.
- 신규 파일 추가 시 아래 검증 명령을 사용한다.

```bash
grep -rn "from pretrend.strategy_engine\|from pretrend.backtest\|from pretrend.paper\|from pretrend.broker" \
  src/pretrend/observability/ src/pretrend/models/ src/pretrend/config.py apps/
# 출력 0줄이어야 함
```

## 5. tests/ 디렉토리 매핑

- `tests/pipeline/` — Infrastructure
- `tests/observability/` (신규) — Observability Track
- `tests/test_config.py`, `tests/test_models_base.py` — Phase 0 신규
- 기존 `tests/pipeline/strategy_engine/`, `tests/pipeline/backtest/`, `tests/pipeline/paper/` — Personal Track (동결)
- Phase 1 추출 시 `tests/pipeline/strategy_engine/test_axis_*`는 `tests/observability/regime/axis/`로 함께 이전한다.

## 6. 위치 결정 빠른 가이드

- Q: 새 시장 관측 지표 추가
  A: `src/pretrend/observability/regime/`
- Q: 새 매수/매도 로직 추가
  A: 추가 금지. Personal Track은 동결 상태다.
- Q: 새 LLM 설명 prompt 추가
  A: `src/pretrend/observability/explainability/`
- Q: 새 dashboard 페이지 추가
  A: `apps/web/`와 `apps/api/routers/`
- Q: 새 DB 테이블 추가
  A: `src/pretrend/models/<domain>.py`와 `migrations/versions/<n>_<name>.py`
- Q: 새 Airflow DAG 추가
  A: `dags/`에 `observability_*_dag.py`처럼 트랙 prefix를 명확히 둔다.
- Q: 새 환경 변수 추가
  A: `src/pretrend/config.py` 필드 추가 후 `.env.example`를 함께 갱신한다.

## 7. 변경 이력 갱신 규칙

- 신규 디렉토리 추가 시 본 문서 §2, §3을 함께 갱신한다.
- 트랙 이동 시 본 문서 §3의 상태를 갱신한다.
- 갱신 시 `docs/changelog.md`에 한 줄 남긴다.

## 8. 참조 문서

- [docs/architecture/track_separation.md](/home/redtable/Desktop/ethan/pretrend/pretrend_ai/docs/architecture/track_separation.md)
- [.agent/REFACTOR_2026Q2.md](/home/redtable/Desktop/ethan/pretrend/pretrend_ai/.agent/REFACTOR_2026Q2.md)
- [.agent/DIRECTION.md](/home/redtable/Desktop/ethan/pretrend/pretrend_ai/.agent/DIRECTION.md)
- [README.md](/home/redtable/Desktop/ethan/pretrend/pretrend_ai/README.md)

## 9. 변경 이력

- 2026-05-12: P17-5로 초안 작성.
