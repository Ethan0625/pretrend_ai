# P30-5 — Agent Docs Publication Safety

## 0. 문서 메타

- Task ID: `P30-5`
- Title: `Agent Docs Publication Safety`
- Status: `DONE`
- Phase: `P30 — Reproducible Runtime & Data Bootstrap`
- Parent: `P30`
- Source(anchor): `.agent/task/P30-5_agent_docs_publication_safety.md`
- Last Updated: `2026-05-15`
- Owner: `Codex`

### 병렬 실행 메타

- `parallel_safe`: `conditional`
- `depends_on`: `[P30-1]`
- `blocks`: `[P30 parent DONE]`
- `executor`: `local`
- `file_scope`:
  - 수정: [`.gitignore`, `.agent/README.md`, `AGENTS.md`, `CLAUDE.md`, `docs/operation/reproducible_runtime_contract.md`]
  - 읽기전용: [`.agent/`, `docs/`, `.env.example`]
- `merge_strategy`: `manual`

---

## 1. 목표

- 현재 문제: `.agent`, `CLAUDE.md`, `AGENTS.md`는 운영 재현성에 중요하지만 현재 Git ignore 상태이며, 전체 공개는 secret/local path 노출 위험이 있다.
- 이번 task의 목표: 공개 가능한 agent 문서를 whitelist로 정하고 보안 검사를 통과한 문서만 Git에 포함한다.
- 기대 효과: 신규 clone에서도 작업 규칙을 공유하되, 민감 문서와 세션 로그는 노출하지 않는다.

---

## 2. 작업 범위

### 2.1 In-Scope

- `.agent` 공개 whitelist 정의.
- `.agent/README.md` 또는 publication guide 작성.
- `AGENTS.md`, `CLAUDE.md` 공개 가능성 검토.
- local path/secret keyword scan.
- `.gitignore` 조정.

### 2.2 Out-of-Scope

- `.agent` 전체 unignore.
- secret 값 수정/출력.
- 대용량 archive 공개.
- historical run log 공개.

### 2.3 수정 금지

- `.agent/settings.local.json` 공개.
- `.agent/RUN_LOG.md` 공개.
- `.env`, `.env.airflow` 공개.
- 실제 API key/token/password 값 노출.

---

## 3. 설계 불변식

- 공개는 whitelist 방식만 허용한다.
- `security` marker 문서는 개별 검토 후 공개 여부를 결정한다.
- archive/history 문서는 기본 비공개다.
- 공개 문서에는 로컬 절대경로와 secret 값이 없어야 한다.

---

## 4. 구현 요구사항

1. `.agent` 내 공개 후보와 제외 후보를 목록화한다.
2. 공개 후보를 secret/local path scan한다.
3. `.gitignore`를 whitelist 방식으로 조정한다.
4. `AGENTS.md`, `CLAUDE.md`를 공개 가능 형태로 보정한다.
5. 공개 제외 문서의 이유를 publication guide에 기록한다.

---

## 5. 검증 방법

```bash
git check-ignore -v .agent/STABLE_CONTEXT.md .agent/RUN_LOG.md .agent/settings.local.json
grep -RInE "(API_KEY|TOKEN|SECRET|PASSWORD|[\\/]home[\\/][^[:space:]]+|\\.env.airflow|\\.local)" .agent AGENTS.md CLAUDE.md
git status --short --ignored .agent AGENTS.md CLAUDE.md
```

검증 주의:

- grep 결과는 실제 값인지 키 이름/설명인지 구분해야 한다.
- secret 값은 최종 답변에 출력하지 않는다.

---

## 6. 완료 기준

- [x] 공개 whitelist가 정의되어 있다.
- [x] 제외 대상이 명시되어 있다.
- [x] 공개 후보에서 secret/local path 위험이 해소되어 있다.
- [x] `.gitignore`가 whitelist 방식으로 조정되어 있다.
- [x] Git status에서 의도한 agent 문서만 stage 가능하다.

## 7. 완료 기록

### 변경 요약

- `.agent` 전체 공개 대신 whitelist 방식으로 `.gitignore`를 조정했다.
- `AGENTS.md`, `CLAUDE.md`를 public publication 대상으로 보정하고 metadata를 추가했다.
- `.agent/README.md`를 추가해 공개 whitelist, 제외 대상, 제외 이유, marker-publication 연결, safety check를 정의했다.
- `.agent/TASK_QUEUE.md`의 private local planning path를 public-safe 문구로 대체했다.
- `docs/operation/reproducible_runtime_contract.md`에 agent docs publication whitelist를 반영했다.

### 공개 whitelist

- `AGENTS.md`, `CLAUDE.md`
- `.agent/README.md`
- `.agent/STABLE_CONTEXT.md`
- `.agent/INVARIANTS.md`
- `.agent/WORKFLOW.md`
- `.agent/CHANGE_GATES.md`
- `.agent/TASK_QUEUE.md`
- `.agent/TASK_TEMPLATE.md`
- `.agent/PARENTS_TASK_TEMPLATE.md`
- `.agent/task/P30_parent_reproducible_runtime.md`
- `.agent/task/P30-0_*` through `.agent/task/P30-6_*`

### 제외 대상

- `.agent/settings.local.json`
- `.agent/RUN_LOG.md`
- `.agent/task/archive/`
- `.agent/*.code-workspace`
- `.agent/After_Phase2_Plan.md`
- `.agent/DIRECTION.md`
- `.agent/REFACTOR_2026Q2.md`
- `.agent/REPORT_TASK_QUEUE_AUDIT.md`
- `.agent/PROMPTS.md`
- `.agent/task/P30_draft_reproducible_runtime_data_bootstrap.md`

### 검증 결과

```bash
git status --short --ignored -uall .agent AGENTS.md CLAUDE.md
```

- PASS.
- Whitelist 대상은 stageable.
- `RUN_LOG`, `settings.local.json`, archive, workspace, draft/planning docs는 ignored.

```bash
git check-ignore -v .agent/STABLE_CONTEXT.md .agent/RUN_LOG.md .agent/settings.local.json .agent/task/archive/TASK_QUEUE_pre-2026Q2.md
```

- PASS.
- `STABLE_CONTEXT.md`는 negative whitelist pattern으로 stageable.
- `RUN_LOG.md`, `settings.local.json`, archive docs는 ignored.

```bash
grep -RIlE "[\\/]home[\\/][^[:space:]]+" <public-agent-candidates>
grep -RIlE "(AIza[0-9A-Za-z_-]{20,}|sk-[0-9A-Za-z_-]{20,}|xox[baprs]-[0-9A-Za-z-]{20,}|AAG[0-9A-Za-z_-]{20,})" <public-agent-candidates>
```

- PASS: no matches.

```bash
grep -RIlE "(API_KEY|TOKEN|SECRET|PASSWORD|[\\/]home[\\/][^[:space:]]+|\\.env.airflow)" <public-agent-candidates>
```

- Review-only matches remain for placeholder/policy terms in publication guide and task docs.
- No actual secret values or local absolute paths were found.
