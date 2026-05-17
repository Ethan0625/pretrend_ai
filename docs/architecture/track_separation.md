# 런타임 경계 계약 — Data Platform vs Legacy Execution

Markers: architecture, contract
Status: active

Version: 2026.05.17
Status: active

---

## 1. Vision

### 1.0 문제 정의

투자 영역에서는 "거시경제 흐름이 중요하다"는 말을 자주 하지만, 실제로 거시 이벤트와 시장 구조 변화가 어떤 방식으로 연결되는지를 반복적으로 확인할 수 있는 개인용 도구는 많지 않다. 본 프로젝트는 투자 전망을 제시하기보다, 무료로 접근 가능한 거시·ETF 데이터를 기반으로 시장 상태를 구조화하고, 특정 시점의 시장 구조가 과거 어떤 구간과 유사하거나 다른지를 재현 가능한 방식으로 관측하는 시스템을 만든다.

### 1.0.1 설계 기준

Pretrend의 공개 운영 기준은 예측 모델이나 자동매매 시스템이 아니라, 시장 판단 이전 단계의 데이터 정합성, 시점 안전성, 재처리 가능성, 운영 재현성이다. 이를 위해 자동화된 스케줄러 기반 수집, Bronze/Silver/Gold 데이터 레이어, Postgres serving mirror, read-only API, freshness monitoring 구조를 운영 기준으로 둔다.

### 1.1 우리가 만들려는 것

> "재현 가능한 Market Data Platform"

핵심 목표는 미래 예측(prediction)이 아니라, **금융·거시 데이터를 재현 가능한 방식으로 수집·정제하고 point-in-time 안전한 feature layer를 유지하는 것**이다. 시장 구조 관측, 유사도 비교, 설명 레이어는 이 데이터 플랫폼을 read-only로 소비하는 활용 표면이다.

### 1.2 우리가 만드는 것이 아닌 것

- 투자 추천 시스템이 아니다.
- AI 매수/매도 신호 시스템이 아니다.
- 수익률 예측 시스템이 아니다.
- GPT wrapper도 아니다.

### 1.3 진짜 목적

**production-grade runtime ownership을 가진 시스템을 운영하는 경험**.

따라서 다음을 최우선으로 본다:
- runtime
- observability
- deployment
- reproducibility
- lineage
- state management
- pipeline reliability

---

## 2. 운영 경계 원칙

본 프로젝트는 현재 운영 영역과 보관된 실행 실험 영역을 명시적으로 분리하여 운영한다.

### 2.1 Data Platform / Observability Surface (메인)

**목적**: 재현 가능한 market data platform과 read-only 관측 표면.

**범위**:
- ingestion (Medallion 공유: Bronze / Silver / Gold)
- `observability/regime/` — axis features, market position, horizon state
- `observability/similarity/` — 과거 시장 구조 유사도 비교
- `observability/explainability/` — LLM 설명 레이어 (해석만, 예측 금지)
- `apps/api/` — FastAPI
- `apps/web/` — React + Vite Dashboard
- `migrations/` — Alembic, Postgres + TimescaleDB schema

**우선순위** (충돌 시):
1. Data pipeline reliability
2. Reproducibility
3. Observability
4. Runtime stability
5. Explainability
6. Dashboard UX
7. AI summary layer

AI/LLM 기능은 항상 후순위다.

### 2.2 Legacy Execution Reference (**동결 + 운영 중단**)

**목적**: 과거 실행 실험 구현 보존. 코드는 동결, **서비스는 운영 중단 (2026-05-12~)**.

**범위**:
- `strategy_engine/{allocation, policy_selector, sell_advisor, universe}`
- `backtest/` (전 preset 포함)
- `paper/` (sim execution)
- `broker/` (KIS mock adapter)
- `dags/paper_trading_dag.py`, `dags/broker_mock_trading_dag.py`, `dags/strategy_engine_dag.py`
- Telegram bot orchestration (`scripts/telegram_*`)

