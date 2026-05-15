# Text Strategy Connection — Contract (SOT, Frozen with reusable rules)

Markers: architecture, contract, legacy
Status: legacy

> 🔒 **Frozen with reusable rules — 본 문서 자체는 동결, 일부 규칙은 Phase 3에서 추출 예정**
>
> 본 문서가 정의하는 "텍스트 → Strategy Engine 연결"은 Personal Track 매매 의사결정 영역에 속하므로 **동결 (2026-05-12~ 운영 중단)** 상태입니다. 본 문서의 본문 그대로 사용하지 않습니다.
>
> 단, 다음 규칙은 **Phase 3 Dashboard report 구성 시 차용 대상**입니다 (본 문서에서 발췌해 Observability Track용 `report_layout_contract.md` (가칭)로 분리할 계획):
> - observer-only 원칙 (텍스트 LLM 출력이 매매 / 예측에 직접 연결 금지)
> - fact control (`llm_summary` 내 raw 값 노출 제한)
> - interpretation rendering 규칙 (textual + structured 병행)
>
> 본 문서 본문의 "Strategy Engine 연결" 표현은 **legacy 문맥**으로 읽고, 위 reusable rules만 신규 작업에서 참조합니다.
>
> P22(2026-05-13)에서 legacy `report_context_*` / `report_analyzer` 구현은 `src/pretrend/observability/explainability/`로 사전 추출되었습니다. 이는 Phase 3 전체 report layout 계약 완료가 아니라, 기존 report 렌더링 구현의 위치 이동과 shim 유지 범위입니다.
>
> 참조: [`track_separation.md`](./track_separation.md), [`REFACTOR_2026Q2.md`](../../.agent/REFACTOR_2026Q2.md)

## Document Status
| Item | Value |
| --- | --- |
| Status | **Frozen with reusable rules** — 본문 동결, 위 3개 규칙만 Phase 3 차용 예정. P22에서 구현 일부(`report_context_*`, `report_analyzer`)만 explainability로 사전 추출 |
| Effective Date | 2026-03-04 (재분류: 2026-05-12) |
| Last Updated | 2026-05-13 |
| Change Tracking | docs/changelog.md |

## 1. 문서 목적
- Gold Text feature(rule-based 3종 + LLM 4종)를 Strategy Engine에 연결하는 방식을 고정한다.
- Gate H 충족 후 구현 가능한 수준으로 입력/집계/변환/fail-open/검증 규칙을 명시한다.
- 기존 4축/3-state 구조와 하드게이트 의미를 보존하는 연결 경계를 정의한다.

## 2. 설계 결정 요약

### 2.1 후보 방안 비교
| 방안 | 설명 | 장점 | 리스크 |
| --- | --- | --- | --- |
| A. sentiment 축 보조 입력 | text를 기존 sentiment 축 tie-breaker로 투입 | 축 수 유지, 저장 구조 최소 변경 | sentiment 축 의미 혼합, 축 책임 불명확 |
| B. 5번째 Text 축 | text 전용 axis 신설 후 독립 3-state 산출 | 격리 명확, UNKNOWN 처리 자연스러움 | 12셀→15셀 확장, Gate A/B 영향 큼 |
| C. Overlay Signal | 4축/AHS 이후 별도 `text_overlay_signal` 생성 후 Policy에 보조 적용 | 기존 4축/12셀 보존, AB 비교 용이, fail-open 단순 | overlay 단계/강도 규칙 설계 필요 |

### 2.2 확정안
- **선택 방안: C. Overlay Signal**
- 이유:
  1. 4축 Axis와 AHS(3-state)를 그대로 유지해 Gate A/B 충돌을 최소화한다.
  2. Text 입력 결측 시 `UNKNOWN -> no-op`이 자연스럽다.
  3. 운영 비교 시 `text on/off` AB 실험을 프리셋 수준으로 분리하기 쉽다.
  4. 5번째 축 도입 없이도 Telegram/Policy/Backtest에 단계적으로 연결할 수 있다.

## 3. 연결 위치와 책임

### 3.1 Strategy Engine 연결 위치
Text는 Axis Feature가 아니라 **overlay sidecar signal**로 연결한다.

```text
Gold Macro + Gold EOD + Gold Text
    -> 4 Axis Features
    -> AHS (long/mid/short)
    -> Market Position
    -> Text Overlay Signal
    -> Policy Selection
    -> Universe / Allocation / Sell Advice / Next Step
```

