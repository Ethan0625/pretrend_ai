v2026.05.12

# Workflow Standard

## 1) 작업 단위 원칙
- 한 작업은 한 목적(계약/기능/운영)으로 분리한다.
- PR/커밋은 목적별로 분리하고 작은 diff를 유지한다.
- 계약 의미 변경 가능성이 있으면 구현보다 계약 검토를 우선한다.
- 에이전트 규칙은 본 문서와 `CHANGE_GATES.md`를 단일 기준으로 유지한다.

Source:
- `docs/agent_adoption_notes.md (#4-운영-규칙-고정-agentsmd)`
- `docs/operation_guide.md (#agent-assisted-development-codex)`

## 2) 표준 실행 커맨드

### Strategy Engine
```bash
PYTHONPATH=src python -m pretrend.pipeline.strategy_engine.strategy_job --date 2024-06-03 --invested-ratio 0.10
PYTHONPATH=src python -m pretrend.pipeline.strategy_engine.strategy_job --date 2024-06-03 --invested-ratio 0.10 --long-z-threshold 0.3
```
Source: `docs/operation_guide.md (#strategy-engine-실행)`

### Backtest / Walk-forward
```bash
PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v2
PYTHONPATH=src python -m pretrend.pipeline.backtest.walk_forward --preset v2 --window-years 4 --step-years 2
```
Source:
- `docs/operation_guide.md (#backtest-engine-실행)`
- `docs/operation_guide.md (#walk-forward-실행)`

### 테스트
```bash
conda run -n pytest-pretrend pytest tests/ -v
conda run -n pytest-pretrend pytest tests/pipeline/backtest/ -v
conda run -n pytest-pretrend pytest tests/pipeline/text/ -v
```
Source:
- `docs/operation_guide.md (#통합-테스트-실행)`
- `docs/operation_guide.md (#backtest-테스트-실행)`
- `docs/operation_guide.md (#text-pipeline-실행)`

### Text Pipeline
```bash
PYTHONPATH=src python -m pretrend.pipeline.text.text_job --stage all --source sec,fed --date 2026-02-18
PYTHONPATH=src python -m pretrend.pipeline.text.backfill --source sec_index,fomc_archive --start 2006-01-01 --end 2024-06-03 --chunk-years 1
PYTHONPATH=src python -m pretrend.pipeline.text.gold_llm_backfill --source fed_fomc --start 2006-01-01 --end 2026-12-31 --max-workers 4
```
Source:
- `docs/operation_guide.md (#text-pipeline-실행)`

### Airflow 상태 확인
```bash
systemctl status airflow-scheduler --no-pager
systemctl status airflow-webserver --no-pager
```
Source: `docs/operation_guide.md (#airflow-서비스-관리-systemd)`

## 3) 세션 종료 업데이트 규칙
- 아래 조건 중 하나라도 만족하면 changelog 업데이트 검토:
  - 계약 의미/불변식 해석 변경
  - 사용자 관측 출력(Telegram/Report) 의미 변경
  - 운영 절차/명령/환경 요구사항 변경
- 운영 명령 변경 시 `operation_guide` 동기화 검토.

Source:
- `docs/changelog.md (#현재-유효-규칙-as-is)`
- `docs/operation_guide.md`

## 4) 테스트 상태 기록 규칙
- 테스트 상태는 고정 숫자를 문서에 상수처럼 박아두지 않는다.
- 항상 최신 pytest/CI 로그를 근거로 확인한다.
- 세션별 실행 결과는 `.agent/RUN_LOG.md`에 날짜 단위로 기록한다.

Source:
- `docs/agent_adoption_notes.md (#5-사람이-개입한-핵심-지점)`

## 5) 브랜치/리뷰 체크
- 기본 브랜치 전략: `dev` 기반 작업
- 리뷰 전 체크:
  - 범위 외 파일 수정 여부
  - 계약-코드 정합성
  - 롤백 가능성
  - **트랙 boundary 침범 여부**: Observability 코드가 `pretrend.strategy_engine/backtest/paper/broker` import 안 했는지, Personal Track 코드가 `pretrend.observability/config/models` import 안 했는지
  - **`personal-frozen` scope commit**: 동결 boundary 위반 의심 시 사장님 확인 우선