**상태**:
- **운영 중단 (2026-05-12~)**: Telegram bot systemd disable, paper/broker/strategy DAG paused
- **신규 기능 추가 금지** (영구)
- 기존 테스트 회귀 0 유지
- 버그 수정만 허용 (단, 운영 중단 상태라 거의 발생 안 함)
- 외부에 "투자 시스템"으로 포지셔닝 하지 않음
- `state/orchestrator.db`, `data/strategy/`, `data/paper/`, `data/broker/` snapshot 자료는 **보존**

---

## 3. Boundary 규칙

### 3.1 코드 의존성 방향

```
[Observability Runtime]               [Legacy Execution]
        ↓                                    ↓
        └──────────→ [Infrastructure] ←──────┘
                     (Medallion + PIT)
```

- Observability Runtime은 Legacy Execution 코드를 **import 하지 않는다**.
- Legacy Execution은 Observability Runtime 코드를 **import 하지 않는다**.
- 두 영역 모두 Infrastructure (Bronze/Silver/Gold, Calendar) 위에서 동작한다.

### 3.2 신규 작업 라우팅 규칙

새 기능을 추가할 때 어느 영역에 속하는지 다음 기준으로 판정:

| 질문 | YES → 어느 영역? |
|---|---|
| 시장 상태를 관측/설명하기 위한 기능인가? | Observability |
| 매수/매도 결정에 사용되는가? | Personal (그러나 동결이므로 거의 추가 안 함) |
| 자금 흐름 / 포지션 관리 기능인가? | Personal (동결) |
| 과거 시장과의 유사도를 비교하는 기능인가? | Observability |
| LLM이 "예측"하는가? | **금지** (해석/설명만 허용) |
| Dashboard에 노출되는 시각화인가? | Observability |
| Airflow DAG 또는 ETL인가? | Infrastructure (공유) |

### 3.3 데이터 의존성

- 현재 운영 영역과 legacy execution 영역은 **Gold snapshot까지만 공유**한다.
- Legacy Execution의 strategy snapshot / paper ledger는 Observability Runtime이 읽지 않는다.
- Observability Runtime의 similarity index / dashboard cache는 Legacy Execution이 읽지 않는다.

---

## 4. 추출 대상 분류 (현재 코드 기준)

**원칙**: "전략" 영역 전체를 frozen으로 처리하지 않는다. **시장 관측 영역(Observability)과 매매 의사결정 영역(Frozen)을 세세하게 분리**한다.

| 현재 위치 | 분류 | 처리 | 비고 |
|---|---|---|---|
| `pipeline/ingest/`, `features/`, `calendar/` | Infrastructure | 위치 유지 (공유) | Medallion 공통 |
| `strategy_engine/axis_features/` | Observation | `observability/regime/axis/`로 이전 완료 | Phase 1 첫 타깃, 기존 위치는 shim 유지 |
| `strategy_engine/axis_horizon_state/{long,mid,short}_engine` | Observation | `observability/regime/horizon/`로 이전 완료 | Phase 1, 기존 위치는 shim 유지 |
| `strategy_engine/market_position/` | Observation | `observability/regime/position/`로 이전 완료 | Phase 1, 기존 위치는 shim 유지 |
| `strategy_engine/next_step/` | Observation | `observability/regime/transition/`로 이전 완료 | Phase 1 — 5/10/20/60/120D 전이 관측, 기존 위치는 shim 유지 |
| `strategy_engine/group_transition/` | Observation | `observability/regime/rotation/`로 이전 완료 | Phase 1 — Tactical group rotation 관측, 기존 위치는 shim 유지 |
| `strategy_engine/universe/` | Mixed | ETF 정의는 공유, picking은 frozen | 32 ETFs SOT는 Observability 입력, picking 로직만 frozen |
| `strategy_engine/{allocation, policy_selector, sell_advisor}` | Investment (Frozen) | 위치 유지 | legacy execution 자동매매 의사결정 |
| `backtest/` | Investment (Frozen) | 위치 유지 | historical replay 필요 시 view만 추가 |
| `paper/`, `broker/` | Investment (Frozen) | 위치 유지 | 손 안 댐 |
| `strategy_engine/report_context*`, `report_analyzer` | Mixed → Explainability | `observability/explainability/`로 사전 이전 완료 | P22에서 next_step boundary 해소를 위해 선행. Phase 3 전체 완료 아님, 기존 위치는 shim 유지 |

