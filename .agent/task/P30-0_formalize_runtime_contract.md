# P30-0 — Formalize Runtime Contract

## 0. 문서 메타

- Task ID: `P30-0`
- Title: `Formalize Runtime Contract`
- Status: `DONE`
- Phase: `P30 — Reproducible Runtime & Data Bootstrap`
- Parent: `P30`
- Source(anchor): `.agent/task/P30-0_formalize_runtime_contract.md`
- Last Updated: `2026-05-15`
- Owner: `Codex`

### 병렬 실행 메타

- `parallel_safe`: `no`
- `depends_on`: `[]`
- `blocks`: `[P30-1, P30-2, P30-3, P30-4, P30-5, P30-6]`
- `executor`: `local`
- `file_scope`:
  - 수정: [`docs/operation/reproducible_runtime_contract.md`, `docs/system_overview.md`, `docs/operation_guide.md`, `docs/environment.md`, `.agent/TASK_QUEUE.md`, `.agent/task/P30_parent_reproducible_runtime.md`, `.agent/task/P30-*.md`]
  - 읽기전용: [`docker-compose.yml`, `.env.example`, `.dockerignore`, `Dockerfile.api`, `docs/testing/operational_invariant_test_contract.md`]
- `merge_strategy`: `review`

---

## 1. 목표

- 현재 문제: P30의 구현 범위가 Docker, DB volume, backup/restore, dev/test image, agent docs publication, docs marker로 넓어서 바로 구현하면 범위가 섞인다.
- 이번 task의 목표: P30 parent/leaf 구조와 장기 runtime contract 문서를 먼저 고정한다.
- 기대 효과: 이후 P30-1~P30-6이 leaf task 기준으로 실행될 수 있다.

---

## 2. Why now

- 왜 지금 필요한가: P29 완료분 commit/push 후 Phase 3로 바로 가지 않고, 정전/OS 이동/신규 clone 대응을 위한 runtime 재현성 기준이 필요하다.
- 선행 조건: P29 완료분 push 완료.
- 미루면 생기는 문제: P30 구현 중 compose, Dockerfile, docs publication, restore 검증 범위가 섞인다.

---

## 3. 작업 범위

### 3.1 In-Scope

- `docs/operation/reproducible_runtime_contract.md` 신설.
- `P30` parent task 문서 신설.
- `P30-1`~`P30-6` leaf task 문서 신설.
- `TASK_QUEUE.md` active queue에 P30 등록.
- `system_overview`, `operation_guide`, `environment`에서 P30 runtime contract 링크.
- 기존 draft는 formal task로 대체되었음을 표시.

### 3.2 Out-of-Scope

- `docker-compose.yml` 수정.
- `.env.example` 수정.
- Dockerfile 추가/수정.
- DB restore 실행.
- pytest 실행.
- `.agent` 공개 whitelist 실제 적용.

### 3.3 수정 금지

- 기존 DB volume 삭제.
- `docker compose down -v`.
- `.env`, `.env.airflow` 내용 출력 또는 commit.
- 구현 파일 수정.

---

## 4. 설계 불변식

- Parent task는 실행 문서가 아니라 상위 범위/leaf 관리 문서다.
- Leaf task만 실제 실행 기준으로 삼는다.
- P30-0은 문서화 leaf이며, P30-1 이후 구현 leaf를 막는다.
- P30 draft는 참고용이며 실행 기준이 아니다.

---

## 5. 구현 요구사항

1. P30 parent 문서를 생성한다.
2. P30-0~P30-6 leaf 문서를 생성한다.
3. 장기 runtime contract 문서를 생성한다.
4. 기존 docs entry point에서 runtime contract를 찾을 수 있게 한다.
5. `TASK_QUEUE.md`에 P30 active entry를 추가한다.
6. draft 문서는 `SUPERSEDED_BY_FORMAL_TASKS`로 표시한다.

---

## 6. 검증 방법

```bash
find .agent/task -maxdepth 1 -type f -name 'P30*' -printf '%f\n' | sort
grep -RIn "docs/operation/reproducible_runtime_contract.md" docs .agent/task .agent/TASK_QUEUE.md
git diff --stat
```

---

## 7. 완료 기준

- [x] P30 parent와 P30-0~P30-6 leaf가 존재한다.
- [x] P30-0이 문서화 leaf로 구분되어 있다.
- [x] P30 parent가 P30-0을 leaf order에 포함한다.
- [x] P30-1은 첫 구현 leaf로 남아 있다.
- [x] runtime contract 문서가 docs entry point에서 연결된다.

---

## 8. 검증 결과

검증일: 2026-05-15

실행한 확인:

```bash
find .agent/task -maxdepth 1 -type f -name 'P30*' -printf '%f\n' | sort
grep -RIn "docs/operation/reproducible_runtime_contract.md" docs .agent/task .agent/TASK_QUEUE.md
grep -RIn "P30-0" .agent/task/P30_parent_reproducible_runtime.md .agent/TASK_QUEUE.md .agent/task/P30-0_formalize_runtime_contract.md
git status --short
git check-ignore -v .agent/task/P30-0_formalize_runtime_contract.md .agent/task/P30_parent_reproducible_runtime.md .agent/TASK_QUEUE.md
```

결과:

- P30 parent와 P30-0~P30-6 leaf 문서 존재 확인.
- `docs/operation/reproducible_runtime_contract.md`가 `system_overview`, `operation_guide`, `environment`, parent/leaf 문서에서 참조됨.
- P30 parent와 `TASK_QUEUE.md` leaf order에 P30-0 포함 확인.
- tracked docs 변경은 `docs/environment.md`, `docs/operation_guide.md`, `docs/system_overview.md`, 신규 `docs/operation/`로 확인.
- `.agent` 문서는 현재 `.gitignore`의 `.agent` 규칙으로 ignored 상태이며, P30-5 전까지 Git 공개 대상이 아니다.
