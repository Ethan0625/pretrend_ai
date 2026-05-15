v2026.02.24

# Invariants Registry

## 1) 핵심 불변식 표

| ID | Invariant | 적용 범위 | 위반 신호 | Source |
| --- | --- | --- | --- | --- |
| INV-PIT-01 | `selected_release_date < trade_date` | Gold Macro / Strategy 입력 | 미래 정보 조인, look-ahead | `docs/architecture/gold_design_contract.md §9`, `docs/data_requirements.md (#8-데이터-품질불변식-요구사항)` |
| INV-IDEMP-01 | `_tmp_run` 기록 후 atomic rename, 동일 파티션 overwrite | Calendar/Strategy snapshot writer | append 누적, 파티션 중복 파일 | `docs/architecture/calendar_design_contract.md (#5-idempotent-write-strategy)`, `docs/strategy_engine_design.md (#section-e--snapshot-storage)` |
| INV-FAILOPEN-01 | 결측 시 fail-open + `UNKNOWN` 허용 + 스키마 유지 | Axis/Horizon, Text, Strategy 출력 | 결측 시 crash/null schema 변경 | `docs/strategy_engine_design.md (#section-a--one-page-summary)`, `docs/architecture/text_observability_contract.md (#6-fail-open-정책)` |
| INV-RO-01 | Strategy는 Gold read-only consumer | Strategy Engine | 상위 레이어 데이터 재가공 저장 | `docs/strategy_engine_design.md (#section-a--one-page-summary)` |
| INV-UNI-01 | Universe-ETF와 Universe-Stock(U0~U3) 개념 분리 | Universe/로드맵 해석 | ETF 실행 로직과 U0~U3 혼재 | `docs/architecture/universe_contract.md (#2-scope--non-goals)`, `docs/milestones.md (#m2-universe-stock-pipelineu0u3-구현-68주)` |
| INV-ENUM-01 | 상태/액션은 계약 ENUM 외 값 금지 | Long/Mid/Short/Composer/Allocation | 임의 문자열 상태값 | `docs/architecture/market_structure_long_contract.md (#6-invariants)`, `docs/architecture/market_structure_mid_contract.md (#6-invariants)`, `docs/architecture/market_structure_short_contract.md (#6-invariants)`, `docs/architecture/allocation_engine_contract.md (#7-invariants)` |
| INV-TEXT-OBS-01 | Text LLM feature는 영구 observer-only이며 실행 입력으로 직접 소비하지 않는다 | Text / Strategy / Paper / Backtest | LLM feature가 실행 입력으로 직접 소비됨 | `docs/architecture/text_observability_contract.md (#14-운영-경계-정책-v1)`, `docs/strategy_engine_design.md (#telegram-phase-15)` |

## 2) 모듈별 위반 감지 체크리스트

### A. Gold / Calendar
- [ ] `release_date`/`selected_release_date`가 `trade_date`보다 이전인가?
- [ ] 파티션 쓰기가 overwrite 규칙을 유지하는가?
- [ ] timestamp/date 정규화가 계약과 일치하는가?

Source:
- `docs/architecture/gold_design_contract.md (#10-6-pit-rules-macro-feature-v1)`
- `docs/architecture/calendar_design_contract.md (#6-normalization-rules)`

### B. Market Structure (Long/Mid/Short/Composer)
- [ ] 출력 grain/key가 `(trade_date)`로 일관적인가?
- [ ] 결측 시 UNKNOWN 경로가 유지되는가?
- [ ] Composer 출력 필드(`run_universe`, `risk_gate`)가 누락되지 않았는가?

Source:
- `docs/architecture/market_structure_long_contract.md (#5-grainkey-trade_date-기준)`
- `docs/architecture/market_structure_mid_contract.md (#5-grainkey)`
- `docs/architecture/market_structure_short_contract.md (#5-grainkey)`
- `docs/architecture/market_structure_composer_contract.md (#4-outputs-필수)`

### C. Universe-ETF
- [ ] Execution Universe 계약 범위를 벗어나지 않는가?
- [ ] phase eligible pool / mid_regime Top-N 규칙이 유지되는가?
- [ ] CORE 예외와 fail-open(UNKNOWN) 처리 일관성이 있는가?

Source:
- `docs/architecture/universe_contract.md (#6-불변식)`

### D. Allocation
- [ ] mode(v0/v1/v2)별 risk_gate/run_universe 규칙이 계약과 일치하는가?
- [ ] next ratio가 [0,1] 범위를 벗어나지 않는가?
- [ ] step_size/adjustment_limit 규칙이 유지되는가?

Source:
- `docs/architecture/allocation_engine_contract.md (#4-rules)`
- `docs/architecture/allocation_engine_contract.md (#7-invariants)`

### E. Text Observability
- [ ] Bronze 멱등키 `(source, source_doc_id)`가 보장되는가?
- [ ] 텍스트 결측 시에도 Strategy 핵심이 fail-open으로 동작하는가?
- [ ] Gold LLM 산출물이 observer-only 경계를 넘지 않는가?
- [ ] SEC adapter가 `recent + files`를 순회하되 공개 인터페이스를 유지하는가?

Source:
- `docs/architecture/text_observability_contract.md (#2-1-bronze-layer--bronzetext_raw)`
- `docs/architecture/text_observability_contract.md (#6-fail-open-정책)`
- `docs/architecture/text_observability_contract.md (#14-운영-경계-정책-v1)`

## 3) 빠른 정합성 점검 명령 (문서용)
```bash
# 금지 문자열/용어 혼선 점검 예시
grep -RIn "selected_release_date < trade_date\|fail-open\|Universe-ETF\|Universe-Stock" docs .agent

# Strategy snapshot 저장 규칙 확인 포인트
grep -RIn "_tmp_run\|atomic\|overwrite\|decision_date" docs/strategy_engine_design.md docs/architecture/*.md
```