### 문서 분류 매트릭스 (`docs/architecture/*`)

| 문서 | 분류 | 비고 |
|---|---|---|
| `eod_observability_contract.md`, `gold_design_contract.md`, `calendar_design_contract.md`, `macro_pipeline_scope.md` | Infrastructure | 공유, 그대로 유효 |
| `market_structure_{long,mid,short,composer}_contract.md` | Observation 자료 | Phase 1+ 이전, observation 컨텍스트로 재해석 |
| `axis_horizon_dependency_contract.md` | Observation 자료 | Phase 1 첫 타깃 |
| `threshold_policy.md`, `next_step_signal_contract.md`, `group_transition_signal_contract.md` | Observation 자료 | Observability regime 자료 |
| `walk_forward_validation_contract.md` | Observation 자료 | similarity 검증 도구로 발전 검토 |
| `text_observability_contract.md` | Observation 자료 | observer-only 원칙 유지 |
| `universe_contract.md` | Mixed | ETF SOT는 공유, picking은 frozen |
| `allocation_engine_contract.md`, `paper_execution_ledger_contract.md`, `paper_trading_alert_contract.md`, `policy_config_contract.md` | Frozen | 자동매매·매매 리포팅 |
| `text_strategy_connection_contract.md` | Mixed | 매매 연결은 frozen, 일부 규칙은 Phase 3 dashboard report에 차용 |

---

## 5. 절대 하지 말아야 할 것

다음 방향으로 흘러가지 않는다:

- AI 투자 추천
- 매수/매도 신호 시스템
- 자동 전략 추천 (Observability 명목으로 변형 추천도 금지)
- LLM 중심 제품화
- 거대한 범용 플랫폼
- 과도한 에이전트 구조
- 초반부터 multi-agent
- 초반부터 Kubernetes 과설계
- 초반부터 microservice 분해
- "이것도 넣을까요?" / "저것도 추가할까요?" 식의 scope expansion

지금 가장 중요한 것:

> "작지만 실제로 운영 가능한 시스템"

---

## 6. 아키텍처 철학

### 6.1 초기 권장 스택

- Python
- FastAPI (`apps/api/`)
- PostgreSQL + TimescaleDB (Docker Compose)
- Parquet (Bronze/Silver/Gold raw layer)
- Airflow (기존 유지, legacy execution DAG는 paused)
- React + Vite (`apps/web/`)
- Docker Compose
- **Cloudflare Tunnel (Phase 2~)** — 로컬 머신을 외부에 노출, 도메인+HTTPS 무료
  - AWS/Hetzner는 Phase 4 이후 의제 (외부 사용자 / 가용성 요구 발생 시)

### 6.2 초반에 금지

- Kubernetes
- distributed infra
- event bus
- microservices
- 복잡한 multi-agent orchestration

---

## 7. 핵심 관측 기능

### 7.1 Fixed ETF Universe
- 정해진 ETF만 사용 (SPY, QQQ, IWM, TLT, IAU, XLK, XLF, XLV, XLE, XLU, ...)
- 초반에는 user-defined ETF 금지
- 현재 SOT: 32 ETFs (`pipeline/config/eod_observability.py`)

