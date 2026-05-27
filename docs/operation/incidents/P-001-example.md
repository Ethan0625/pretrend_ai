Markers: operation
Status: draft

# P-001 예시 — 대시보드 지표 불일치

> **주의**: 이 문서는 실제 발생한 이슈가 아니라 인시던트 작성 방법을 보여주는 예시다.  
> 실제 인시던트가 발생하면 이 형식을 따라 새 파일을 만든다.

---

## 1. 요약

- ID: `P-001`
- 날짜: TBD
- 영역: 대시보드 / Strategy Snapshot
- 심각도: High
- 상태: Draft
- 관련 커밋: TBD
- 관련 테스트: TBD
- 관련 계약 문서:
  - `docs/architecture/boundary_contract.md`

---

## 2. 깨진 계약

대시보드에 표시되는 전략 판단 값은 strategy snapshot의 값을 재계산하지 않고 read-only로 조회해야 한다.

```text
대시보드는 strategy_snapshot 테이블(또는 Gold serving table)을 read-only로 조회한다.
대시보드 레이어에서 strategy logic 또는 allocation logic을 재구현하지 않는다.
```

---

## 3. 증상

동일한 `trade_date` 기준으로 dashboard에 표시된 `invested_ratio` 값이 strategy snapshot 저장값과 다르게 보일 수 있는 가능성이 확인됐다.

- 발견 경로: 코드 리뷰 중 dashboard query layer에서 일부 계산을 재수행하는 패턴 발견
- 재현 여부: TBD

---

## 4. 기대 동작

대시보드는 strategy snapshot에 저장된 값을 그대로 표시해야 한다.

대시보드 레이어에서 strategy logic 또는 allocation logic을 재구현하지 않는다.

동일한 `trade_date`에 대해 dashboard 표시값과 snapshot 저장값이 항상 일치해야 한다.

---

## 5. 근본 원인

- 코드 경로: TBD
- 데이터 경로: TBD
- 문서/계약 경로: `docs/architecture/boundary_contract.md`에서 dashboard read-only 경계가 명시적으로 강제되지 않음
- 누락된 검증: dashboard output == stored snapshot 비교 테스트 없음
- 잘못된 가정: dashboard query가 strategy engine 로직을 동일하게 재현할 것이라는 가정

---

## 6. 수정

- 수정 파일: TBD
- 수정 방식: 대시보드는 Gold serving table 또는 snapshot table을 read-only로 조회하도록 고정
- 임시 조치인지 구조 개선인지: 구조 개선
- 영향 범위: dashboard layer만

---

## 7. 검증

- 실행한 테스트: TBD
- 추가한 테스트: `dashboard output == stored strategy snapshot` 비교 test 추가 예정
- 수동 확인: 동일 trade_date 기준 dashboard 표시값과 DB row 일치 확인
- 재현 전/후 결과: TBD

---

## 8. 예방 / 가드

- [ ] dashboard read-only contract 문서화 (`docs/architecture/boundary_contract.md`)
- [ ] `dashboard output == stored snapshot` consistency test 추가
- [ ] strategy calculation 중복 구현 금지 원칙을 contract에 명시

---

## 9. 남은 부채

- 실제 dashboard 구현 이후 구체 테스트 추가 필요
- 현재 strategy engine이 Personal Track frozen 상태이므로 snapshot 직접 비교는 Observability layer에서 확인

---

## 10. 메모

이 예시는 Observability dashboard가 확장될 때 유사한 패턴을 사전에 방지하기 위한 참조 사례로 작성됐다.
