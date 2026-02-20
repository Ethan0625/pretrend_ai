# Universe-ETF (Execution Universe) — Contract (SOT)

## Document Status
| Item | Value |
| --- | --- |
| Status | Active |
| Structure Policy | 구조는 고정, 기능은 확장 |
| Effective Date | 2026-02-13 |
| Change Tracking | docs/changelog.md |

## Capability Matrix
| Capability | Status | Notes |
| --- | --- | --- |
| Core scope | Active | 본 문서의 계약/설계 범위 |
| Extension ports | Reserved | v1+ 확장 포트는 인터페이스만 정의 |
| Numeric scoring/tuning | Not supported | 본 문서 범위에서 금지 |

## TOC
- [1. 문서 목적](#1-문서-목적)
- [2. Scope & Non-Goals](#2-scope--non-goals)
- [3. 입력 계약](#3-입력-계약)
- [4. 출력 계약](#4-출력-계약)
- [5. Grain / Key](#5-grain--key)
- [6. 불변식](#6-불변식)
- [7. DoD](#7-dod)

연계 문서:
- `docs/strategy_architecture.md`
- `docs/architecture/market_structure_composer_contract.md`
- `docs/architecture/gold_design_contract.md`
- `docs/architecture/calendar_design_contract.md`
- `docs/architecture/eod_observability_contract.md`

## 1. 문서 목적
### 책임
- Universe-ETF(v1)의 입력/출력 인터페이스를 SOT로 고정한다.
- Market Structure Composer와 Allocation Engine 사이의 계약 경계를 명확히 한다.

### Non-goals
- 자산별 상세 점수식, 가중치, 랭킹 로직을 정의하지 않는다.

## 2. Scope & Non-Goals
### 책임
- Observability ETF 대상의 후보 선별 계약을 정의한다(Execution Universe 범위).
- Composer 차단 상태에서 결과 제약을 명시한다.

### Non-goals
- 대상: 개별 종목 제외, Observability ETF만
- Universe-Stock(U0~U3) 파이프라인은 본 계약 범위 밖(별도 로드맵)
- 주문 실행/포지션 사이징 포함하지 않음

## 3. 입력 계약
### 책임
- Universe-ETF 입력 소스와 필수 컬럼을 고정한다.

### Non-goals
- 입력 테이블 재계산/보정

입력 소스:
1. Market Structure Composer output
2. Gold EOD Features

입력 스키마:

| 입력 | 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| MS Composer | trade_date | DATE | Y | 기준일 |
| MS Composer | run_universe | BOOLEAN | Y | Universe-ETF 실행 여부 |
| MS Composer | risk_gate | BOOLEAN | Y | 증가 차단 브레이크 상태 |
| Gold EOD | symbol | TEXT | Y | Observability 심볼 |
| Gold EOD | trade_date | DATE | Y | 기준일 |
| Gold EOD | asset_group | TEXT | Y | 그룹 라벨 |
| Gold EOD | asset_name | TEXT | Y | canonical 라벨 |
| Gold EOD | asset_subtype | TEXT | N | 세부 라벨 |
| Gold EOD | ret_20d | FLOAT | N | 상대강도 재료 |
| Gold EOD | vol_20d | FLOAT | N | 리스크 재료 |

## 4. 출력 계약
### 책임
- Allocation Engine이 소비 가능한 `candidate_etf_list` 스키마를 고정한다.

### Non-goals
- 후보 개수 제한/정렬 규칙 확정

필수 출력 컬럼:

| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| rebalance_date | DATE | Y | 리밸런싱 기준일 |
| symbol | TEXT | Y | ETF 심볼 |
| asset_group | TEXT | Y | 그룹 라벨 |
| relative_strength | FLOAT | N | 상대강도 지표 |
| is_candidate | BOOLEAN | Y | 후보 여부 |

개념 예시:

```yaml
rebalance_date: 2026-02-12
symbol: XLV
asset_group: SECTOR
relative_strength: 0.14
is_candidate: true
```

## 5. Grain / Key
### 책임
- 출력 grain과 유일성 기준을 명시한다.

### Non-goals
- 동일일 다중 버전 관리 전략

- Grain: `(rebalance_date, symbol)`
- Primary key: `(rebalance_date, symbol)`
- `rebalance_date`는 Composer `trade_date`와 동일 캘린더 기준을 사용한다.

## 6. 불변식
### 책임
- Universe-ETF 출력의 무결성 제약을 명시한다.

### Non-goals
- 후보 우선순위 알고리즘 정의

- Observability 라벨은 read-only (입력 라벨 수정 금지)
- `run_universe=false`이면 candidate 0개
- `is_candidate`는 BOOLEAN 외 값 금지
- `asset_group`은 Observability ENUM(`INDEX/COUNTRY/COMMODITY/BOND/SECTOR`) 외 값 금지

## 7. DoD
### 책임
- 구현 검증 최소 기준을 제공한다.

### Non-goals
- 테스트 데이터셋 고정

- **UV1**: 차단 상태(`run_universe=false`) 입력 시 candidate 0개 검증
- **UV2**: 필수 컬럼/타입 검증
- **UV3**: `asset_group` ENUM 위반 금지 검증

---

## Change History
| Date | Summary | References |
| --- | --- | --- |
| 2026-02-21 | Universe 용어 이원화 반영: Universe-ETF(Execution) 계약으로 명시, Universe-Stock(U0~U3) 범위 분리 | docs/changelog.md |
| 2026-02-13 | 파일명 버전 제거 및 문서 표준 블록(Document Status/Capability Matrix) 적용 | docs/changelog.md |
