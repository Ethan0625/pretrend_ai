# Gold Layer v1 — Design Contract (문서 전용)

## 1. 개요 (Overview & Status)
- Gold Layer v1은 Silver 출력물을 기반으로 한 **설계 계약서**이며, 아직 구현되지 않았다.
- 구현은 Calendar pipeline(econ_events, fred_vintages)이 준비되기 전까지 차단된다.
- 목적: 향후 구현·인터뷰 시 참조할 고정된 계약으로, 설계 변경을 의도하지 않는다.

## 2. Gold Layer의 역할과 범위
- 역할: Silver Macro/EOD Feature를 사용해 사전 계산된 Gold 신호/타깃을 제공한다.
- 범위: 데이터 가용성·PIT(Poin t-in-Time) 안전성·투명성을 보장하는 계약 정의에 한정한다. 구현, 스케줄링, DAG 설계는 본 문서 범위를 벗어난다.

## 3. Calendar Pipeline 의존성 (구현 차단 사유 명시)
- Gold v1은 Calendar pipeline( econ_events, fred_vintages )에서 제공하는 이벤트/발표 일정에 **의존**한다.
- 해당 Calendar 파이프라인은 아직 존재하지 않으며, 구현 전까지 Gold v1 실행은 허용되지 않는다.
- Calendar가 준비되면 `release_date` 가정값을 검증·보정하고, PIT 조인을 위한 공식 타임라인을 제공한다.

## 4. Core Philosophy (release_date 철학)
- Gold의 모든 값은 `release_date` 시점에 **알 수 있었다고 가정되는 정보**만을 반영해야 한다.
- `release_date`는 가정(assumption)에 기반하며 실제 발표 시각의 그라운드 트루스가 아니다.
- 투명성/설명가능성: 각 값이 어떤 `release_date` 가정 아래 산출됐는지 명시하고, Silver 입력으로 추적 가능해야 한다.

## 5. Market Cutoff 규칙 (T+1)
- 기본 전제: 시장 반영 기준은 T+1 컷오프를 따른다.
- `release_date` 기준으로 다음 거래일부터 사용할 수 있다는 가정이며, 실거래 시각 검증은 Calendar가 준비된 후 수행한다.

## 6. Gold 데이터 모델 개요 (코드 없이 설명)
- 입력: Silver Macro Features, Silver EOD Features, 그리고 향후 Calendar 이벤트/빈티지 정보.
- 출력: `business key`(symbol 또는 indicator_id + date 등), `release_date`, `trade_date`(또는 대상 날짜), 파생 신호/타깃, 입력 파티션·라인리지, 감사용 메타데이터.
- 파티셔닝: Silver와 일관된 단위(예: symbol/year/month 또는 macro date 버킷)를 유지한다.

## 7. PIT Join 규칙 (Plain English → 한국어)
- 조인은 항상 `release_date` 기준으로 수행하며, 소비 시점보다 이후의 정보는 사용할 수 없다.
- 인게스트 시각이나 관측 시각으로 조인하지 않는다(이는 감사 전용).
- 동일 지표/값에 여러 릴리즈가 있는 경우, 소비 측 `trade_date`보다 **엄격히 이전**의 `release_date` 버전을 선택한다.
- Calendar 데이터가 없을 때는 가정된 `release_date`를 사용하되, “assumption-based”로 명시한다.

## 8. Evidence Columns와 감사 가능성(Auditability)
- Silver 입력 파티션/파일을 추적할 수 있는 라인리지 컬럼, 사용한 `release_date` 가정, 인게스트 시각 메타를 보존한다.
- 관측 시점과 가용 시점을 구분하기 위해 ingestion 메타와 `release_date`를 모두 기록한다.
- Calendar 검증 여부(assumption vs validated)를 식별할 플래그를 포함한다.
- 재실행 결정성: 동일 입력·가정으로 재실행 시 동일 결과를 산출해야 한다.

## 9. PIT Invariants (테스트 계약)
- `release_date`는 소비되는 `trade_date`보다 반드시 이른 시점이어야 한다: `release_date < trade_date`.
- 중복 릴리즈가 있을 경우 가장 늦은(가장 최근) `release_date`를 선택하되, 여전히 소비 시점 이전이어야 한다.
- Calendar 미구현 시 가정 기반임을 표시해야 하며, 추후 Calendar 반영 시 동일 로직으로 재현 가능해야 한다.

## 10. Gold v1의 Non-Goals
- Calendar 파이프라인 구현 또는 Gold 계산 로직 구현을 포함하지 않는다.
- 실제 발표 시각의 완전한 정확성을 보장하지 않는다(`release_date`는 가정).
- 전략/유니버스/LLM 기능 확장이나 새로운 설계 제안은 범위 밖이다.

## 11. 구현 선행 조건 (Implementation Prerequisites)
- Calendar pipeline(econ_events, fred_vintages)이 구현되어 `release_date` 가정을 검증할 수 있어야 한다.
- PIT 조인을 위한 공식 캘린더 기준이 마련된 뒤에야 Gold v1 구현을 착수한다.
- 상기 조건 충족 전까지 본 문서는 설계 계약으로만 사용하며, 구현은 차단한다.