### 7.2 Point-in-Time Data Discipline
- release timing, feature availability, revision timing, vintage 고려
- 기준: "당시 시장에서 실제로 알 수 있었는가?"
- 현재 Gold layer가 이 원칙 구현 (`selected_release_date < trade_date`)

### 7.3 Market Structure Dashboard
- ETF heatmap
- Sector relative strength
- Volatility state
- Macro timeline
- Cross-asset movement
- Similarity replay

### 7.4 Historical Similarity
- 현재 상태와 과거 상태의 구조적 유사성 비교
- 예: defensive rotation / bond stress / gold strength / small cap weakness 등을 feature vector로 구성
- 과거 어떤 시기와 유사한지 관측
- **"예측" 금지**, "과거 유사성 설명"만 허용

### 7.5 Explainability Layer
- LLM은 "관측 결과 설명"에만 사용
- 예: "최근 Utilities relative strength 상승", "risk-off regime과 유사"
- 추천 / 예측 금지

---

## 8. 운영 우선순위

production-grade runtime ownership을 위한 운영 항목:
- ingestion reliability
- scheduling (Airflow)
- retries
- stale detection
- snapshot consistency
- structured logging
- monitoring (향후 Grafana 도입 검토)
- reproducibility
- deployment discipline (Docker Compose)

---

## 9. 참조 문서

- 시스템 개요: `docs/system_overview.md`
- 데이터 모델: `docs/data/data_model.md`
- 운영 재현성 계약: `docs/operation/reproducible_runtime_contract.md`
- DB 결정: Postgres + TimescaleDB
- 기존 Medallion 계약: `docs/architecture/gold_design_contract.md`, `eod_observability_contract.md`
- 기존 strategy 계약 (legacy reference): `docs/architecture/market_structure_*_contract.md`

---

## 10. 변경 이력

- 2026-05-12: 초안. 현재 운영 영역과 legacy execution 영역의 경계 결정.
- 2026-05-12: Legacy Execution **운영 중단** 결정 (코드는 보존, 서비스는 정지). Cloud roadmap: Phase 2 Cloudflare Tunnel 도입.
- 2026-05-12: §4 추출 대상 표 세분화 — strategy 영역 전체 frozen이 아니라 Observation(market_structure/axis/horizon/next_step/group_transition)과 Investment(allocation/policy/sell/picking)를 분리. next_step, group_transition 모듈 추가. 문서 분류 매트릭스 추가.
- 2026-05-13: P23으로 legacy execution 테스트를 `tests/archive/personal/`로 이동하고, default pytest surface에서 archive를 제외.

---

## 11. Test Surface 운영 정책

### 11.1 Active Surface

기본 pytest(`conda run -n pytest-pretrend pytest -q --tb=short`)는 현재 운영 표면만 검증한다.

- 포함:
  - `tests/observability/`
  - `tests/pipeline/`의 Infrastructure 및 active Mixed 잔여 테스트
  - `tests/dags/`의 active 잔여 테스트
  - `tests/test_*.py`
- 제외:
  - `tests/archive/`
  - Legacy execution frozen 테스트(`tests/archive/personal/`로 이동)

### 11.2 Archive Surface

`tests/archive/personal/`은 legacy execution frozen 자산의 회귀 검증 보관소다.

- 포함:
  - Backtest / Paper / Broker 테스트
  - Personal Strategy Engine 테스트
  - Personal DAG 테스트
  - Telegram bot / task store / policy engine 테스트
- 기본 pytest에서는 제외한다.
- 필요 시 명시적으로 실행한다:

```bash
conda run -n pytest-pretrend pytest tests/archive/personal/ -q --tb=short
```

### 11.3 실행 책임

- Observability / Infrastructure 작업: 현재 운영 표면 기본 pytest 실행.
- Legacy execution frozen 영역 변경: archive surface 수동 pytest를 함께 실행.
- Legacy execution은 신규 기능 추가 금지 상태이므로 archive 테스트는 삭제하지 않고 보존한다.
