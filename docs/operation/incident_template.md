Markers: operation
Status: active

# 인시던트 작성 템플릿

각 인시던트는 이 파일을 복사해 `docs/operation/incidents/P-XXX-title.md`로 저장한다.

**스크린샷은 설명의 중심이 아니다.**  
스크린샷은 증상 섹션에서 필요할 때만 `docs/assets/screenshots/` 아래 보조 증거로 둔다.  
인시던트의 중심은 항상 아래 네 가지다.

```
깨진 계약
근본 원인
수정
가드
```

가드가 없으면 Resolved가 아니라 Monitoring 또는 Deferred로 기록한다.

---

# P-XXX — 인시던트 제목

## 1. 요약

- ID: `P-XXX`
- 날짜:
- 영역: (대시보드 / Gold 계층 / Calendar / EOD / Strategy / Runtime / Airflow / Tests / Docs)
- 심각도: (Critical / High / Medium / Low)
- 상태: (Draft / Investigating / Resolved / Monitoring / Deferred)
- 관련 커밋:
- 관련 테스트:
- 관련 계약 문서:

---

## 2. 깨진 계약

어떤 계약 또는 운영 기준이 깨졌는가?

예:

```text
Gold layer는 trade_date 기준으로 release_date < trade_date 조건을 만족하는 값만 사용해야 한다.
```

---

## 3. 증상

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

## 4. 기대 동작

정상 동작은 무엇이어야 하는가?

---

## 5. 근본 원인

원인은 무엇인가?

- 코드 경로:
- 데이터 경로:
- 문서/계약 경로:
- 누락된 검증:
- 잘못된 가정:

---

## 6. 수정

무엇을 어떻게 수정했는가?

- 수정 파일:
- 수정 방식:
- 임시 조치인지 구조 개선인지:
- 영향 범위:

---

## 7. 검증

어떻게 검증했는가?

- 실행한 테스트:
- 추가한 테스트:
- 수동 확인:
- 재현 전/후 결과:

---

## 8. 예방 / 가드

같은 문제가 다시 발생하지 않게 어떤 장치를 두었는가?

- 테스트
- 계약 문서 업데이트
- helper/service 추출
- 검증 규칙
- dashboard read-only view
- CI gate
- runbook 업데이트

**가드 없이 Resolved로 표기하지 않는다.**

---

## 9. 남은 부채

아직 남은 한계나 후속 작업은 무엇인가?

---

## 10. 메모

추가 메모.
