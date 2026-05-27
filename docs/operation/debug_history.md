Markers: operation
Status: active

# Pretrend 디버그 히스토리

Pretrend 로컬 운영 및 개발 과정에서 발견된 주요 디버그/운영 이슈를 기록한다.

이 문서는 단순 작업 로그가 아니라, 운영 기준이 깨진 사례와 재발 방지 장치를 추적하기 위한 문서다.

`RUN_LOG.md`는 시간순 운영 로그이고, 이 문서는 그중 재발 방지 가치가 있는 항목을 승격한 인시던트 인덱스다.
대시보드의 "디버그 히스토리" 탭은 이 인덱스를 정적으로 미러링하며, 상세 설명의 기준 위치는 `docs/operation/incidents/`다.

각 인시던트는 다음 구조를 따른다.

```
계약
→ 증상
→ 근본 원인
→ 수정
→ 검증
→ 예방 / 가드
```

가드가 없으면 Resolved가 아니라 Monitoring 또는 Deferred로 기록한다.

---

## 인시던트 인덱스

| ID | 날짜 | 영역 | 심각도 | 상태 | 증상 | 근본 원인 | 가드 | 상세 |
|---|---|---|---|---|---|---|---|---|
| P-101 | 2026-05-20 | Docker Runtime | Medium | Resolved | Public image pull이 credential helper 오류로 실패 | Windows Docker Desktop `credsStore: "desktop"` helper가 현재 로그인 세션에서 응답하지 않음 | credential helper troubleshooting을 운영 가이드와 RUN_LOG에 고정 | [P-101](./incidents/P-101-docker-credential-helper.md) |
| P-102 | 2026-05-27 | Postgres / API | High | Monitoring | `/health`는 200이지만 DB 의존 API가 500 또는 timeout | Postgres crash recovery 중 API healthcheck가 DB readiness를 대표하지 못함 | `/api/v1/meta` freshness check와 Postgres recovery runbook을 운영 가이드에 고정 | [P-102](./incidents/P-102-postgres-crash-recovery.md) |
| P-103 | 2026-05-27 | EOD Pipeline | High | Resolved | 짧은 증분 backfill이 전체 backfill처럼 오래 실행됨 | EOD Silver가 symbol 미지정 시 Bronze 전체를 `rglob`로 읽은 뒤 날짜 필터링 | 날짜 window 기반 partition pruning + old corrupt partition 방어 테스트 추가 | [P-103](./incidents/P-103-eod-silver-window-scan.md) |
| P-104 | 2026-05-27 | Regime Similarity | Medium | Deferred | Gold/EOD freshness는 최신인데 `similarity_regime`만 과거 날짜에 머묾 | regime similarity source가 Observability 독립 builder가 아니라 legacy `strategy_job` snapshot에 의존 | P33 이후 Observability regime runtime snapshot 독립화 task로 분리 | [P-104](./incidents/P-104-regime-snapshot-dependency.md) |

`P-001-example.md`는 실제 인시던트가 아니라 작성 형식 예시다. 실제 운영 이슈 인덱스에는 포함하지 않는다.

---

## 심각도 기준

| 심각도 | 기준 |
|---|---|
| Critical | 데이터 오염, 미래정보 누수, 잘못된 전략 판단 가능성 |
| High | 재현성 훼손, snapshot 불일치, 운영 결과 왜곡 |
| Medium | 특정 경로 실패, dashboard 불일치, 복구 가능한 batch 실패 |
| Low | 문서 누락, 경고, 개선성 이슈 |

---

## 상태 기준

| 상태 | 의미 |
|---|---|
| Draft | 기록 초안 |
| Investigating | 원인 분석 중 |
| Resolved | 수정 및 검증 완료. 가드 장치 확인 필수. |
| Monitoring | 수정 후 관찰 중 |
| Deferred | 후속 작업으로 보류 |

---

## 주요 참조

- 운영 장애 시나리오 카탈로그: `docs/testing/operational_failure_scenario_catalog.md`
- 운영 재현성 계약: `docs/operation/reproducible_runtime_contract.md`
- 운영 이슈 단기 기록: `docs/operation/RUN_LOG.md`
- 인시던트 작성 템플릿: `docs/operation/incident_template.md`
- 보조 증거 이미지: `docs/assets/screenshots/`
