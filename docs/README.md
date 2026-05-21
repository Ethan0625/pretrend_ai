# Docs Marker 가이드

Markers: operation, testing, architecture
Status: active
Publication: public

## 목적

Pretrend 문서는 재현 가능한 market data platform의 운영 계약, 데이터 구조, 검증 기준을 설명한다. 기준 언어는 한국어이며, 필요한 기술 용어와 고유 명칭만 영어를 함께 사용한다.

Docs marker는 문서의 운영 역할, 공개 위험도, 읽기 우선순위를 분류한다. Marker 자체가 계약 의미를 바꾸지는 않는다.

## Marker 어휘

| Marker | 의미 |
| --- | --- |
| `contract` | Public behavior, grain/key/schema, invariant, interface commitment를 정의한다. |
| `operation` | Runtime, runbook, environment, deployment, recovery procedure를 정의한다. |
| `testing` | Validation, pytest marker, smoke, reproducibility gate behavior를 정의한다. |
| `architecture` | System structure, boundary, data flow, module responsibility를 정의한다. |
| `roadmap` | 향후 순서나 phase plan을 정의한다. Active runtime contract가 아니다. |
| `agent` | Agent workflow, task execution, publication, collaboration rule을 정의한다. |
| `legacy` | Reference-only frozen material. Active source of truth로 취급하지 않는다. |
| `security` | Security, secret handling, access, publication risk guidance를 포함한다. |

## Status 값

| Status | 의미 |
| --- | --- |
| `active` | 현재 source of truth 또는 현재 운영 가이드. |
| `reference` | 유용한 맥락이지만 primary source of truth는 아니다. |
| `legacy` | Frozen historical material. 맥락 보존용이다. |
| `draft` | Work-in-progress guidance. Active contract를 override하면 안 된다. |

## 필수 형식

문서 상단에 단순 metadata line을 사용한다.

```text
  Markers: contract, operation
  Status: active
```

기존 title line은 metadata 위에 남겨둘 수 있다. 별도 contract review 없이 marker만으로 legacy 문서를 active로 재분류하지 않는다.

## 공개 정책 연결

Agent docs publication도 같은 marker vocabulary를 사용한다. Whitelist와 exclusion policy는 `.agent/README.md`를 참조한다.

## 주요 Active 문서

| 문서 | 역할 |
| --- | --- |
| [operation/reproducible_runtime_contract.md](operation/reproducible_runtime_contract.md) | Docker runtime, Airflow profile, restore/backfill, 격리 test DB, 재현성 검증 절차. |
| [operation/RUN_LOG.md](operation/RUN_LOG.md) | 로컬 운영/검증 중 발생한 재현성 이슈와 조치 내역. |
| [testing/operational_invariant_test_contract.md](testing/operational_invariant_test_contract.md) | pytest marker/gate, runtime gate, DB synthetic row smoke 기준. |
| [testing/operational_failure_scenario_catalog.md](testing/operational_failure_scenario_catalog.md) | `OFS-*` 운영 장애 시나리오와 synthetic test data anchor. |
