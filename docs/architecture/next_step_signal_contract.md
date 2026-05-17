# Next Step Signal — Contract (SOT)

Markers: architecture, contract
Status: active

> 🟢 **Market Data Platform 관측 계약**
>
> 본 문서는 Gold feature layer를 소비해 **5/10/20/60/120거래일 sojourn / transition hazard**를 관측하는 계약입니다.
> 매매 신호가 아니라 read-only observation context로 활용됩니다.
> 코드 모듈은 P22(2026-05-13)에서 `observability/regime/transition/` 하위로 이전 완료되었습니다.
> 기존 `strategy_engine/next_step/` 경로는 backward compatibility re-export shim으로 유지됩니다.
> 참조: [`track_separation.md`](./track_separation.md)

## 문서 상태
| Item | Value |
| --- | --- |
| Status | **Active (Observability 자료, 전이 관측 컨텍스트, Phase 1 추출 완료 — 2026-05-13)** |
| Structure Policy | 구조는 고정, 기능은 확장 |
| Effective Date | 2026-02-24 |
| Change Tracking | docs/changelog.md |

## 기능 매트릭스
| 기능 | 상태 | 비고 |
| --- | --- | --- |
| Core scope | Active | 본 문서의 계약/설계 범위 |
| Extension ports | Reserved | v1+ 확장 포트는 인터페이스만 정의 |
| Numeric scoring/tuning | Not supported | 본 문서 범위에서 금지 |

