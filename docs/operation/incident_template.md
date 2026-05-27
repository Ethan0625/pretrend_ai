Markers: operation
Status: active

# Incident 작성 템플릿

각 incident는 이 파일을 복사해 `docs/operation/incidents/P-XXX-title.md`로 저장한다.

**스크린샷은 설명의 중심이 아니다.**  
스크린샷은 Symptom 섹션에서 필요할 때만 `docs/assets/screenshots/` 아래 보조 증거로 둔다.  
incident의 중심은 항상 아래 네 가지다.

```
Broken Contract
Root Cause
Fix
Guard
```

Guard가 없으면 Resolved가 아니라 Monitoring 또는 Deferred로 기록한다.

---

# P-XXX — Incident Title

## 1. Summary

- ID: `P-XXX`
- Date:
- Area: (Dashboard / Gold Layer / Calendar / EOD / Strategy / Runtime / Airflow / Tests / Docs)
- Severity: (Critical / High / Medium / Low)
- Status: (Draft / Investigating / Resolved / Monitoring / Deferred)
- Related Commit:
- Related Tests:
- Related Contract Docs:

---

## 2. Broken Contract

어떤 계약 또는 운영 기준이 깨졌는가?

예:

```text
Gold layer는 trade_date 기준으로 release_date < trade_date 조건을 만족하는 값만 사용해야 한다.
```

---

## 3. Symptom

어떤 증상으로 발견했는가?

- API 응답 이상
- dashboard 수치 불일치
- test failure
- DAG failure
- DB row mismatch
- snapshot mismatch
- log warning

보조 스크린샷: `docs/assets/screenshots/P-XXX-symptom.png` (있는 경우만)

---

## 4. Expected Behavior

정상 동작은 무엇이어야 하는가?

---

## 5. Root Cause

원인은 무엇인가?

- 코드 경로:
- 데이터 경로:
- 문서/계약 경로:
- 누락된 검증:
- 잘못된 가정:

---

## 6. Fix

무엇을 어떻게 수정했는가?

- 수정 파일:
- 수정 방식:
- 임시 조치인지 구조 개선인지:
- 영향 범위:

---

## 7. Verification

어떻게 검증했는가?

- 실행한 테스트:
- 추가한 테스트:
- 수동 확인:
- 재현 전/후 결과:

---

## 8. Prevention / Guard

같은 문제가 다시 발생하지 않게 어떤 장치를 두었는가?

- test
- contract doc update
- helper/service extraction
- validation rule
- dashboard read-only view
- CI gate
- runbook update

**Guard 없이 Resolved로 표기하지 않는다.**

---

## 9. Remaining Debt

아직 남은 한계나 후속 작업은 무엇인가?

---

## 10. Notes

추가 메모.