## 6) 커밋/PR 규칙

### 6.1 Conventional Commits 형식
- 형식: `type(scope): title`
- type: `feat|fix|refactor|test|docs|chore|perf|build|ci`
- 제목 50자 이내, 본문 72자 줄바꿈
- 한 커밋은 한 목적(기능/문서/운영)만 포함

### 6.2 Track scope 표준 (2026Q2~)

본 프로젝트는 Two-Track 운영 — 트랙을 commit scope에 반영해 히스토리만으로 어느 트랙 변경인지 즉시 파악 가능하게 한다.

**Top-level track scope**:

| scope | 트랙 | 사용 시점 | 빈도 |
|---|---|---|---|
| `observability` | Observability Track | 신규 작업 본진 (regime, similarity, explainability, apps/api, apps/web) | 가장 많음 |
| `infra` | Infrastructure (공유) | Bronze/Silver/Gold (`pipeline/ingest`, `features`, `calendar`), Macro/EOD DAG | 중간 |
| `personal-frozen` | Personal Track | **극히 드물게** — CI 호환성 같은 unavoidable fix만 | 거의 없음 |

**Module sub-scope** (선택, 트랙 scope 뒤에 슬래시로):
- `observability/regime`, `observability/similarity`, `observability/explainability`
- `infra/ingest`, `infra/calendar`, `infra/eod`
- 일반 보조 scope (`docs`, `chore`, `refactor`)는 트랙과 무관하게 기존 패턴 유지 가능

### 6.3 예시

```
feat(observability/regime): add axis_features extraction module
feat(infra): macro DAG retry on transient FRED errors
fix(personal-frozen): emergency CI fix for broker import path
docs(track-separation): clarify Cloudflare Tunnel Phase 2 scope
chore(deps): pin sqlalchemy 2.0.x
refactor(observability/regime): rename axis_*.py to clearer naming
build(docker): add timescaledb compose service
```

### 6.4 Personal Track commit 발생 시 강화 규칙

`personal-frozen` scope이 등장하는 commit은 다음을 만족해야 한다:
- 본문에 변경 이유 명시 (CI fix, security patch, unavoidable refactor 등)
- 신규 기능 추가 0 — 버그 수정 / 호환성 패치만
- 1줄 변경이라도 trivial로 처리하지 않고 commit message에 근거 기록
- 동결 boundary 위반 의심 시 작업 중단 후 사장님 확인 우선

### 6.5 PR 규칙
- 목적/범위/비범위 명시
- 검증 명령과 결과 명시(실행한 것만)
- 리스크/롤백 절차 명시
- 계약/스키마 의미 변경 시 관련 SOT 문서 링크 포함
- 트랙 scope과 PR title 정합 유지

## 7) 최근 반영 사항

### v2026.05.12 (2026Q2 방향 재정의)
- Two-Track 분리 결정: Observability Track (메인) + Personal Track (동결 + 운영 중단)
- Commit scope 표준 추가 (§6.2): `observability` / `infra` / `personal-frozen`
- 브랜치/리뷰 체크에 트랙 boundary 검증 추가 (§5)
- Cloud roadmap: Phase 2 Cloudflare Tunnel 도입, AWS는 Phase 4 이후 의제

### v2026.02.24 (legacy, Personal Track 자산)
- 전이예측 계약 계층 추가:
  - `next_step_signal_contract.md` (3-state + 다음 스텝 가설 + 4축 근거 + 12셀 진단)
  - `walk_forward_validation_contract.md` (Tier-1/Tier-2 + PASS 상태 전이)
- Telegram 포맷 확장:
  - `시장 컨텍스트` + `다음 스텝 가설(10D 중심 / 5·10·20·60·120D)` + `시장 근거(4축)` + `진단 요약`
