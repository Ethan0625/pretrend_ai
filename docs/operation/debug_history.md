Markers: operation
Status: active

# Pretrend Debug History

Pretrend 로컬 운영 및 개발 과정에서 발견된 주요 디버그/운영 이슈를 기록한다.

이 문서는 단순 작업 로그가 아니라, 운영 기준이 깨진 사례와 재발 방지 장치를 추적하기 위한 문서다.

각 incident는 다음 구조를 따른다.

```
Contract
→ Symptom
→ Root Cause
→ Fix
→ Verification
→ Prevention / Guard
```

Guard가 없으면 Resolved가 아니라 Monitoring 또는 Deferred로 기록한다.

---

## Incident Index

| ID | Date | Area | Severity | Status | Symptom | Root Cause | Guard | Detail |
|---|---|---|---|---|---|---|---|---|
| P-001 | TBD | Dashboard | High | Draft | Dashboard 표시값이 strategy snapshot 저장값과 다를 수 있음 | Dashboard query layer에서 strategy logic 재계산 시 불일치 | Dashboard read-only contract 문서화 예정 | [P-001](./incidents/P-001-example.md) |

---

## Severity 기준

| Severity | 기준 |
|---|---|
| Critical | 데이터 오염, 미래정보 누수, 잘못된 전략 판단 가능성 |
| High | 재현성 훼손, snapshot 불일치, 운영 결과 왜곡 |
| Medium | 특정 경로 실패, dashboard 불일치, 복구 가능한 batch 실패 |
| Low | 문서 누락, 경고, 개선성 이슈 |

---

## Status 기준

| Status | 의미 |
|---|---|
| Draft | 기록 초안 |
| Investigating | 원인 분석 중 |
| Resolved | 수정 및 검증 완료. Guard 장치 확인 필수. |
| Monitoring | 수정 후 관찰 중 |
| Deferred | 후속 작업으로 보류 |

---

## 주요 참조

- 운영 장애 시나리오 카탈로그: `docs/testing/operational_failure_scenario_catalog.md`
- 운영 재현성 계약: `docs/operation/reproducible_runtime_contract.md`
- 운영 이슈 단기 기록: `docs/operation/RUN_LOG.md`
- Incident 작성 템플릿: `docs/operation/incident_template.md`
- 보조 증거 이미지: `docs/assets/screenshots/`
