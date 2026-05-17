---
# `.agent/TASK_TEMPLATE.md`
---
# [TASK_ID] — [TASK_TITLE]

## 0. 문서 메타

- Task ID: `[예: P3-5c]`
- Title: `[세부 작업 제목]`
- Status: `TODO | IN PROGRESS | BLOCKED | DONE | CANCELLED`
- Phase: `[예: P3 — Text→Strategy 통합 + 실운영]`
- Parent: `[예: P3-5]`
- Source(anchor): `[예: .agent/task/P3-5c_xxx.md]`
- Last Updated: `YYYY-MM-DD`
- Owner: `Codex | Claude Code | Human`

### 병렬 실행 메타 (Codex 워커 배정 시 참조)

- `parallel_safe`: `yes | no | conditional`
  - `yes`: 다른 task와 동시에 실행 가능
  - `no`: 단독 실행 필요 (공유 파일 또는 DB 상태 의존)
  - `conditional`: depends_on 완료 후에만 병렬 허용
- `depends_on`: `[]` — 이 task 시작 전 DONE이어야 하는 Task ID 목록
- `blocks`: `[]` — 이 task 완료 전 시작 불가한 Task ID 목록
- `executor`: `local | worktree`
  - `local`: 메인 프로젝트 디렉토리에서 직접 실행 (기본값 — gitignore 파일 포함, bot/agent/script 작업)
  - `worktree`: git worktree 생성 후 실행 (git 추적 파일만 복사 — 브랜치 분리가 필요한 경우에만)
- `file_scope`:
  - 수정: `[]` — 이 task가 변경하는 파일/디렉토리
  - 읽기전용: `[]` — 읽기만 하는 파일 (충돌 없음)
- `merge_strategy`: `auto | review | manual`
  - `auto`: 테스트 통과 시 Claude 팀장이 자동 머지 승인
  - `review`: Claude 팀장 리뷰 후 사장 확인 없이 머지
  - `manual`: 사장 결재 후 머지 (프로덕션 영향 있는 변경)

---

## 1. 목표

이 leaf task 하나가 왜 필요한지, 이번 작업으로 무엇을 수정/고정/보완하는지 2~4문장으로 작성한다.

- 현재 문제:
- 이번 task의 목표:
- 기대 효과:

---

## 2. Why now

`TASK_QUEUE.md`와 parent task 문서에 연결되도록 작성한다.

- 왜 지금 필요한가:
- 선행 조건:
- 미루면 생기는 문제:

---

## 3. 배경

이번 leaf task를 이해하는 데 필요한 최소 배경만 적는다.

- 관련 parent task:
- 관련 설계/계약 문서:
- 현재 구현 상태:
- 관련 완료 이력:

---

## 4. 현재 상태

이번 task가 들어가기 전 상태를 구현자 관점에서 적는다.

- 현재 동작:
- 이미 완료된 범위:
- 이번 task 이전에 남아 있는 문제:
- 확인된 이슈:

---

## 5. 문제의 본질

이 leaf task가 해결해야 하는 단일 구조 문제를 적는다.

- 현재는:
- 하지만:
- 이번 task의 핵심은:

---

## 6. 작업 범위

### 6.1 In-Scope
이번 task에서 수정 가능한 파일/디렉토리/문서만 적는다.

- `src/...`
- `tests/...`
- `docs/...`
- `dags/...`

### 6.2 Out-of-Scope
이번 task에서 다루지 않을 범위를 적는다.

- 
- 
- 

### 6.3 수정 금지
이번 task에서 변경하면 안 되는 계약/스키마/API/운영 규칙을 적는다.

- 
- 
- 

---

## 7. 설계 불변식

이번 task 수행 중 반드시 유지해야 하는 규칙을 적는다.

- PIT 정합성 유지
- idempotent write 유지
- snapshot reproducibility 유지
- 기존 contract key/grain 유지
- public API 임의 변경 금지
- 기존 경로 회귀 금지

