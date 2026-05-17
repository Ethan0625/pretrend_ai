# Project Summary

Markers: architecture
Status: active

> ⚠️ **현재 포지셔닝**
>
> Pretrend는 **재현 가능한 market data platform**이다.
> 이 문서는 데이터 파이프라인과 운영 설계 의도를 설명하는 공개 요약입니다.
> 현재 운영 구조는 [`docs/system_overview.md`](system_overview.md),
> [`docs/architecture/system_map_2026q2.md`](architecture/system_map_2026q2.md),
> [`docs/operation/reproducible_runtime_contract.md`](operation/reproducible_runtime_contract.md)를 우선합니다.

## Problem Definition

금융·거시 데이터는 수집 시점, 발표 시점, 관측 시점이 서로 다르다. 이 차이를 정리하지 않고 바로 예측 모델이나 자동매매 시스템으로 연결하면 point-in-time 위반, schema drift, 재처리 불가능한 snapshot이 누적된다. Pretrend는 시장 판단 이전 단계에서 데이터 정합성, 시점 안전성, 재처리 가능성, 운영 재현성을 확보하기 위한 market data platform으로 설계한다.

## 왜 이 방향인가

초기 Pretrend는 로컬 기반 매매 실험 구조였으나, 프로젝트 목적을 예측에서 재현 가능한 데이터 플랫폼과 시장 구조 관측 기반으로 전환하면서 공개 운영 가능한 데이터 시스템으로 재설계하고 있다.

이에 따라 로컬 의존 배치 구조를 정리하고, 자동화된 스케줄러 기반 수집, Bronze/Silver/Gold 데이터 레이어, market state feature 생성, dashboard serving, freshness monitoring 구조로 전환하고 있다.

## 데이터 기반 운영 원칙

시계열 데이터 파이프라인에서 가장 먼저 깨지는 것은 모델 성능이 아니라 데이터 기준이다. 거시 지표와 시장 데이터는 관측 시점, 발표 시점, 소비 시점이 다르기 때문에, 이를 정리하지 않고 바로 전략이나 모델로 연결하면 point-in-time 위반, snapshot 비재현, partial overwrite 같은 운영 문제가 발생한다.

이 프로젝트는 전략 판단 이전 단계의 데이터 기반을 재현 가능하게 고정하기 위해, AI/ML이나 규칙 기반 분석이 원천 데이터를 직접 읽지 않고 Bronze / Silver / Gold 레이어를 거쳐 계약이 고정된 입력만 읽도록 만든다. LLM은 의사결정 주체가 아니라, 이미 구축된 관측 결과를 설명하는 보조 계층으로만 사용한다.

## Architecture Overview

```text
Bronze -> Silver -> Gold Parquet SOT -> Postgres Mirror -> FastAPI

Bronze   : raw ingest and source preservation
Silver   : normalization, dedup, feature preparation
Gold     : PIT-safe feature snapshots
Postgres : serving mirror/cache
FastAPI  : read-only observability API
```

- Bronze는 원천 보존과 수집 이력을 담당한다.
- Silver는 정규화, 중복 제거, 계약 정렬을 담당한다.
- Gold는 `selected_release_date < trade_date` 규칙을 만족하는 PIT-safe feature snapshot을 제공한다.
- Postgres와 FastAPI는 dashboard/API serving을 담당하며 upstream feature SOT를 다시 쓰지 않는다.

## Key Design Decisions

- **Contract-first**: grain, key, required columns, enum, write rule을 문서 계약으로 먼저 고정한다.
- **Read-only serving boundary**: 데이터 생성 계층과 조회/설명 계층을 분리해 변경 주기와 책임을 나눈다.
- **Snapshot storage**: `decision_date`와 파티션 기준으로 저장해 비교 가능한 산출물을 남긴다.
- **Idempotent overwrite**: `_tmp_run` 이후 atomic rename을 사용하고 append 누적을 피한다.
- **Fail-open**: 결측이 있어도 schema는 유지하고 `UNKNOWN`으로 전달한다.

## Operating Principles

- point-in-time safety
- reproducibility over ad-hoc convenience
- overwrite + atomic write
- lineage and evidence columns
- contract and schema validation
- downstream read-only boundaries

## What Tests/CI Protect

- 중복 적재나 재실행으로 파티션이 오염되지 않는지
- Calendar/Gold 계층의 PIT 규칙이 유지되는지
- 레이어별 schema / contract drift가 없는지
- snapshot write 경로가 partial state를 남기지 않는지
- API/serving layer가 Gold/Postgres snapshot 계약을 벗어나지 않는지

GitHub Actions CI는 `.github/workflows/ci.yaml`에서 `pytest --gate fast -q --tb=short`를 실행해 빠른 운영 회귀를 기본선에서 점검한다. DB, restore, DAG 변경은 로컬 또는 Docker에서 `pytest --gate runtime`, `pytest --gate dags`, `pytest --gate pre-dashboard`를 추가로 실행한다.
pytest 추가 기준은 `docs/testing/operational_failure_scenario_catalog.md`의 운영 장애 시나리오와 synthetic test data 계약을 따른다.

## Explicit Boundaries / Non-goals

- 자동매매 시스템 자체 구현
- LLM을 핵심 매매 판단에 직접 연결
- 수익률이나 모델 성능을 프로젝트 핵심 가치로 홍보
- 실서비스 운영 성과 주장
- 레이어 계약보다 전략 튜닝을 우선하는 설계
