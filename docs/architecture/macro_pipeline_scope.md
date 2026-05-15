Markers: architecture, contract
Status: active

v2026.03.12 (재분류: 2026-05-12)

# macro_pipeline_dag Scope

> 🟢 **Infrastructure (공유) — 두 트랙 공통 자산**
>
> Macro pipeline DAG (`macro_pipeline_dag`)은 Bronze/Silver/Gold 레이어의 Macro feature 운영 자산이며, Observability Track / Personal Track 양쪽이 read-only로 소비합니다. Personal Track 운영 중단(2026-05-12~) 후에도 본 DAG는 **운영 유지** 대상입니다.
> 참조: [`track_separation.md`](./track_separation.md)


## 목적
- `macro_pipeline_dag`가 수집/정규화하는 외부 일별 시계열의 운영 경계를 고정한다.
- 본 문서는 경제/정책 지표(FRED)를 DAG에서 처리하는 범위를 명시한다.

## 포함 데이터 소스
1. FRED 경제지표
   - 금리, 물가, 고용 등 거시/정책 신호

## 설계 결정
- `macro_pipeline_dag`는 FRED 기반 경제지표 수집에 집중한다.
- 시장 심리 신호(VIX 계열, SKEW 등)는 EOD 파이프라인(`eod_pipeline_dag`)을 통해 수집한다.
- DAG 내부에서는 단일 task(`run_macro_job`)로 Bronze → Silver 처리를 수행한다.

## 포함 범위
- Bronze ingest
- Silver feature 계산
- 일별 스케줄링
- 파티션 overwrite 기반 멱등 저장
- 실패 시 경고 로그 + 독립 복구

## 비포함 범위
- Gold feature 계산
- VIX/SKEW 등 시장 심리 신호 수집 (→ eod_pipeline_dag)
- Short Engine 통합
- 전략 신호 생성

## 운영 원칙
- FRED task 기존 동작은 보존한다.
- 신규 시장 심리 신호는 EOD 파이프라인에 편입한다.
