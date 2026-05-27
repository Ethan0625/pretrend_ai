Markers: operation
Status: draft

# P-001 Example — Dashboard Metric Drift

> **주의**: 이 문서는 실제 발생한 이슈가 아니라 incident 작성 방법을 보여주는 예시다.  
> 실제 incident가 발생하면 이 형식을 따라 새 파일을 만든다.

---

## 1. Summary

- ID: `P-001`
- Date: TBD
- Area: Dashboard / Strategy Snapshot
- Severity: High
- Status: Draft
- Related Commit: TBD
- Related Tests: TBD
- Related Contract Docs:
  - `docs/architecture/boundary_contract.md`

---

## 2. Broken Contract

Dashboard에 표시되는 전략 판단 값은 strategy snapshot의 값을 재계산하지 않고 read-only로 조회해야 한다.

```text
Dashboard는 strategy_snapshot 테이블(또는 Gold serving table)을 read-only로 조회한다.
Dashboard layer에서 strategy logic 또는 allocation logic을 재구현하지 않는다.
```

---

## 3. Symptom

동일한 `trade_date` 기준으로 dashboard에 표시된 `invested_ratio` 값이 strategy snapshot 저장값과 다르게 보일 수 있는 가능성이 확인됐다.

- 발견 경로: 코드 리뷰 중 dashboard query layer에서 일부 계산을 재수행하는 패턴 발견
- 재현 여부: TBD

---

## 4. Expected Behavior

Dashboard는 strategy snapshot에 저장된 값을 그대로 표시해야 한다.

Dashboard 레이어에서 strategy logic 또는 allocation logic을 재구현하지 않는다.

동일한 `trade_date`에 대해 dashboard 표시값과 snapshot 저장값이 항상 일치해야 한다.

---

## 5. Root Cause

- 코드 경로: TBD
- 데이터 경로: TBD
- 문서/계약 경로: `docs/architecture/boundary_contract.md`에서 dashboard read-only 경계가 명시적으로 강제되지 않음
- 누락된 검증: dashboard output == stored snapshot 비교 테스트 없음
- 잘못된 가정: dashboard query가 strategy engine 로직을 동일하게 재현할 것이라는 가정

---

## 6. Fix

- 수정 파일: TBD
- 수정 방식: Dashboard는 Gold serving table 또는 snapshot table을 read-only로 조회하도록 고정
- 임시 조치인지 구조 개선인지: 구조 개선
- 영향 범위: dashboard layer만

---

## 7. Verification

- 실행한 테스트: TBD
- 추가한 테스트: `dashboard output == stored strategy snapshot` 비교 test 추가 예정
- 수동 확인: 동일 trade_date 기준 dashboard 표시값과 DB row 일치 확인
- 재현 전/후 결과: TBD

---

## 8. Prevention / Guard

- [ ] dashboard read-only contract 문서화 (`docs/architecture/boundary_contract.md`)
- [ ] `dashboard output == stored snapshot` consistency test 추가
- [ ] strategy calculation 중복 구현 금지 원칙을 contract에 명시

---

## 9. Remaining Debt

- 실제 dashboard 구현 이후 구체 테스트 추가 필요
- 현재 strategy engine이 Personal Track frozen 상태이므로 snapshot 직접 비교는 Observability layer에서 확인

---

## 10. Notes

이 예시는 Observability dashboard가 확장될 때 유사한 패턴을 사전에 방지하기 위한 참조 사례로 작성됐다.
