# P30-6 — Docs Marker Classification

## 0. 문서 메타

- Task ID: `P30-6`
- Title: `Docs Marker Classification`
- Status: `DONE`
- Phase: `P30 — Reproducible Runtime & Data Bootstrap`
- Parent: `P30`
- Source(anchor): `.agent/task/P30-6_docs_marker_classification.md`
- Last Updated: `2026-05-15`
- Owner: `Codex`

### 병렬 실행 메타

- `parallel_safe`: `conditional`
- `depends_on`: `[P30-5]`
- `blocks`: `[P30 parent DONE]`
- `executor`: `local`
- `file_scope`:
  - 수정: [`docs/`, `.agent/README.md`, `docs/operation/reproducible_runtime_contract.md`]
  - 읽기전용: [`pyproject.toml`, `tests/`, `.agent/TASK_QUEUE.md`]
- `merge_strategy`: `review`

---

## 1. 목표

- 현재 문제: pytest는 marker로 테스트의 의미를 분류하지만 docs는 읽기 순서, 공개 범위, 계약/운영/legacy 성격이 명확히 표시되지 않는다.
- 이번 task의 목표: docs marker 기준을 정의하고 주요 문서에 적용한다.
- 기대 효과: 신규 agent/개발자가 어떤 문서를 먼저 읽고, 어떤 문서를 공개 가능한지 marker 기준으로 판단할 수 있다.

---

## 2. 작업 범위

### 2.1 In-Scope

- docs marker vocabulary 정의.
- marker 표기 방식 결정.
- 주요 active docs에 marker 적용.
- legacy/reference-only 문서 표시.
- P30-5 publication whitelist와 marker 기준 연결.

### 2.2 Out-of-Scope

- 모든 historical archive 문서 전수 보정.
- 문서 내용 대규모 재작성.
- pytest marker 변경.
- public API contract 변경.

### 2.3 수정 금지

- 문서 marker를 근거로 contract 의미 변경.
- legacy 문서를 active SOT처럼 승격.
- secret/local path를 공개 대상 문서에 남기기.

---

## 3. 설계 불변식

- docs marker는 pytest marker와 1:1일 필요가 없다.
- `contract`, `testing`, `operation`, `legacy`는 pytest/운영 경계와 이름을 맞춘다.
- `agent`, `security`, `architecture`, `roadmap`은 docs 전용 marker로 허용한다.
- marker는 공개 범위와 읽기 순서 판단에 사용된다.

---

## 4. 구현 요구사항

1. marker vocabulary를 문서화한다.
2. front matter 또는 상단 metadata line 중 하나를 선택한다.
3. `docs/system_overview.md`, `docs/operation_guide.md`, `docs/environment.md`, `docs/testing/operational_invariant_test_contract.md`, `docs/architecture/*` 주요 문서에 marker를 적용한다.
4. `docs/legacy/`는 `legacy` / reference-only임을 명시한다.
5. P30-5 publication guide와 marker 기준을 동기화한다.

---

## 5. 검증 방법

```bash
grep -RIn "^Markers:" docs .agent/README.md
grep -RIn "Status: active\\|Status: legacy\\|Status: reference" docs .agent/README.md
```

필요 시 marker inventory 문서를 추가한다.

---

## 6. 완료 기준

- [x] docs marker vocabulary가 정의되어 있다.
- [x] marker 표기 방식이 하나로 정해져 있다.
- [x] 주요 active docs에 marker가 붙어 있다.
- [x] legacy/reference-only 문서가 구분되어 있다.
- [x] P30-5 공개 whitelist가 marker 기준과 연결되어 있다.

## 7. 완료 기록

### 변경 요약

- `docs/README.md`를 추가해 docs marker vocabulary와 status 값을 정의했다.
- 표기 방식은 문서 상단 metadata line으로 통일했다.
  - `Markers: ...`
  - `Status: active|reference|legacy|draft`
- 주요 active docs와 `docs/architecture/*.md`에 marker/status를 추가했다.
- Personal Track frozen architecture docs와 `docs/legacy/` 문서를 `legacy`로 구분했다.
- `threshold_policy.md`, `universe_contract.md`는 active SOT가 아닌 `reference`로 표시했다.
- `.agent/README.md`와 `docs/operation/reproducible_runtime_contract.md`에서 marker-publication 기준을 연결했다.

### 검증 결과

```bash
grep -RIn "^Markers:" docs .agent/README.md
grep -RIn "Status: active\\|Status: legacy\\|Status: reference" docs .agent/README.md
```

- PASS.
- Marker metadata count: 39.
- Status metadata count: 39.
- `docs/architecture/*.md` marker/status 누락 0.

```bash
pytest tests/ops/ -q --tb=short
git diff --check
```

- PASS: `5 passed`.
- PASS: whitespace check clean.
