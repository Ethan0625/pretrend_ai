# Project Summary

> ⚠️ **2026Q2 방향 재정의 안내**
>
> 본 프로젝트는 **Market Structure Observability Runtime**으로 재정의되었다.
> 본 문서는 데이터 파이프라인 측면의 설계 의도를 설명하며 여전히 유효하지만, **자동매매/Strategy Engine 중심 서술은 Personal Track(동결) 자산을 의미**한다.
> 신규 작업 방향은 다음 문서를 우선 참조한다:
> - [`docs/architecture/track_separation.md`](architecture/track_separation.md) — 트랙 분리 원칙
> - [`.agent/REFACTOR_2026Q2.md`](../.agent/REFACTOR_2026Q2.md) — 리팩토링 계획 (Phase 0~3)

## Problem Definition

투자 영역에서는 "거시경제 흐름이 중요하다"는 말을 자주 하지만, 실제로 거시 이벤트와 시장 구조 변화가 어떤 방식으로 연결되는지를 반복적으로 확인할 수 있는 개인용 도구는 많지 않다. 저는 투자 전망을 제시하기보다, 무료로 접근 가능한 거시·ETF 데이터를 기반으로 시장 상태를 구조화하고, 특정 시점의 시장 구조가 과거 어떤 구간과 유사하거나 다른지를 재현 가능한 방식으로 관측하는 시스템을 만들고자 했다.

## Why This Transition

초기 Pretrend는 로컬 기반 매매 실험 구조였으나, 프로젝트 목적을 예측에서 시장 구조 관측으로 전환하면서 공개 운영 가능한 데이터 시스템으로 재설계하고 있다.

이에 따라 로컬 의존 배치 구조를 정리하고, 자동화된 스케줄러 기반 수집, Bronze/Silver/Gold 데이터 레이어, market state feature 생성, dashboard serving, freshness monitoring 구조로 전환하고 있다.

## 데이터 기반 운영 원칙 (legacy 보조 설명)

시계열 데이터 파이프라인에서 가장 먼저 깨지는 것은 모델 성능이 아니라 데이터 기준이다. 거시 지표와 시장 데이터는 관측 시점, 발표 시점, 소비 시점이 다르기 때문에, 이를 정리하지 않고 바로 전략이나 모델로 연결하면 point-in-time 위반, snapshot 비재현, partial overwrite 같은 운영 문제가 발생한다.

이 프로젝트는 전략 판단 이전 단계의 데이터 기반을 재현 가능하게 고정하기 위해, AI/ML이나 규칙 기반 분석이 원천 데이터를 직접 읽지 않고 Bronze / Silver / Gold 레이어를 거쳐 계약이 고정된 입력만 읽도록 만든다.

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
