# Operational scenario fixtures

이 디렉터리는 운영 장애를 재현하는 synthetic test data를 고정하는 위치다. production dump, 실제 API 응답 원본, 개인 로컬 상태를 보관하지 않는다.

각 시나리오는 아래 형식을 따른다.

```text
tests/fixtures/operational_scenarios/<scenario-id>_<short_name>/
├─ README.md
├─ input/
└─ expected/
```

`README.md`에는 다음 항목을 적는다.

- 시나리오 ID: 예 `OFS-001`
- 막는 장애: 실제 운영 흐름에서 어떤 실패를 막는지
- 입력 데이터: 어떤 row/column/edge case가 필요한지
- 기대 결과: pytest가 어떤 invariant를 assert하는지
- gate: `fast`, `runtime`, `dags`, `pre-dashboard` 중 어디에 들어가는지

작은 fixture는 테스트 파일 안의 builder 함수로 둘 수 있다. 이 경우에도 함수명 또는 docstring에 시나리오 ID를 남긴다.