### 3.2 책임 경계
- `market_position`:
  - long/mid/short와 `run_universe`, `risk_gate`의 권위 기준
  - Text로 덮어쓰지 않는다.
- `text_overlay_signal`:
  - Text 기반 보조 방향(`RISK_ON/NEUTRAL/RISK_OFF/UNKNOWN`)만 산출
  - hard gate를 대체하지 않는다.
- `policy_selection`:
  - 기본 정책 결과에 overlay를 soft adjustment로 반영한다.

## 4. 입력 데이터와 Grain

### 4.1 Rule-based Gold
경로:
- `data/gold/text/text_daily_features/year=YYYY/month=MM/*.parquet`

Grain:
- `(trade_date, feature_name)`

사용 feature:
- `macro_hawkish_score`
- `filing_risk_burst`
- `policy_uncertainty_idx`

### 4.2 LLM Gold
경로:
- `data/gold/text/text_llm_features/year=YYYY/month=MM/*.parquet`

Grain:
- `(trade_date, doc_id, source, feature_name)`

사용 feature:
- `llm_tone`
- `llm_topics`
- `llm_tags`
- `llm_summary` (Telegram/설명 전용, 전략 입력 직접 사용 금지)

용어 고정:
- `llm_feature`: `llm_tone`, `llm_topics`, `llm_tags`, `llm_summary`를 포함한 text-only LLM 산출물
- `llm_summary`: `llm_feature` 내부의 문서 요약 필드
- `interpretation_summary`: signal snapshot + text snapshot(+ llm_feature) 결합 해석문

### 4.3 Derived Snapshot
P3-3 구현 시 아래 snapshot을 추가한다.

경로:
- `data/strategy/text_overlay_signal/decision_date=YYYY-MM-DD/*.parquet`

Grain:
- `(trade_date)`

필수 컬럼:
- `trade_date`
- `text_signal_state`
- `text_signal_confidence`
- `text_rule_coverage_ratio`
- `llm_doc_count_5d`
- `text_tone_mean_5d`
- `text_top_topics_json`
- `text_top_tags_json`
- `text_latest_summary`
- `text_overlay_reason`
- `source_run_id`

## 5. 집계 규칙

### 5.1 집계 원칙
- Text overlay는 **trade_date 단위**로만 계산한다.
- `llm_summary`는 overlay 계산에서 제외하고 Telegram 설명에만 사용한다.
- Lookback은 거래일 기준으로 고정한다.
- `interpretation_summary`는 저장 레이어 기본 산출물이 아니며, Telegram/리포트 단계에서만 생성한다.

### 5.2 Rule-based feature 집계
- `macro_hawkish_score`, `filing_risk_burst`, `policy_uncertainty_idx`는 해당 `trade_date` 값 그대로 사용한다.
- 세 feature의 `coverage_ratio` 중앙값을 `rule_coverage_ratio`로 사용한다.

### 5.3 LLM feature 집계
- lookback window:
  - `5 거래일` rolling, 현재 `trade_date` 포함
- `llm_tone_mean_5d`:
  - `llm_tone`의 confidence-weighted mean
- `llm_topics`:
  - 최근 5거래일 문서의 topic item 빈도 카운트
  - 상위 3개를 `top_topics_json`으로 저장
- `llm_tags`:
  - 최근 5거래일 문서의 tag item 빈도 카운트
  - 상위 5개를 `top_tags_json`으로 저장
- `llm_summary`:
  - overlay 계산에는 사용하지 않음
  - Telegram/리포트의 `interpretation_summary` 작성 시 참고 가능한 text-only 요약 필드
  - 최신 1건만 선택 사용 가능

### 5.4 비거래일 문서 처리
- `text_observability_contract.md §4`의 이벤트 정렬 규칙을 따른다.
- 주말/휴일 문서는 이미 정렬된 `trade_date` 기준으로 집계한다.

## 6. Text Signal -> 3-State 변환 규칙

### 6.1 Evidence score
`text_signal_score`는 rule-based와 LLM evidence의 합으로 계산한다.

#### Rule-based evidence
- `macro_hawkish_score >= 0.60` -> `-1.0`
- `macro_hawkish_score <= 0.35` -> `+1.0`
- `filing_risk_burst >= 2.0` -> `-1.0`
- `policy_uncertainty_idx >= 0.70` -> `-1.0`
- `policy_uncertainty_idx <= 0.30` -> `+0.5`