프로젝트 특화 invariant가 있으면 추가한다.

---

## 8. 구현 요구사항

이 문서는 하나의 leaf task만 다룬다.  
따라서 `Task A/B/C`처럼 다시 하위 task를 만들지 않고, 이번 task의 구현 요구사항만 번호 목록으로 적는다.

1. 
2. 
3. 
4. 

---

## 9. 비목표 (Non-Goals)

이번 task에서 일부러 하지 않는 것을 적는다.  
프로젝트 문서들도 Scope와 Non-goals를 분리해 고정하고 있으므로 같은 원칙을 따른다. :contentReference[oaicite:4]{index=4} :contentReference[oaicite:5]{index=5}

- 이번 task는 `[...]`를 하지 않는다.
- `[...]`는 후속 task에서 다룬다.
- 범위 확장 구현 금지:
  - “관련 코드 전체 정리”
  - “가능한 범위에서 추가 개선”
  - “적절히 리팩토링”
  같은 표현으로 임의 확장하지 않는다.

---

## 10. 세부 완료 기준 (Task DoD)

이번 leaf task가 DONE으로 이동하기 위한 체크 가능한 조건을 적는다.

- [ ] 구현 요구사항이 반영되었다.
- [ ] 수정 금지 범위를 침범하지 않았다.
- [ ] 설계 불변식이 유지된다.
- [ ] 관련 테스트/검증이 통과한다.
- [ ] 필요한 문서 반영이 완료되었다.
- [ ] parent task와 queue 상태 갱신 기준을 충족한다.

---

## 11. 예상 산출물

### Code
- 수정 파일:
- 신규 파일:

### Tests
- 추가 테스트:
- 수정 테스트:

### Docs
- 수정 문서:
- changelog 반영 여부:

### Queue / Task 관리
- `TASK_QUEUE.md` 반영 필요 여부:
- parent task 상태 갱신 필요 여부:

---

## 12. 검증 방법

### 12.1 Test Commands
실행해야 하는 명령을 구체적으로 적는다.  
기존 task 문서도 검증 명령을 명시하는 형태이므로 이를 유지한다. :contentReference[oaicite:6]{index=6}

```bash
conda run -n pytest-pretrend pytest tests/... -v
````

필요 시 회귀 또는 수동 검증 명령도 추가한다.

```bash
conda run -n pytest-pretrend pytest tests/ -q --tb=short
```

### 12.2 Validation Points

* 로그/경고/오류가 의도대로 출력되는가
* contract 컬럼/키가 유지되는가
* 기존 경로 회귀가 없는가
* 모드/source 식별 필드가 올바른가

### 12.3 Verification Notes

* 외부 API 호출 여부:
* dry-run 필요 여부:
* mock fixture 사용 여부:
* 수동 검증 필요 여부:

---

## 13. 리스크

* 주요 리스크:
* 영향:
* 완화책:
* Blocker 여부:
* External API / Secret / Rate-limit / ToS 메모:

---

## 14. 참조 문서

* `.agent/TASK_QUEUE.md`
* `.agent/task/[PARENT_TASK_FILE].md`
* `docs/changelog.md`
* `docs/roadmap/milestones.md`
* `docs/architecture/strategy_engine_design.md`
* `docs/architecture/...`
* `docs/operation_guide.md`

---

## 15. 작업 시 유의사항

* 이 문서는 leaf task 실행용이다.
* 하나의 문서에는 하나의 task만 넣는다.
* `P3-5c` 문서 안에 다시 `Task A/B/C`를 만들지 않는다.
* 이름 변경만으로 끝내지 말고 구조 문제 해결 여부를 확인한다.
* 새로운 사실/규칙을 임의로 추가하지 않는다.
* 테스트 미지정 시 임의 대규모 실행 금지.

---

## 16. 완료 후 기록 형식

`TASK_QUEUE.md`의 Completed 형식과 맞추어 기록한다. Completed는 `결과 / Artifacts / Verification / Source(anchor)`를 남긴다.  

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

---
