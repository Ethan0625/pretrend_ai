# Agent Adoption Notes — Codex 도입 평가 및 운영 기준

> 🟢 **공통 가이드 (두 트랙 공유) — Workflow / Agent 운영 규칙**
>
> 본 문서는 Codex(Agent) 도입 평가 결과를 정리한 운영 가이드이며, 두 트랙 모두에 적용됩니다.
> 현재 운영 규칙 SOT: [`.agent/WORKFLOW.md`](../.agent/WORKFLOW.md), [`.agent/DIRECTION.md`](../.agent/DIRECTION.md), [`architecture/track_separation.md`](architecture/track_separation.md)
> 본 문서는 평가 시점 기록으로 보존되며, 최신 규칙은 `.agent/WORKFLOW.md`를 우선 참조합니다.

## 1. 목적

본 문서는 Pretrend 프로젝트에서 AI Agent(OpenAI Codex)를 **실험적으로 도입하고, 실제 운영에 적용 가능한 범위와 한계를 평가한 결과**를 정리한다.

목표는 다음과 같다.

* AI Agent를 무분별하게 사용하는 것이 아니라, **사람의 판단이 필요한 지점과 자동화 가능한 지점을 구분**한다.
* 테스트·문서와 같이 **실패 비용이 낮은 영역부터 단계적으로 도입**한다.
* 향후 자동매매 실행 레이어(OpenClaw 등) 도입 여부를 판단하기 위한 기준을 남긴다.

---

## 2. 도입 배경

Pretrend는 데이터 파이프라인(Bronze → Silver → Gold)과 Universe 계산을 기반으로 한 자동매매 시스템으로, 다음과 같은 특성을 가진다.

* 멱등성(idempotency), 파티션 overwrite, as-of join 등 **데이터 정합성이 핵심**
* 잘못된 자동화는 금전적 손실로 직결될 수 있음
* 테스트 및 문서 품질이 장기 운영 안정성에 큰 영향을 미침

이러한 특성상, AI Agent를 **설계·판단 주체가 아닌 보조 도구**로 한정하여 도입하는 것이 필요했다.

---

## 3. 초기 접근 방식

### 3.1 Task Spec 기반 Agent 사용

* Codex에게는 항상 **명시적인 Task Spec**을 제공
* Task Spec에는 다음을 반드시 포함

  * Scope 제한 (tests-only, docs-only 등)
  * 금지 사항 (API 변경, 시크릿 사용 금지)
  * Definition of Done (pytest 통과, 변경 파일 목록 등)

> 초기 Task Spec은 외부 도움(ChatGPT)을 통해 생성되었으나,
> 실제 도입 과정에서는 해당 Spec을 그대로 수용하지 않고 검토·수정하며
> 프로젝트 규칙(AGENTS.md)에 맞게 운영 기준을 확정했다.

이 과정에서 **Agent는 초안 생성기**, 사람은 **검토자·의사결정자**라는 역할 분리가 명확해졌다.

### 3.2 Task Spec 예시 (실제 사용 사례)

아래는 본 프로젝트에서 Codex에게 전달한 실제 Task Spec 유형의 예시이다.

```md
## Task
- Goal: Add 2 pytest cases to validate Silver writer idempotent overwrite behavior for EOD outputs.
- Scope: tests/ directory only (do NOT modify src/).
- Constraints:
  - Follow existing patterns under tests/pipeline.
  - Keep the diff small (one task, prefer <= 300 LOC).
  - Do not assume commands were executed; only suggest verification commands.

## Required Tests
1) Overwrite-on-second-write (no duplication)
   - Same partition, distinguishable values to detect overwrite
2) Output artifact invariant
   - Repeated writes must not increase partition artifacts

## Output format
- List changed files
- Brief rationale for each test
- Exact verification commands (pytest -q)
```

이와 같이 Task Spec을 **사람이 통제 가능한 수준으로 구체화**함으로써,
Agent가 생성하는 산출물의 범위와 리스크를 사전에 제한했다.

---

## 4. 운영 규칙 고정 (AGENTS.md)

Agent 도입 과정에서 가장 중요했던 요소는 **프로젝트 규칙의 고정**이었다.

AGENTS.md에 고정한 핵심 원칙:

* 작은 diff 유지 (1 task / ≤300 LOC 권장)
* public API 변경 금지
* 시크릿 하드코딩 금지
* 파이프라인 멱등성 및 파티션 overwrite 규칙 보존
* 변경 시 반드시 테스트 및 문서 동반

이 파일은 Codex뿐 아니라 **사람에게도 동일하게 적용되는 프로젝트 헌법**으로 사용한다.

---

## 5. 사람이 개입한 핵심 지점

Agent가 생성한 테스트/문서는 그대로 채택하지 않았다. 주요 개입 지점은 다음과 같다.

### 5.1 테스트 품질 검증

* 파일 단위 검증 → **파티션 단위 invariant 검증**으로 재설계
* 파일명/구현에 결합된 assert 제거
* "중복 없음", "overwrite 보장" 등 **의미적 불변조건(invariant)** 중심으로 수정

### 5.2 불필요한 구조 제거

* parquet 파일 반복 로딩 반복문 제거
* 전체 파티션 데이터를 기준으로 검증하도록 단순화

이 과정을 통해 Agent 산출물을 **운영 환경 변화에 덜 취약한 테스트**로 개선했다.

---

## 6. 현재 적용 범위 (2026-02 기준)

### 적용 중

* 테스트 코드 생성 및 회귀 테스트 보강
* 문서 동기화 (README, operation_guide)
* 반복적인 검증 작업

### 의도적으로 제외

* Universe 계산 로직 판단
* 전략/시그널 설계
* 자동매매 실행 판단

Agent는 "결정을 내리는 주체"가 아니라, **결정을 검증·보조하는 도구**로만 사용한다.

---

## 7. 효과 및 한계

### 효과

* 테스트 작성 속도 개선
* 반복 작업에서 인지 부하 감소
* 규칙 기반 운영으로 안정성 확보

### 한계

* Task Spec 품질이 낮으면 산출물 품질도 급격히 저하
* 규칙 없이 사용 시 오히려 리뷰 비용 증가

---

## 8. 향후 확장 기준

OpenClaw 등 실행 오케스트레이션 프레임워크 도입은 다음 조건 충족 후 검토한다.

* Signal contract 고정
* Risk rule 문서화 및 테스트 완료
* Paper trading 안정 운영
* Kill switch 설계 완료

그 전까지 Agent는 **개발 보조 도구**로만 사용한다.

---

## 9. 정리

* AI Agent로 전체 개발과정을 대체하지 않는다.
* 품질은 여전히 **사람의 판단 지점**에서 결정된다.
* Agent 도입의 성공 여부는 모델 성능보다 **운영 규칙과 통제 구조**에 달려 있다.

이 문서는 향후 Pretrend 프로젝트뿐 아니라, 다른 AI Agent 도입 시에도 기준 문서로 활용한다.
