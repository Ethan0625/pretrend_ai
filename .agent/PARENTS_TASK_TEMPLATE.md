---
# `.agent/PARENT_TASK_TEMPLATE.md`
---
# [PARENT_TASK_ID] — [PARENT_TASK_TITLE]

## 0. 문서 메타

- Parent Task ID: `[예: P3-5]`
- Title: `[상위 작업 제목]`
- Status: `TODO | IN PROGRESS | BLOCKED | DONE | CANCELLED`
- Phase: `[예: P3 — Text→Strategy 통합 + 실운영]`
- Source(anchor): `[예: .agent/task/P3-5_PAPER_TRADING_KIS_MOCK_REVIEW_PLAN.md]`
- Last Updated: `YYYY-MM-DD`
- Owner: `Human | Claude Code`

---

## 1. 목표

이 상위 작업이 왜 필요한지, 이번 workstream 전체에서 무엇을 달성하려는지 2~4문장으로 작성한다.

- 현재 문제:
- 상위 목표:
- 기대 효과:

---

## 2. Why now

`TASK_QUEUE.md`의 Active Queue와 연결되는 형태로 작성한다.

- 왜 지금 필요한가:
- 선행 조건:
- 미루면 생기는 문제:

---

## 3. 배경

현재까지의 구현/운영/문서 상태를 사실 기준으로 정리한다.

- 관련 설계 문서:
- 관련 계약 문서:
- 운영 맥락:
- 이전 완료 이력:
- 관련 Gate / Risk:

---

## 4. 현재 상태

이 상위 작업 기준으로 이미 끝난 범위와 남은 범위를 나눠 적는다.

### 4.1 완료된 범위
- 
- 
- 

### 4.2 현재 남은 핵심 범위
- 
- 
- 

### 4.3 확인된 이슈 / Blocker
- 
- 
- 

---

## 5. 문제의 본질

겉으로 보이는 현상이 아니라, 이 상위 작업이 해결하려는 구조적 문제를 서술한다.

- 현재는:
- 하지만:
- 이 상위 작업의 핵심은:

---

## 6. 상위 범위 정의

### 6.1 In-Scope
이 parent task 전체에서 다루는 범위를 적는다.

- 
- 
- 

### 6.2 Out-of-Scope
이 parent task 전체에서 다루지 않을 범위를 적는다.

- 
- 
- 

### 6.3 수정 금지
상위 차원에서 건드리면 안 되는 범위를 적는다.

- 
- 
- 

---

## 7. 설계 불변식

parent task 전반에서 유지해야 하는 invariant를 적는다.

- PIT 정합성 유지
- idempotent write 유지
- snapshot reproducibility 유지
- fail-open / fail-fast 경계 유지
- public contract 임의 변경 금지
- JSON logging 유지

프로젝트 특화 invariant가 있으면 추가한다.

---

## 8. 세부 task 분해

이 상위 작업을 leaf task 단위로 분해한다.
각 항목은 `TASK_QUEUE.md`와 `.agent/task/` 개별 문서로 연결될 수 있어야 한다.

| Task ID | 제목 | 상태 | 목적 | parallel_safe | executor | Source(anchor) |
| --- | --- | --- | --- | --- | --- | --- |
| `[예: P3-5a]` | `[세부 작업 제목]` | `TODO/DONE` | `[한 줄 목적]` | `yes/no` | `local/worktree` | `[.agent/task/...md]` |
| `[예: P3-5b]` | `[세부 작업 제목]` | `TODO/DONE` | `[한 줄 목적]` | `yes/no` | `local/worktree` | `[.agent/task/...md]` |
| `[예: P3-5c]` | `[세부 작업 제목]` | `TODO/DONE` | `[한 줄 목적]` | `yes/no` | `local/worktree` | `[.agent/task/...md]` |

### 8.1 실행 순서 / 병렬 그룹

Codex 워커 배정 시 Claude 팀장이 참조하는 실행 순서도. 같은 그룹은 동시에 배정 가능.

