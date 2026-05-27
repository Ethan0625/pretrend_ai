Markers: operation
Status: active

# Screenshots — 보조 증거 저장소

이 디렉토리는 incident 문서의 보조 증거 이미지를 저장한다.

## 원칙

**스크린샷은 설명의 중심이 아니다.**

스크린샷은 다음 용도로만 사용한다.

- Symptom 섹션에서 "어떤 증상이 보였는가"를 시각적으로 보여줄 때
- 수정 전/후 상태 비교가 텍스트로 표현하기 어려울 때

설명과 근거는 반드시 incident 문서 본문(`Broken Contract`, `Root Cause`, `Fix`, `Guard`)에 텍스트로 작성한다.

## 파일 명명 규칙

```
{INCIDENT_ID}-{description}.png

예:
P-001-dashboard-drift-before.png
P-002-pit-leakage-query-result.png
```

## 참조 방법

incident 문서 Symptom 섹션에서:

```markdown
## 3. Symptom

...

보조 스크린샷: `docs/assets/screenshots/P-001-dashboard-drift-before.png`
```

## 주의사항

- 스크린샷에 개인 정보, 비공개 토큰, 내부 IP 주소가 포함되지 않도록 확인한다.
- 스크린샷 없이 텍스트만으로 충분한 경우 추가하지 않는다.