#### LLM tone evidence
- `llm_tone_mean_5d >= 0.25` -> `-1.0`  (`hawkish`)
- `llm_tone_mean_5d <= -0.25` -> `+1.0` (`dovish`)

#### LLM tag evidence
- risk-off tag:
  - `hike`, `qt`, `guidance_raise`, `downgrade`, `default`, `spread_widening`, `liquidity_crunch`, `bank_run`, `crash`, `correction`, `capitulation`, `volatility_spike`, `risk_off`
- risk-on tag:
  - `cut`, `qe`, `guidance_cut`, `fiscal_stimulus`, `risk_on`

규칙:
- 최근 5거래일 상위 tag에 risk-off tag가 1개 이상 있으면 `-1.0`
- 최근 5거래일 상위 tag에 risk-on tag가 1개 이상 있으면 `+1.0`
- 양쪽이 동시에 있으면 상쇄(`0.0`)

### 6.2 3-state 변환
- `text_signal_score >= +1.5` -> `RISK_ON`
- `text_signal_score <= -1.5` -> `RISK_OFF`
- 그 외 -> `NEUTRAL`

### 6.3 Confidence
- `text_confidence = min(0.95, 0.5 * rule_coverage_ratio + 0.5 * min(1.0, llm_doc_count_5d / 3))`
- LLM 문서가 없어도 rule-based만으로 계산 가능하다.

## 7. Strategy 적용 규칙

### 7.1 적용 원칙
- `text_signal`은 **soft overlay only**다.
- `run_universe`, `risk_gate`, long/mid/short는 Text로 덮어쓰지 않는다.

### 7.2 정책 적용
기본 정책 결과에 대해 아래를 적용한다.

| text_signal | 적용 |
| --- | --- |
| `RISK_ON` | `target_ratio` 1 step 상향 (`+0.05`) |
| `NEUTRAL` | 변경 없음 |
| `RISK_OFF` | `target_ratio` 1 step 하향 (`-0.05`) |
| `UNKNOWN` | 변경 없음 |

추가 규칙:
- hard gate(`run_universe=false`)이면 `RISK_ON` overlay는 무시한다.
- `risk_gate=false`이면 기존 runner 계약을 우선한다.
- overlay는 정책 step 1회만 허용하며, base policy를 뒤집는 강제 override가 아니다.

## 8. Fail-open 규칙

| 시나리오 | 결과 |
| --- | --- |
| Gold Text 파티션 전체 없음 | `text_signal=UNKNOWN`, no-op |
| LLM feature만 없음 | rule-based 3종만으로 계산 |
| rule-based coverage 중앙값 `< 0.5` | `text_signal=UNKNOWN` |
| `llm_topics`/`llm_tags` JSON 파싱 실패 | 해당 문서만 제외 후 계속 |
| `llm_doc_count_5d = 0` | tone/tag evidence 0, rule-based만 사용 |

원칙:
- Text 부재는 기존 4축/3-state 동작을 깨지 않는다.
- `UNKNOWN`은 overlay no-op과 동일하게 취급한다.
- `interpretation_summary`는 observer-only 출력이며 전략 입력으로 승격하지 않는다.

## 9. AB Backtest 비교 프로토콜

### 9.1 비교군
- A 그룹: 기존 전략 (`v2` 또는 당시 운영 preset)
- B 그룹: 동일 preset + `text_overlay_signal`

### 9.2 비교 지표
- `XIRR`
- `MDD`
- `Sharpe`
- `Calmar`
- `DCA Return`

### 9.3 비교 구간
- 전체: `2006-01-03 ~ 2024-06-03`
- Walk-forward: 기존 9구간

### 9.4 채택 기준
- `Sharpe` 개선 `>= 0.05`, 또는
- `MDD` 개선이 있고 `XIRR` 훼손이 `<= 0.30%p`

기준 미달 시:
- observer-only 유지
- 계약은 유지하되 구현 보류 가능

## 10. 구현 전제 / 운영 조건
- 구현 전제:
  1. `text_pipeline_dag` 정상 운영 확인
  2. 전체 백필 완료(2006~2026) 및 Gold/Gold LLM 생성 검증
  3. P3-2 설계 확정
  4. AB 비교 프로토콜 확정