## 목차
- [1. 문서 목적](#1-문서-목적)
- [2. 범위와 제외 범위](#2-scope--non-goals)
- [3. Inputs](#3-inputs)
- [4. Outputs](#4-outputs)
- [5. Axis×Horizon Evidence Matrix (4x3)](#5-axishorizon-evidence-matrix-4x3)
- [6. 운영 게이트 규칙(Soft Gate)](#6-운영-게이트-규칙soft-gate)
- [7. Hypothesis (v3.2 Extension)](#7-hypothesis-v32-extension)
- [8. Hypothesis (v3.3 Duration/Transition MVP)](#8-hypothesis-v33-durationtransition-mvp)
- [9. Hypothesis (v3.4.2-phase State Machine)](#9-hypothesis-v342-phase-state-machine)
- [10. Invariants](#10-invariants)
- [11. DoD](#11-dod)

참조:
- `docs/architecture/strategy_engine_design.md`
- `docs/architecture/axis_horizon_dependency_contract.md`
- `docs/architecture/market_structure_long_contract.md`
- `docs/architecture/market_structure_mid_contract.md`
- `docs/architecture/market_structure_short_contract.md`
- `docs/architecture/paper_execution_ledger_contract.md`
- `docs/architecture/allocation_engine_contract.md`
- `docs/architecture/group_transition_signal_contract.md`

## 1. 문서 목적
### 책임
 - 현재 상태(3-state: long/mid/short)와 다음 스텝 가설(5/10/20/60/120D)의 출력 계약을 고정한다.
- Telegram/리포트 소비용 4축 근거 서술 인터페이스를 고정한다.
- 12셀(4축×3horizon)을 실행 신호가 아닌 진단 KPI 계층으로 정의한다.
- Strategy/Paper/Backtest가 공통 소비하는 **운용 게이트 입력(snapshot)** 인터페이스를 고정한다.

### 제외 범위
- 실거래 주문/집행 판단 직접 생성
- ML 모델 학습/튜닝 기준 정의

## 2. 범위와 제외 범위
### Scope
- 입력 상태(long_phase, mid_regime, short_signal) 기반 다음 스텝 가설 생성
- 4축(매크로/가격/수급/심리) 근거 문구 생성
- 12셀 진단 KPI(coverage, unknown_ratio) 계산
- 시장 3-state 전이예측 전용 인터페이스 고정

### 제외 범위
- 12셀 개별 셀을 독립 실행 신호로 승격
- 가설 정확도 성능 보장
- 전술 그룹 전이 예측(별도 계약: `group_transition_signal_contract.md`)

## 3. Inputs
### 책임
- Next Step Signal의 최소 입력을 고정한다.

### 제외 범위
- Axis 엔진 내부 산출식 정의

| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| trade_date | DATE | Y | 기준일 |
| long_phase | TEXT | Y | 장기 상태 ENUM |
| mid_regime | TEXT | Y | 중기 상태 ENUM |
| short_signal | TEXT | Y | 단기 상태 ENUM |
| long_detail_json | TEXT(JSON) | N | 장기 근거 상세 |
| mid_detail_json | TEXT(JSON) | N | 중기 근거 상세 |
| short_detail_json | TEXT(JSON) | N | 단기 근거 상세 |

결측 처리:
- detail JSON 결측/파싱 실패 시 fail-open 문구를 출력한다.

## 4. Outputs
### 책임
- 다음 스텝 가설 + 근거 + 진단 인터페이스를 고정한다.

### 제외 범위
- 포트폴리오 비중 조정 명령 생성

| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| trade_date | DATE | Y | 기준일 |
| bias_5d | TEXT | Y | `RISK_ON_BIAS`, `NEUTRAL_BIAS`, `RISK_OFF_BIAS`, `UNKNOWN` |
| confidence_5d | FLOAT | Y | 0~1 |
| bias_10d | TEXT | Y | `RISK_ON_BIAS`, `NEUTRAL_BIAS`, `RISK_OFF_BIAS`, `UNKNOWN` |
| confidence_10d | FLOAT | Y | 0~1 |
| bias_20d | TEXT | Y | `RISK_ON_BIAS`, `NEUTRAL_BIAS`, `RISK_OFF_BIAS`, `UNKNOWN` |
| confidence_20d | FLOAT | Y | 0~1 |
| bias_60d | TEXT | Y | `RISK_ON_BIAS`, `NEUTRAL_BIAS`, `RISK_OFF_BIAS`, `UNKNOWN` |
| confidence_60d | FLOAT | Y | 0~1 |
| bias_120d | TEXT | Y | `RISK_ON_BIAS`, `NEUTRAL_BIAS`, `RISK_OFF_BIAS`, `UNKNOWN` |
| confidence_120d | FLOAT | Y | 0~1 |
| bias_effective | TEXT | N | v3.2 확장 포트(실제 적용 bias, nullable) |
| bias_override_flag | BOOLEAN | N | v3.2 확장 포트(override 발동 여부, nullable) |
| bias_override_reason | TEXT | N | v3.2 확장 포트(`PANIC`, `RISK_OFF`, `NONE`, nullable) |
| bias_state_source | TEXT | N | v3.4.2 확장 포트(`BASELINE`, `OVERLAY`, `HOLD_COOLDOWN`, `HARD_GATE`) |
| bias_switch_flag | BOOLEAN | N | v3.4.2 확장 포트(이전 bias 대비 전환 여부) |
| bias_switch_reason | TEXT | N | v3.4.2 확장 포트(`PHASE_BASELINE`, `MID_RISK_ON`, `SHORT_PANIC`, `COOLDOWN` 등) |
| bias_cooldown_left | INT | N | v3.4.2 확장 포트(재전환 금지 잔여 거래일) |
| bias_candidate_20d | TEXT | N | v3.4.2a 확장 포트(cooldown 압축 시 후보 bias) |
| cooldown_compressed_flag | BOOLEAN | N | v3.4.2a 확장 포트(cooldown 압축 후보 여부) |
| cooldown_compressed_reason | TEXT | N | v3.4.2a 확장 포트(`MID_RISK_ON`, `RELIEF_STREAK`, `NONE`) |
| hard_gate_exit_assist_flag | BOOLEAN | N | v3.4.2a 확장 포트(run_universe 복귀 보조 완화 후보 여부) |
| hard_gate_exit_assist_reason | TEXT | N | v3.4.2a 확장 포트(`RUN_UNIVERSE_RECOVERY_RELIEF`, `NONE`) |
| state_age_days | INT | N | v3.3 확장 포트(현재 3-state 연속 일수) |
| sojourn_prob_5d | FLOAT | N | v3.3 확장 포트(5거래일 지속 확률) |
| sojourn_prob_10d | FLOAT | N | v3.3 확장 포트(10거래일 지속 확률) |
| sojourn_prob_20d | FLOAT | N | v3.3 확장 포트(20거래일 지속 확률) |
| sojourn_prob_60d | FLOAT | N | v3.3 확장 포트(60거래일 지속 확률) |
| sojourn_prob_120d | FLOAT | N | v3.3 확장 포트(120거래일 지속 확률) |
| transition_hazard_5d | FLOAT | N | v3.3 확장 포트(5거래일 전환 위험도) |
| transition_hazard_10d | FLOAT | N | v3.3 확장 포트(10거래일 전환 위험도) |
| transition_hazard_20d | FLOAT | N | v3.3 확장 포트(20거래일 전환 위험도) |
| transition_hazard_60d | FLOAT | N | v3.3 확장 포트(60거래일 전환 위험도) |
| transition_hazard_120d | FLOAT | N | v3.3 확장 포트(120거래일 전환 위험도) |
| transition_expected_5d | TEXT | N | v3.3 확장 포트(5거래일 예상 다음 상태, nullable) |
| transition_expected_10d | TEXT | N | v3.3 확장 포트(10거래일 예상 다음 상태, nullable) |
| transition_expected_20d | TEXT | N | v3.3 확장 포트(20거래일 예상 다음 상태, nullable) |
| transition_expected_60d | TEXT | N | v3.3 확장 포트(60거래일 예상 다음 상태, nullable) |
| transition_expected_120d | TEXT | N | v3.3 확장 포트(120거래일 예상 다음 상태, nullable) |
| evidence_axis_macro | TEXT | Y | 매크로/정책 서술 |
| evidence_axis_price | TEXT | Y | 가격 서술 |
| evidence_axis_flow | TEXT | Y | 수급/구조 서술 |
| evidence_axis_sentiment | TEXT | Y | 심리 서술 |
| evidence_quality_score | FLOAT | N | 품질 점수(확장 포트, nullable) |
| evidence_unknown_ratio | FLOAT | Y | 0~1 |
| diag_12slot_coverage | FLOAT | Y | 0~1 |
| diag_12slot_quality | TEXT | Y | `양호`, `경고` |
| horizon_bias_diversity_count | INT | N | 5개 지평 bias의 고유값 개수(1~5), 진단 전용 |
| horizon_bias_diversity_ratio_60d | FLOAT | N | row 시점 기준 과거 60개 row에서 `diversity_count>=2` 비율(0~1) |
| horizon_conf_spread | FLOAT | N | 지평별 confidence 최대-최소 스프레드(0~1) |
| source_run_id | TEXT | Y | 생성 run 식별자 |

저장 경로(SOT):
- `data/strategy/next_step_signal/decision_date=YYYY-MM-DD/*.parquet`
- `data/strategy/next_step_history/year=YYYY/month=MM/*.parquet` (history, precompute 저장본)

History Grain/Key:
- Grain `(trade_date, decision_date_ref)`
- Key `(trade_date, decision_date_ref)`

소비 우선순위:
1. `next_step_history` + `next_step_signal` 저장본
2. 런타임 재계산 fallback (결측 시 fail-open)

운영 메시지 소비 규칙(SIGNAL/PAPER):
- `bias_5d/10d/20d/60d/120d`, `confidence_*`, `transition_hazard_*`, `transition_expected_*`는 snapshot에서 직접 소비한다.
- 실행 기준 bias는 `bias_20d` 단일 경로를 사용한다.
- 운영 메시지 경로에서 상태 기반 즉석 재계산은 금지한다.
- snapshot 결측 시 표시용 fail-open(`UNKNOWN/N/A`)만 허용한다.
- SIGNAL 출력은 `10D 상세 + (5D/20D/60D/120D 요약) + diversity 진단`으로 압축한다.

## 5. Axis×Horizon Evidence Matrix (4x3)
### 책임
- 12셀의 역할을 진단 계층으로 명시한다.

### 제외 범위
- 12셀 전부를 실행 신호로 사용

- 12셀은 독립 실행 신호가 아니라 **evidence diagnostics layer**다.
- 현재 실행/의사결정 핵심 출력은 3-state(long/mid/short)다.
- 12셀은 coverage/unknown_ratio/축별 일관성 점검용 보조 KPI로 사용한다.

## 6. 운영 게이트 규칙(Soft Gate)
소비 규칙(권장 기본값):
- `RISK_ON_BIAS` → tactical 기본 강도 유지
- `NEUTRAL_BIAS` → tactical 완화(슬롯/비중 축소)
- `RISK_OFF_BIAS` → tactical 축소(코어 우선)
- `UNKNOWN` → `NEUTRAL_BIAS`와 동일한 fail-open 처리

우선순위:
1. 하드 게이트(`run_universe`, `risk_gate`) 우선
2. next_step soft gate로 강도만 조절
3. 기본 리밸런싱/배분 규칙 적용

## 7. Hypothesis (v3.2 Extension)
### 책임
- v3.2의 월간 lock + shock override 실험 확장을 기존 계약 내부에서 관리한다.

### 제외 범위
- 신규 계약 파일 생성
- ML 기반 전이예측 튜닝

- v3.2는 **새 계약이 아닌 기존 계약의 확장 가설**이다.
- 기본 정책은 v3.1과 동일한 monthly lock이다.
- override 트리거:
  - `short_signal=PANIC` 2거래일 연속 → `RISK_OFF_BIAS`
  - `mid_regime=RISK_OFF` 3거래일 연속 → `NEUTRAL_BIAS`
- cooldown:
  - override 발동 후 5거래일 동안 재전환 금지
- fail-open:
  - 결측/파싱 실패 시 `UNKNOWN`을 `NEUTRAL_BIAS`로 완화해 사용

## 8. Hypothesis (v3.3 Duration/Transition MVP)
### 책임
- 국면 지속기간/전환시점 추정을 규칙 기반 확률로 추가한다.

### 제외 범위
- ML 학습/튜닝 도입
- v3.2 soft gate 대체

- v3.3은 v3.2 위에 얹는 **확장 가설**이며, 하드게이트는 불변이다.
- 지평은 `5/10/20/60/120 거래일` 고정이다.
- `sojourn_prob_hd`는 상태 지속 확률, `transition_hazard_hd = 1 - sojourn_prob_hd`로 정의한다.
- 소표본/결측 시 nullable 허용(fail-open)하며 기존 bias 흐름을 유지한다.
- `transition_expected_*`는 설명용 필드이며 실행 명령이 아니다.

## 9. Hypothesis (v3.4.2-phase State Machine)
### 책임
- `bias_20d` 실행축에 phase-aware 상태머신을 추가해 회복기 참여/하락기 방어 균형을 보강한다.

### 제외 범위
- 5/10/60/120D bias까지 상태머신으로 확장
- 하드게이트 의미 변경

- baseline:
  - `EXPANSION/LATE_CYCLE/UNKNOWN -> NEUTRAL_BIAS`
  - `RECOVERY -> RISK_ON_BIAS`
  - `SLOWDOWN/RECESSION -> RISK_OFF_BIAS`
- overlay score:
  - `mid_regime=RISK_ON:+2`, `RISK_OFF:-2`
  - `short_signal=RELIEF:+1`, `PANIC:-2`
  - `transition_hazard_10d >= 0.95: -1` (결측은 0, fail-open)
- weekly cadence:
  - 월요일만 판정, 비월요일은 기존 bias 유지
- hysteresis/cooldown:
  - 진입 임계 `>=+2`/`<=-2`, 해제 임계 `<=0`/`>=0`
  - 전환 후 5거래일 재전환 금지(`HOLD_COOLDOWN`)
- hard gate:
  - `run_universe=false` 시 실행 관점 `RISK_OFF_BIAS` 우선

v3.4.2a (체류 완화 실험, 소비자 적용):
- 상태머신 자체는 유지하고, 소비자(backtest/paper preset `v3.4.2a`)에서 soft-only 완화를 적용한다.
- `cooldown_compressed_flag=true` + `bias_state_source=HOLD_COOLDOWN`이면 후보 bias(`bias_candidate_20d`)를 적용할 수 있다.
- `hard_gate_exit_assist_flag=true` + 현재 bias=`RISK_OFF_BIAS`이면 `NEUTRAL_BIAS` 1단 완화를 허용한다.
- 위 보정은 실행 강도 조절용이며 하드 게이트를 대체하지 않는다.

## 10. Invariants
### 책임
- 설명 가능성과 fail-open 동작을 보장한다.

### 제외 범위
- 미래 성과 보장

- 4축 근거 서술 필드는 항상 생성되어야 한다.
- 근거 결측/파싱 실패 시 기본 문구(`영향 근거 없음`)로 대체한다.
- 12셀 진단은 quality 표시로 압축되며, 실행 신호를 직접 대체하지 않는다.
- `evidence_unknown_ratio = 1 - diag_12slot_coverage` 제약을 유지한다.
- `horizon_bias_diversity_ratio_60d`는 row 시점 기준 과거 60개 row만 사용해야 하며 look-ahead를 금지한다.
- 본 출력은 규칙 기반이며, numeric tuning/ML 학습 로직을 포함하지 않는다.
- `bias_20d`는 월요일 판정 + 비월요일 hold + cooldown 제약을 따른다(v3.4.2 확장).
- 하드게이트(`run_universe`)는 phase-aware 상태머신보다 우선한다.

## 11. DoD
### 책임
- 계약 기반 검증 기준을 제공한다.

### 제외 범위
- 백테스트 수익성 검증

- **NSS1**: 입력 필수 컬럼/ENUM 검증
- **NSS2**: bias/confidence 출력 필드 생성 검증
- **NSS3**: 4축 근거 문구 4줄 항상 출력 검증
- **NSS4**: detail 결측 시 fail-open 문구 출력 검증
- **NSS5**: 12셀 진단 지표(`diag_12slot_coverage`, `evidence_unknown_ratio`) 계산 검증
- **NSS6**: 4축 근거 서술 필드가 항상 생성됨을 검증(결측 시 fallback)
- **NSS7**: 12셀 진단 지표(`coverage`, `unknown_ratio`) 일관성 검증
- **NSS8**: Strategy/Paper/Backtest가 동일 snapshot(`next_step_signal`)을 소비함을 검증
- **NSS9**: v3.2 확장 포트(`bias_effective`, `bias_override_flag`, `bias_override_reason`) nullable/하위호환 검증
- **NSS10**: v3.3 확장 포트(`state_age_days`, `sojourn_prob_*`, `transition_hazard_*`, `transition_expected_*`) nullable/하위호환 검증
- **NSS11**: `transition_hazard_hd = 1 - sojourn_prob_hd` 수치 일관성 검증(결측 제외)
- **NSS12**: history key(`trade_date`, `decision_date_ref`) 중복 방지 및 재현성 검증
- **NSS13**: `RECOVERY -> RISK_ON_BIAS` baseline 매핑 및 월요일 판정 규칙 검증
- **NSS14**: cooldown 중 재전환 금지 + `run_universe=false` 하드게이트 우선 검증
- **NSS15**: 신규 진단 컬럼(3개)이 nullable + 하위호환으로 추가됨을 검증(기존 컬럼 변경 금지)
- **NSS16**: 동일 입력 재실행 시 `horizon_bias_diversity_ratio_60d` 결과 동일 + 미래 row 추가 시 과거 row 값 불변을 검증
- **NSS15**: v3.4.2a 확장 포트(`cooldown_compressed_*`, `hard_gate_exit_assist_*`) nullable/하위호환 검증

---

## 변경 이력
| 날짜 | 요약 | 참조 |
| --- | --- | --- |
| 2026-02-25 | v3.3 Duration/Transition MVP 확장 포트(5/10/20d) 추가 | docs/changelog.md |
| 2026-02-25 | v3.1/v3.2 운영 반영: v3.2를 기존 계약의 확장 가설로 추가하고 extension fields(nullable) 정의 | docs/changelog.md |
| 2026-02-25 | 전이예측을 운용 게이트 입력으로 승격(Soft Gate 규칙/공통 snapshot 경로 명시) | docs/changelog.md |
| 2026-02-27 | v3.4.2-phase 상태머신 확장: RECOVERY baseline 상향 + weekly cadence + hysteresis/cooldown + 메타 필드 4종 | docs/changelog.md |
| 2026-02-27 | v3.4.2a 체류 완화 실험 포트 추가: cooldown compression 후보 + hard-gate exit assist 후보 | docs/changelog.md |
| 2026-02-24 | Next Step Signal 계약 신규 추가: 3-state + 4축 근거 + 12셀 진단 KPI 계층 정의 | docs/changelog.md |