- Walk-forward 출력 확장:
  - `validation_status`, `tier1_pass`, `tier2_warning`, `diag_*` 컬럼 기반 요약
- Text 운영 확장:
  - `text_pipeline_dag`: `Bronze -> Silver -> Gold(rule) -> Gold LLM`
  - `gold_llm_backfill.py`: FOMC/SEC 백필 CLI
  - `sec_edgar.py`: `filings.files` 페이지네이션 지원
  - Telegram은 `llm_feature`를 읽어 `interpretation_summary`를 생성할 수 있으나, 전략 입력은 observer-only로 고정

Source:
- `.agent/REFACTOR_2026Q2.md`
- `docs/architecture/track_separation.md`
- `docs/operation_guide.md (#agent-assisted-development-codex)`

## 8) Task 문서 운영 규칙

### 8.1 task 문서 계층
- `TASK_QUEUE.md`는 상태 관리 보드다.
- parent task 문서는 상위 workstream의 목표 / 상태 / 세부 task 분해 / 상위 DoD를 관리한다.
- leaf task 문서는 Codex 실행용 단일 작업 문서다.

예:
- parent task: `P3-5`
- leaf task: `P3-5a`, `P3-5b`, `P3-5c`

### 8.2 Parent / Leaf 구분 원칙
- parent task는 여러 leaf task를 묶는 상위 작업이다.
- leaf task는 Codex가 한 번에 실행 가능한 단일 작업이다.
- leaf task 문서 하나에는 하나의 작업만 넣는다.
- leaf task 안에 다시 `Task A/B/C` 같은 하위 task를 만들지 않는다.

### 8.3 task 문서 작성 기준
- parent task는 `.agent/PARENT_TASK_TEMPLATE.md`를 따른다.
- leaf task는 `.agent/TASK_TEMPLATE.md`를 따른다.
- 모든 task 문서는 `TASK_QUEUE.md`의 `Why now / DoD / Risk / Source(anchor)`와 정합하게 유지한다.
- leaf task는 반드시 다음을 포함한다.
  - In-Scope
  - Out-of-Scope
  - 수정 금지
  - 설계 불변식
  - 검증 명령
  - 체크 가능한 DoD

### 8.4 문서-큐 정합성
- `TASK_QUEUE.md`의 Active 항목은 현재 진행 또는 대기 중인 parent / leaf task를 반영한다.
- 개별 실행 내용은 `.agent/task/*.md` 문서에 기록한다.
- task 완료 시 queue와 task 문서의 상태를 함께 갱신한다.

### 8.5 archive 운영 규칙
- 완료된 task 문서는 삭제하지 않고 archive로 이동한다.
- active 문서는 `.agent/task/`에 둔다.
- 완료 문서는 `.agent/task/archive/`로 이동한다.

#### 8.5.1 leaf task archive
- 완료된 leaf task는 archive로 이동한다.
- archive 문서는 참고용 이력이며, 현재 실행 기준 문서가 아니다.

#### 8.5.2 parent task archive
- parent task는 하위 leaf task가 남아 있는 동안 active 위치에 유지한다.
- 하위 leaf task가 모두 완료되고 parent DoD가 충족되면 archive로 이동한다.

#### 8.5.3 workstream 단위 보관
- 가능하면 parent task와 하위 leaf task를 같은 archive 경로에 묶어 보관한다.

예:
- `.agent/task/archive/P3-5/`

### 8.6 완료 기록 기준
- 완료된 task는 결과 / Artifacts / Verification / Source(anchor)를 남긴다.
- 완료 후 `TASK_QUEUE.md`의 Completed 섹션과 task 문서의 완료 기록이 정합해야 한다.

### 8.7 읽기 원칙
- Claude는 active 문서를 기준으로 문제 정의와 task 분해를 수행한다.
- Codex는 active leaf task 문서를 직접 실행 기준으로 사용한다.
- archive 문서는 과거 이력과 재참조용으로만 사용한다.