- 운영 원칙:
  - Text overlay는 observer->soft overlay 승격이지만 hard gate를 대체하지 않는다.
  - 운영 메시지와 backtest는 동일 snapshot(`text_overlay_signal`)을 권위 입력으로 사용한다.

## 11. 구현 결과 / 승격 판정 (2026-03-04)

### 11.1 구현 상태
- `P3-3` 구현 완료:
  - `load_gold_text()` 추가
  - `text_overlay_signal` snapshot 생성
  - `policy_selection`에 text overlay 컬럼 병합
  - Telegram 시장 근거 섹션에 text evidence 표시
  - backtest preset `v2_text` 추가

### 11.2 AB 1차 비교 결과
비교 구간:
- `2006-01-03 ~ 2024-06-03`

| Metric | v2 | v2_text | Delta |
| --- | --- | --- | --- |
| XIRR | `+7.74%` | `+7.33%` | `-0.41%p` |
| MDD | `-15.65%` | `-21.92%` | `-6.27%p` |
| Sharpe | `1.69` | `1.64` | `-0.05` 미만 |
| Trade Count | `5093` | `5180` | `+87` |

### 11.3 P3-3 판정
- 구현은 **완료**
- 운영 승격은 **보류**

근거:
- `§9.4` 채택 기준 중 `MDD 악화 > 3%p` 조건에 걸린다.
- 따라서 현 시점 Text overlay는 `observer-only`를 유지하고, 운영 preset 승격은 하지 않는다.

### 11.4 P3-3b 재설계 실험 (2026-03-04)

P3-3a 진단에서 `RISK_ON` overlay가 MDD 악화의 주범임을 확인한 후, 최소 재설계 실험군 2개를 추가 비교했다.

| preset | XIRR | MDD | Sharpe | v2 대비 |
| --- | --- | --- | --- | --- |
| `v2` (baseline) | `+7.74%` | `-15.65%` | `1.691` | — |
| `v2_text` (P3-3) | `+7.33%` | `-21.92%` | `1.644` | 악화 |
| `v2_text_riskoff` | `+7.71%` | `-15.65%` | `1.690` | ≈0 |
| `v2_text_riskoff_guarded` | `+7.74%` | `-15.65%` | `1.691` | ≈0 |

- `v2_text_riskoff`: `RISK_ON` 제거, `RISK_OFF=-0.05`
- `v2_text_riskoff_guarded`: `RISK_ON` 제거, `RISK_OFF=-0.025`, `confidence>=0.7`

### 11.5 최종 판정: 영구 observer-only

- **결론**: 현재 text signal은 alpha를 보유하지 않는다.
  - `RISK_ON`을 켜면 MDD가 6%p 악화된다.
  - `RISK_OFF`만 남기면 사실상 no-op이다 (XIRR/Sharpe delta ≈ 0).
  - 고신뢰 필터(`confidence>=0.7`)까지 적용하면 매매 변경이 5건에 불과하다.
- **판정**: Text overlay는 **영구 observer-only**로 확정한다.
- **유지 범위**:
  - `text_pipeline_dag`: 유지 (Ollama 로컬, 비용 $0)
  - `text_overlay_signal` snapshot 생성: 유지 (observability)
  - Telegram 시장 근거 섹션 text evidence 표시: 유지
- **제거 범위**:
  - Backtest preset (`v2_text`, `v2_text_riskoff`, `v2_text_riskoff_guarded`): 제거
  - `compute_allocation_v2_text()`: 제거
- **재검토 조건**: 차별화된 신호원(실시간 뉴스, 컨센서스 서프라이즈 등)이 추가될 경우 재실험

## 12. Change History
| Date | Summary |
| --- | --- |
| 2026-03-04 | P3-2 설계 초안 작성. Overlay Signal 방안 확정, 집계/3-state/fail-open/AB 비교 프로토콜 고정 |
| 2026-03-04 | P3-3 구현 착수 기준으로 snapshot 컬럼명을 `text_signal_state/*` 계열로 확정하고 Gate H 시간조건을 제거 |
| 2026-03-04 | P3-3 구현/AB 비교 완료. `v2_text` 운영 승격 보류(observer-only 유지) |
| 2026-03-04 | P3-3b 재설계 실험 완료. text signal alpha 부재 확인. 영구 observer-only 확정, backtest preset 제거 |
