# Project Summary

## Problem Definition

시계열 데이터 파이프라인에서 가장 먼저 깨지는 것은 모델 성능이 아니라 데이터 기준이다. 거시 지표와 시장 데이터는 관측 시점, 발표 시점, 소비 시점이 다르기 때문에, 이를 정리하지 않고 바로 전략이나 모델로 연결하면 point-in-time 위반, snapshot 비재현, partial overwrite 같은 운영 문제가 발생한다.

## Why This Exists

이 프로젝트는 자동매매 시스템을 만들기 위해 시작한 것이 아니라, **전략 판단 이전 단계의 데이터 기반을 재현 가능하게 고정하기 위해** 만들었다. 목표는 AI/ML이나 규칙 기반 전략이 원천 데이터를 직접 읽지 않고, Bronze / Silver / Gold 레이어를 거쳐 계약이 고정된 입력만 읽도록 만드는 것이다.

## Architecture Overview

```text
Bronze -> Silver -> Gold -> Strategy Engine

Bronze          : raw ingest and source preservation
Silver          : normalization, dedup, feature preparation
Gold            : PIT-safe, strategy-ready snapshots
Strategy Engine : Gold read-only consumer
```

- Bronze는 원천 보존과 수집 이력을 담당한다.
- Silver는 정규화, 중복 제거, 계약 정렬을 담당한다.
- Gold는 `selected_release_date < trade_date` 규칙을 만족하는 strategy-ready snapshot을 제공한다.
- Strategy Engine은 Gold를 소비할 뿐 상위 레이어를 다시 쓰지 않는다.

## Key Design Decisions

- **Contract-first**: grain, key, required columns, enum, write rule을 문서 계약으로 먼저 고정한다.
- **Layer / strategy separation**: 데이터 생성 계층과 전략 판단 계층을 분리해 변경 주기와 책임을 나눈다.
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
- Strategy/Paper/Backtest가 Gold snapshot 계약을 벗어나지 않는지

GitHub Actions CI는 `.github/workflows/ci.yaml`에서 `pytest -q`를 실행해 위 회귀를 기본선에서 점검한다.

## Explicit Boundaries / Non-goals

- 자동매매 시스템 자체 구현
- LLM을 핵심 매매 판단에 직접 연결
- 수익률이나 모델 성능을 프로젝트 핵심 가치로 홍보
- 실서비스 운영 성과 주장
- 레이어 계약보다 전략 튜닝을 우선하는 설계