```
[그룹 1 — 병렬 실행 가능]
  P3-5a  (file_scope: src/a.py, executor: local)
  P3-5b  (file_scope: src/b.py, executor: local)

[그룹 2 — P3-5a 완료 후 실행]
  P3-5c  (depends_on: P3-5a, executor: local)

[그룹 3 — 단독 실행 (parallel_safe: no)]
  P3-5d  (file_scope: 공유 config, DB schema, executor: worktree)
```

> executor 기본값: `local` — gitignore 파일(bot, agent, scripts 등) 포함 작업에 필수.
> `worktree`는 git 추적 파일만 복사되므로, gitignore 대상 파일을 수정하는 task에 사용 금지.

### 8.2 충돌 위험 파일

여러 task가 동시에 건드리면 안 되는 공유 파일/디렉토리를 명시한다.

- `[예: src/pretrend/pipeline/config.py]` — P3-5a, P3-5c 동시 수정 금지
- `[예: data/strategy/]` — 런타임 출력 디렉토리, 순차 실행 필요

---

## 9. 세부 task별 요약

### [TASK_ID]
- 목적:
- 핵심 변경:
- 완료 기준 요약:
- 리스크:
- 비고:

### [TASK_ID]
- 목적:
- 핵심 변경:
- 완료 기준 요약:
- 리스크:
- 비고:

---

## 10. 상위 완료 기준 (Parent DoD)

이 상위 작업이 DONE으로 이동하기 위한 최종 조건을 적는다.  
`TASK_QUEUE.md`의 DoD와 정합해야 한다. :contentReference[oaicite:3]{index=3}

- [ ] 상위 범위에 포함된 leaf task가 모두 완료되었다.
- [ ] 수정 금지 범위를 침범하지 않았다.
- [ ] 설계 불변식이 유지된다.
- [ ] 필요한 코드/테스트/문서가 모두 동기화되었다.
- [ ] 운영 검증 또는 수동 검증 조건이 충족되었다.
- [ ] `TASK_QUEUE.md` 상태와 source(anchor)가 동기화되었다.

---

## 11. 리스크

`TASK_QUEUE.md`의 Risk와 연결되는 수준으로 적는다.

- 주요 리스크:
- 영향:
- 완화책:
- Blocker 여부:
- External API / Secret / Rate-limit / ToS 메모:

---

## 12. 검증 전략

상위 작업 관점의 검증 전략을 적는다.

### 12.1 단위/회귀 테스트
```bash
conda run -n pytest-pretrend pytest tests/... -q --tb=short
````

### 12.2 수동 검증 / 운영 검증

```bash
# 필요한 경우 실행 명령
```

### 12.3 확인 포인트

*
*
*

---

## 13. 예상 산출물

### Code

* 수정 파일:
* 신규 파일:

### Tests

* 추가 테스트:
* 수정 테스트:

### Docs

* 수정 문서:
* changelog 반영 여부:

### Queue / Task 관리

* `TASK_QUEUE.md` 반영:
* Completed 이동 조건:

---

## 14. 참조 문서

* `.agent/TASK_QUEUE.md`
* `.agent/task/...`
* `docs/changelog.md`
* `docs/roadmap/milestones.md`
* `docs/architecture/strategy_engine_design.md`
* `docs/architecture/...`
* `docs/operation_guide.md`

---

## 15. 작업 시 유의사항

* 이 문서는 leaf task 실행 지시문이 아니라 상위 계획 문서다.
* 개별 구현 지시는 `P3-5a`, `P3-5b` 같은 leaf task 문서로 분리한다.
* parent 문서 안에 구현 세부 diff를 과도하게 넣지 않는다.
* 새로운 사실/정책을 임의로 추가하지 않는다.
* queue 상태와 source(anchor)를 함께 관리한다.

---

## 16. 완료 후 기록 형식

### 결과

*

### Artifacts

*

### Verification

*
* 결과:

### Source(anchor)

* `.agent/task/[THIS_FILE_NAME].md`

````
