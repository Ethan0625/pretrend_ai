# Changelog

## v2026.02.22c — Mid Engine v1.1 spread 버그 수정 + Short Engine 보강

### fix(strategy_engine): Mid Engine breadth 부호 반전 버그 수정 (v1.1)
- 원인: `breadth_iwm_spy_ratio = iwm_ret_20d / spy_ret_20d`는 `spy_ret_20d < 0` 구간에서 부호/해석 반전 발생
  - 예: `SPY=-5%`, `IWM=-3%` → ratio=0.6 (기존 로직은 `RISK_OFF` 오판정)
- 수정:
  - `flow_structure.py`: `_compute_breadth_ratio()` → `_compute_breadth_spread()`
  - 계산식: `breadth_iwm_spy_spread = iwm_ret_20d - spy_ret_20d`
  - `schema.py`: `FLOW_OPTIONAL_COLUMNS` 컬럼명 갱신
  - `mid_engine.py`: ratio 임계값(`>1.0/<0.8`) 제거, spread 임계값(`>+0.005/<-0.005`) 적용
- 효과:
  - spread 표준편차(`0.028`) 기준 약 `0.18σ` 노이즈 필터 구간 확보
  - `NEUTRAL` 구간 약 `15.3%` 확보

### feat(strategy_engine): Short Engine secondary PANIC 신호 확장
- `short_engine.py`에 `smallcap_stress` 신호 추가:
  - 조건: `iwm_spy_vol_spread > 0.005`
  - 의미: 소형주 변동성 스트레스 감지
- secondary PANIC 확인 규칙:
  - 기존 3신호(`vol_spike`, `wide_intraday`, `flight_to_safety`)
  - 변경 4신호 + `2개 이상` 충족 시 PANIC 확인

### test(strategy_engine): Mid/Short 회귀 테스트 추가
- `tests/pipeline/strategy_engine/test_mid_engine.py`
  - MM4 fixture: ratio → spread 값 반영
  - MM5 신규 3건: ratio 부호 반전 케이스를 spread 방식으로 교정 검증
- `tests/pipeline/strategy_engine/test_short_engine.py`
  - MSH7 신규 2건: `smallcap_stress` 경계값(`>0.005`, `<=0.005`) 검증
- `tests/pipeline/strategy_engine/test_axis_features.py`
  - breadth 컬럼/메서드명 변경 반영(2곳)

### 성과 비교 (v2 preset, 2006-01 ~ 2024-06, DCA $300/월)

| 엔진 | XIRR | MDD | Sharpe |
| --- | --- | --- | --- |
| v0 | +8.00% | -15.71% | 1.69 |
| v1 | +6.94% | -17.74% | 1.65 |
| v1.1 | +7.25% | -15.65% | 1.68 |

- v1.1 결과: `XIRR +0.31%p` 회복, `MDD -15.65%`로 v0 대비 소폭 개선, Sharpe 1.68
- 전체 테스트: `389 passed, 1 skipped`

---

## v2026.02.22b — Strategy Engine Allocation v1/v2 업그레이드

### feat(strategy_engine): Allocation v1/v2 모드 추가

`allocation/engine.py`:
- `_ALLOCATION_V1_MAP`: `long_phase` → 목표 비율 (EXPANSION=0.60, RECESSION=0.10, SLOWDOWN=0.20, UNKNOWN=0.40 등)
- `_ALLOCATION_V2_MAP`: `(long_phase, mid_regime)` → 목표 비율 (6×4 = 24 셀, 4단계 fallback)
- `_apply_delta()`: v1/v2 공통 gradual movement 헬퍼. PANIC(risk_gate=False)이어도 INCREASE 허용(저점매수)
- `_compute_allocation_v1()`, `_compute_allocation_v2()`: phase/regime 기반 target-seeking
- `build_allocation(allocation_mode="v0")`: `"v0"|"v1"|"v2"` dispatch 지원. 미등록 mode → v0 fallback

`strategy_job.py`:
- `StrategyJobRunner(allocation_mode="v0")` 필드 추가
- CLI `--allocation-mode v0|v1|v2` 인자 추가

**v0 vs v1/v2 PANIC 동작 차이:**
- v0: risk_gate=False → INCREASE 차단 (범위유지 보수적)
- v1/v2: risk_gate=False → INCREASE 허용 (target-seeking 저점매수)

### test(strategy_engine): Allocation v1/v2 테스트 추가 (+19건)
- `TestAllocationV1`: EXPANSION(+), RECESSION(-), SLOWDOWN(-), at_target, run_universe gate, risk_gate PANIC, unknown fallback, adj_limit 경계
- `TestAllocationV2`: LATE_CYCLE+RISK_OFF(-), EXPANSION+RISK_ON(+), RECESSION+RISK_OFF(-), UNKNOWN+UNKNOWN(HOLD), fallback chain, PANIC/run_universe gate
- `TestAllocationModeDispatch`: default=v0, unknown mode fallback
- 전체 테스트: `373 passed, 1 skipped`

### docs(strategy_engine): K4/K5/K7/K9 갱신
- K4: 373 passed, SE 소계 140
- K5: Allocation v1/v2 수정 이력 추가
- K7: v1/v2 CLI 예시 추가
- K9: SE v1/v2 지원 완료 표 갱신

---

## v2026.02.22 — 문서 정합성 수정 및 Backtest Sell 실행 로직 안정화

### fix(docs): strategy_engine_design.md CORE 정의 수정 (TLT→SCHD)
- `§D1-1` CORE 목록을 `(SPY, TLT, IAU)` → `(SPY, SCHD, IAU)`로 정정
  - `TLT`는 BOND tactical로 이동 — RECESSION/SLOWDOWN 구간에서 RS 기반 자동 선정
  - `SCHD`는 2011-10-24 이전 데이터 없음 → Universe Engine이 `gold_eod` 미존재 심볼을 자동 제외하므로 별도 처리 불필요
- `§D1-1` 관련 `docs/architecture/universe_contract.md` CORE 정의 동기화

### feat(docs): K8 성과 지표 DCA 기준으로 교체 (v2026.02.22 기준)
- 기존 CAGR/MDD/Sharpe 단순 테이블 → DCA 총수익/XIRR/MDD/Sharpe/Calmar 확장 테이블

| 지표 | v0 | v1 | v2 | SPY B&H |
| --- | --- | --- | --- | --- |
| DCA 총수익 | +46.9% | +60.0% | +122.9% | - |
| XIRR (DCA) | +3.97% | +4.81% | +8.00% | +10.13% |
| MDD | -11.18% | -20.19% | -15.71% | -55.19% |
| Sharpe | 1.76 | 1.60 | 1.69 | - |
| Calmar | 2.53 | 1.43 | 1.99 | - |

### feat(docs): K9 Backtest Allocation 아키텍처 vs Strategy Engine 신규 섹션
- Allocation 버전 차이 명시 (SE=RC_V0_DEFAULT 단일 / Backtest=v0/v1/v2 프리셋)
- Sell Advisor advisory 역할 명시:
  - `sell_budget_ratio` / `sell_priority_list`는 권고 출력
  - 실제 매도 실행은 `_execute_sell_tranche()`의 target_weights 기반 로직
  - Sell Planner → Sell Advisor 명칭 변경 완료 (P3 이행)

### fix(backtest): Sell 실행 전략 확정 — target_weights 기반 (phase-based 실험 후 복원)
- PHASE_SELL_MODE (phase별 rs_priority/비례 혼합) 실험 후 제거
  - Full rs_priority: v0 +15.4%, v2 +102.6%
  - Phase-based 혼합: v0 +15.4~15.8%, v2 +96.2~97.8%
  - Pure 비례: v0 +15.8%, v2 +92.8%
  - **target_weights (복원)**: v0 +46.9%, v1 +60.0%, v2 +122.9%
- target_weights 방식이 단순 비례/rs_priority 대비 v2 기준 +20~30%p 우수
  - 이유: 매도와 동시에 내부 비중 정상화 (과매수 포지션 선제 정리)
- `config.py` PHASE_SELL_MODE 상수 제거, `runner.py` StagedSellPlan 단순화

### K4 테스트 현황 갱신
- 전체: `305 passed` → `354 passed, 1 skipped`
- Strategy Engine: 121건 / Backtest Engine: 62건

---

## v2026.02.21b — Backtest Runner 실행 규칙 정합화 및 리포트 지표 확장

### fix(backtest): 실행 스케줄/리스크 게이트/유니버스 참조 경로 정합화
- `runner.py` 실행 규칙을 주간 단위로 명시하고 코드/동작을 정합화:
  - 월요일: 전 거래일(T-1) 신호 평가
  - 화요일: `INCREASE` 실행(현금 배포 매수)
  - 금요일: `DECREASE` 단계 매도 실행(`50% → 30% → 20%`, 3주)
- `risk_gate=false(PANIC)` 처리 변경:
  - `INCREASE`는 허용(저점 매수)
  - `DECREASE` 신규 생성 차단 + 진행 중 트랜치 동결
- `what_to_hold` snapshot 직접 의존 대신 `gold_eod`(`ret_20d`, `asset_group`) 기반 inline Universe 계산 경로 유지
- 월 첫 거래일 DCA 자금 투입(`monthly_addition`) 및 벤치마크(SPY) 동일 규칙 적용

### feat(backtest): DCA/XIRR 및 최종 포지션 리포트 확장
- `BacktestConfig`/`BacktestPreset`에 `monthly_addition` 필드 추가
- `metrics.py`에 `compute_xirr()` 추가, `compute_metrics()`에 아래 지표 확장:
  - `dca_return`, `xirr`, `total_capital_injected`
- `BacktestResult` 확장:
  - `total_capital_injected`, `cash_flows`, `bm_cash_flows`
  - `final_positions`, `final_benchmark_positions`
- `report.py` 출력 확장:
  - 전략 vs SPY 병렬 성과표
  - DCA/IRR 지표 표기
  - 최종 보유 포지션 테이블 출력

### fix(backtest): 보조 로직 정합화
- `rebalancer.py` 전술 비중 차감 로직 개선:
  - 단일 core 차감 방식 → core 전체 비례 차감(기존 core 비율 유지)
  - 최소 core 비중 제약(`0.05`) 기반 슬롯 축소 처리
- pre-SCHD 기본 구성 변경:
  - `SPY 80 / IAU 20` → `DVY 25 / VIG 25 / SPY 30 / IAU 20`
  - SCHD 출시 후 DVY/VIG→SCHD 단계 전환 로직 반영
- `portfolio.py`:
  - `add_cash()` 추가(DCA 투입)
  - snapshot에 `avg_cost` 포함

### 테스트 영향
- backtest 관련 테스트 기대값/시나리오를 신규 규칙에 맞게 갱신
  - `tests/pipeline/backtest/test_runner.py`
  - `tests/pipeline/backtest/test_rebalancer.py`
  - `tests/pipeline/backtest/test_allocation.py`

---

## v2026.02.21 — Universe Engine v1 + Strategy/Backtest Universe 경로 수정

### feat(universe): Phase-based eligible pool + mid_regime Top-N
- Universe Engine v1 구현: 단순 `is_candidate=True` 방식에서 `phase eligible pool + mid_regime Top-N` 구조로 전환
- Phase 제외 규칙:
  - `RECESSION`: `{USO, UNG}`
  - `SLOWDOWN`: `{UNG}`
  - `LATE_CYCLE`: `{}` (전체 허용, live RS 위임)
  - `EXPANSION`: `{UNG}`
  - `RECOVERY`: `{USO, UNG, XLE}`
  - `UNKNOWN`: `{}` (fail-open)
- `mid_regime` Top-N:
  - `RISK_OFF=5`, `NEUTRAL=7`, `RISK_ON=9`, `UNKNOWN=7`
- 상대강도 정의: `relative_strength = ret_20d(symbol) - ret_20d(SPY)`
- CORE(`SPY`, `TLT`, `IAU`)는 phase 필터 및 Top-N과 무관하게 항상 `is_candidate=true`
- 테스트: `tests/pipeline/strategy_engine/test_universe.py` UV1~UV6, 총 15건 통과

### fix(strategy/backtest): what_to_hold 누적 버그 및 snapshot 의존 경로 수정
- `strategy_job.py` 수정:
  - 기존 `build_universe(df_ps, df_gold_eod)` 호출이 전 기간 `policy_selection`을 전달해 `what_to_hold` snapshot 누적 발생
  - 수정: `decision_date` 하루치(`df_ps_today`)만 `build_universe` 입력으로 전달
- `backtest/runner.py` 수정:
  - 누적 가능성이 있는 `what_to_hold` snapshot 로드 제거
  - `_load_gold_eod_features()` 추가
  - `_compute_universe_inline()` 추가
  - 리밸런싱 시점별 inline Universe 계산으로 전환
- 성과(2006-01-03 ~ 2024-06-03, `z_threshold=0.3`):

| 지표 | v0 | v1 | v2 | SPY B&H |
| --- | --- | --- | --- | --- |
| CAGR | +5.98% | +3.51% | +3.99% | +10.13% |
| MDD | -28.51% | -26.51% | -19.75% | -55.19% |
| Sharpe | 0.68 | 0.51 | 0.62 | - |

- 테스트: 전체 `346 passed, 1 skipped`

---

## v2026.02.20 — Text Data Pipeline 설계 확정 + Universe 이원화 문서 정합화

### 변경 요약
- **Text 수집 전략 v1 확정**: Tiered Hybrid ($0 시작, T+1 배치). 소스: SEC EDGAR + Fed/FOMC (FMP News는 유료 전환 보류)
- **text_observability_contract.md 보강**: Bronze 멱등키 `(source, source_doc_id)` + `source_doc_id`/`ingested_at`/`raw_payload_hash` 신규 필드, Silver LLM → Reserved(v1+) + v0 필수 필드(asset_scope/quality_flags/clean_text), Gold long 포맷 전환 + 초기 3개 feature (`macro_hawkish_score`/`filing_risk_burst`/`policy_uncertainty_idx`), Fail-open 정책 + 품질 KPI 섹션 추가
- **strategy_engine_design.md SECTION J 업데이트**: 텍스트 보조 feature 역할 명시, Gold long format 스키마 확정, fail-open 원칙
- **data_ingest_datasources.md 보강**: 텍스트 소스 섹션 신규 추가 (SEC EDGAR, Fed/FOMC, FMP 보류)
- **Universe 이원화 문서 정합화 (Codex 완료)**: `universe_design.md` → `Universe-ETF Design`으로 개명 + `Universe-Stock(U0~U3)` 참조 명시, `milestones.md`/`data_ingest_datasources.md`/`README.md` 전반 용어 통일

### 소스 접근 가능 여부 확인 결과
| 소스 | 상태 | 비고 |
| --- | --- | --- |
| SEC EDGAR (data.sec.gov) | ✅ 사용 가능 | User-Agent 필수, 10 req/sec 상한 |
| Fed/FOMC RSS | ✅ 사용 가능 | `federalreserve.gov/feeds/press_all.xml` 실시간 확인 |
| FMP News | ❌ 무료 불가 | 무료 플랜 뉴스 미지원. Starter $22/월 이상 필요 |

---

## v2026.02.21 — Walk-Forward 분석 + Phase 분포 모니터링 + threshold 가변화 설계

### 변경 요약
- **Walk-Forward 기간별 성과 분석** (`walk_forward.py`) 신규: threshold=0.3 운영 안정성 검증 도구
- **Phase 분포 모니터링** (`compute_phase_distribution()`, `print_phase_distribution()`) 추가: 연/반기/분기별 LATE_CYCLE%, S+R% 추적
- **`_utils.py`** 신규: `load_strategy_snapshot()` 공통 유틸 (runner.py + walk_forward.py 공유)
- **가변 threshold 설계 문서** (`docs/architecture/threshold_policy_v2.md`): 이산 상태 {0.0, 0.3}, 트리거, cooldown=6개월 명시
- **Universe 용어 이원화 기준 도입**: `Universe-ETF(Execution Universe)` / `Universe-Stock(U0~U3)`로 구분
- **과거 changelog 원문 보존 원칙**: 과거 섹션은 용어 치환 없이 유지, 최신 섹션에서 해석 기준만 명시
- **문서 정합화**: README 실행/검증 섹션, Strategy Engine SOT 구현 현황, Long contract 입력 계약(indicator_id N/권장) 동기화
- 신규 테스트 13건 추가, 전체 `305 passed, 1 skipped`

### Universe 용어 기준 (문서 해석 규칙)
- `Universe-ETF (Execution Universe)`: 현재 Strategy Engine에서 실제 운용 중인 ETF 후보 선별 모듈
- `Universe-Stock (Research Universe, U0~U3)`: Macro→Theme→Stock 로드맵 파이프라인
- 과거 changelog 항목의 `Universe` 표현은 작성 시점의 원문으로 보존한다.

### Walk-Forward (`pipeline/backtest/walk_forward.py`)

**목적**: 동일 snapshot(2024-06-03) 기반 기간별 성과 일관성 검증.

> **주의**: 동일 snapshot 재사용으로 look-ahead bias가 존재할 수 있음.

**주요 구성**:
```
WalkForwardConfig: preset, windows, window_years=4, step_years=2, full_start, full_end
WalkForwardRunner.run() → DataFrame (고정 스키마)
  컬럼: window_start, window_end, cagr, total_return, max_drawdown,
        sharpe_ratio, benchmark_cagr, excess_cagr, preset, generated_at
```

**저장 산출물** (`report.py:save_walk_forward()`):
- `data/backtest/reports/walk_forward/walk_forward_{preset}_{ts}.parquet`
- `data/backtest/reports/walk_forward/walk_forward_{preset}_{ts}_summary.json`

**CLI**:
```bash
python -m pretrend.pipeline.backtest.walk_forward \
    --preset v2 --window-years 4 --step-years 2 [--save]
```

### Phase 분포 모니터링 (`metrics.py`, `report.py`)

```python
compute_phase_distribution(policy_df, group_by="year"|"half"|"quarter")
# 반환: period, LATE_CYCLE_pct, SLOWDOWN_pct, RECESSION_pct,
#       EXPANSION_pct, RECOVERY_pct, UNKNOWN_pct, SR_combined_pct

print_phase_distribution(policy_df, group_by="year")
# 경고 기준: LATE_CYCLE% > 60% (L), S+R% > 50% (H), S+R% < 15% (l)
```

### `_utils.py` 공통 유틸화

`runner.py:_load_snapshot()` → `pipeline/backtest/_utils.py:load_strategy_snapshot()` 추출.
승격 정책: 여러 pipeline에서 재사용 확인 시 `src/pretrend/utils/`로 이전.

### 가변 threshold 설계 (`docs/architecture/threshold_policy_v2.md`)

- threshold ∈ {0.0, 0.3} 이산 전환
- 트리거: rolling 12개월 LATE_CYCLE% > 60% → 0.3→0.0 / S+R% < 15% → 0.0→0.3
- Cooldown: 최소 6개월
- **코드 미구현** — 운영 검증 후 필요 조건 충족 시 착수

### Walk-Forward 실증 검증 결과 (v2, 4년 창, 2년 슬라이드, 2006~2024.6)

> look-ahead bias 존재 (동일 snapshot 재사용). 목적: 국면별 전략 행동 일관성 파악.

**9개 창 성과**:
| Window | CAGR | Total | MDD | Sharpe | Exc.CAGR |
|--------|------|-------|-----|--------|----------|
| 2006-01 ~ 2010-01 | +2.05% | +8.4% | -15.79% | 0.34 | +3.17% |
| 2008-01 ~ 2012-01 | +0.76% | +3.1% | -15.39% | 0.13 | +1.77% |
| 2010-01 ~ 2014-01 | +5.63% | +24.5% | -9.50% | 0.76 | -9.43% |
| 2012-01 ~ 2016-01 | +4.92% | +21.1% | -4.96% | 0.90 | -9.89% |
| 2014-01 ~ 2018-01 | +5.14% | +22.2% | -6.01% | 1.08 | -7.38% |
| 2016-01 ~ 2020-01 | +5.32% | +23.0% | -6.36% | 1.13 | -9.45% |
| 2018-01 ~ 2022-01 | +6.41% | +28.2% | -12.44% | 0.88 | -10.89% |
| 2020-01 ~ 2024-01 | +4.18% | +17.8% | -17.65% | 0.49 | -7.37% |
| 2022-01 ~ 2024-06 | +1.49% | +3.6% | -8.66% | 0.28 | -4.22% |
| **평균** | **+3.99%** | **+16.9%** | **-10.75%** | **0.67** | **-5.96%** |

**해석**:
- **최적 구간 (2012~2020)**: CAGR 4~5%, MDD -5~-6%, Sharpe 0.76~1.13 — 전략이 가장 안정적으로 작동
- **취약 구간**: GFC 직격(2008~2012, CAGR +0.76%), 금리인상기(2022~2024.6, CAGR +1.49%) — 설계 한계 내 허용 범위
- **Excess CAGR 마이너스**: SPY B&H 대비 언더퍼폼이나, MDD를 평균 -10.75%로 억제한 대가

### Phase 분포 실증 결과 (policy_selection, 2006~2024 연도별)

**경고 발생 연도**:
| 연도 | LATE% | S+R% | 경고 | 해석 |
|------|-------|------|------|------|
| 2007 | 61.5% | 13.8% | Ll | LATE_CYCLE 과다 + S+R 과소 |
| 2008 | 80.5% | 6.3% | Ll | 금융위기 전야 미감지 |
| 2010 | 18.0% | 60.5% | H | GFC 이후 과도 방어 |
| 2016 | 71.7% | 0.0% | Ll | LATE_CYCLE 고착 |
| 2018 | 77.4% | 22.6% | L | LATE_CYCLE 과다 |
| 2019 | 20.3% | 64.0% | H | 침체 과잉 감지 |
| 2021 | 64.4% | 0.0% | Ll | 금리인상 전야 미감지 |
| **2022** | **96.9%** | **2.7%** | **Ll** | **threshold 억제 극단 — 금리인상 최고조** |
| 2023 | 22.7% | 71.5% | H | SLOWDOWN 과다 |
| 2024 | 6.3% | 54.9% | H | SLOWDOWN 지속 |

**가변화 조건 사후 검토**:
- `threshold_policy_v2.md` 필요 조건 "Ll 연속 2년": **2021~2022에 사후 발생**
- 현재(2023~2024)는 H 구간으로 전환 → threshold 가변화 필요성 없음, 0.3 고정 유지 적절

### 신규 테스트 (13건)
**`tests/pipeline/backtest/test_walk_forward.py` — 9건**
- `TestGenerateWindows`: 창 생성 범위·캡핑·명시적 기간 검증 (3건)
- `TestWalkForwardRunnerRun`: 스키마·행 수·빈 window 검증 (3건)
- `TestSaveWalkForward`: parquet+json 생성·컬럼·키 검증 (3건)

**`tests/pipeline/backtest/test_metrics.py` — 4건**
- `TestComputePhaseDistribution`: 연도별 집계·SR_combined·빈 DF·half 집계 (4건)

---

## v2026.02.20 — _get_signal_row 버그 수정 + z-score threshold=0.3 채택

### 변경 요약
- **버그 수정**: `runner.py:_get_signal_row` 다중 decision_date 스냅샷 혼합 → 비결정적 선택 문제 해결
- **버그 수정**: `runner.py:_load_snapshot` Hive 파티션에서 `decision_date` 컬럼 복원
- **Long Engine v1 threshold=0.3 채택**: `_classify_long_phase(threshold=0.3)` → SLOWDOWN+RECESSION 37.7% → 27.0%
- `_classify_long_phase`/`build_long_phase`/`build_axis_horizon_state`/`strategy_job` CLI에 `z_threshold` 파라미터 추가
- 신규 테스트 7건 추가, 전체 `291 passed, 1 skipped`

### 핵심 버그 수정: `pipeline/backtest/runner.py`

**문제**: `_load_snapshot()`이 모든 decision_date parquet를 concat → 동일 trade_date에 여러 스냅샷이 존재할 때 `iloc[0]`이 비결정적. 과거 결과(v0 +4.51% CAGR)는 GFC 스냅샷(2009-03-09)과 2024-06-03 스냅샷이 혼합된 결과였음.

**수정**:
```
1. _load_snapshot(): Hive 파티션 경로에서 decision_date 추출 → date 타입으로 컬럼 추가
2. _get_signal_row(): 최신 decision_date 우선 선택 → source_run_id desc 동률 타이브레이커
```

**수정 후 실제 베이스라인** (threshold=0.0, 스냅샷 혼합 없음):
| 지표 | v0 | v1 | v2 |
|------|-----|-----|-----|
| Total Return | +43.4% | +93.5% | +101.6% |
| CAGR | +1.98% | +3.65% | +3.88% |
| MDD | -6.70% | -21.51% | -15.13% |
| Sharpe | 0.73 | 0.57 | 0.65 |

### z-score threshold=0.3 채택

**Phase 분포 변화** (2006-2026 전체 Gold Macro 기준):
| phase | threshold=0.0 | threshold=0.3 |
|-------|---------------|---------------|
| LATE_CYCLE | 37.7% | **45.1%** |
| SLOWDOWN | 22.9% | 15.5% |
| RECESSION | 14.8% | 11.8% |
| RECOVERY | 5.7% | 8.7% |
| SLOWDOWN+RECESSION 합계 | 37.7% | **27.3%** |

**백테스트 성과 비교** (threshold=0.0 → 0.3):
| 지표 | v0 (0.0) | v0 (0.3) | v2 (0.0) | v2 (0.3) |
|------|---------|---------|---------|---------|
| Total Return | +43.4% | +46.0% | +101.6% | **+118.3%** |
| CAGR | +1.98% | +2.08% | +3.88% | **+4.33%** |
| MDD | -6.70% | -7.23% | -15.13% | -15.79% |
| Sharpe | 0.73 | 0.72 | 0.65 | **0.68** |

**채택 근거**: v2에서 CAGR +0.45%p, Sharpe +0.03 개선. MDD 소폭 악화(-0.66%p)는 허용 범위.

**2024-06-03 스냅샷 재생성** (threshold=0.3 기준):
- LATE_CYCLE: 45.8%, SLOWDOWN: 14.6%, RECESSION: 12.4% — S+R 합계 27.0%

### 신규 테스트 7건
**`tests/pipeline/backtest/test_runner.py` — _get_signal_row 결정론성 (3건)**
- `TestGetSignalRowDeterminism::test_latest_decision_date_wins`: 최신 decision_date 행 선택
- `TestGetSignalRowDeterminism::test_string_decision_date_compared_correctly`: date 변환 후 비교
- `TestGetSignalRowDeterminism::test_source_run_id_tiebreaker`: source_run_id desc 동률 정렬

**`tests/pipeline/strategy_engine/test_long_engine.py` — threshold 파라미터 (4건)**
- `TestLongPhaseThreshold::test_threshold_zero_default`: default threshold=0.0 동작
- `TestLongPhaseThreshold::test_threshold_03_borderline_is_late_cycle`: z=-0.1 → LATE_CYCLE
- `TestLongPhaseThreshold::test_threshold_03_clearly_negative_is_slowdown`: z=-0.5 → SLOWDOWN
- `TestLongPhaseThreshold::test_threshold_03_easing_borderline`: z=-0.1, easing → RECOVERY

### 추가 완료 (동일 세션)
- market_structure_long_contract.md 개정: v1 rolling z-score 로직, z_threshold=0.3, §6 Invariants 상세화
- indicator_id 입력 계약은 2026-02-21에 fail-open 정책 정합화(N/권장)로 보정
- `BacktestResult.metrics` 필드 추가 (total_return 포함 전 지표 programmatic 접근)
- `save_result()` → `{stem}_metrics.json` 저장 추가

---

## v2026.02.19b — Long Engine v1 (delta_6m 지표별 rolling z-score 정규화)

### 변경 요약
- `long_engine.py`: `delta_6m_mean` (이질적 지표 혼합 평균) → 지표별 rolling z-score 평균으로 교체
- LATE_CYCLE 지배 비율 **59.7% → 41.3%** (-18.4%p) 감소 달성
- 신규 테스트 4건 추가, 전체 `284 passed, 1 skipped`

### 핵심 변경: `pipeline/strategy_engine/axis_horizon_state/long_engine.py`

**문제**: `delta_6m_mean` = CPI(수 단위) + UNRATE(0.x 단위) 혼합 평균 → CPI 스케일 압도 → tightening 기간 거의 전부 LATE_CYCLE (59.7%)

**해결**: 지표별 rolling z-score 정규화 (단위 불변)
```
1. (indicator_id, trade_date) 중복 제거: keep="last"
2. 지표별 rolling z-score: window=252, min_periods=60
3. NaN fallback: z-score 미계산 시 raw delta_6m 부호(sign) 사용
4. indicator_id 컬럼 없으면 regime 단독 판정 (fail-open)
```

**LATE_CYCLE 비율 변화** (2006-2024, decision_date=2024-06-03 기준):
| phase | 변경 전 (v0 엔진) | 변경 후 (v1 엔진) |
|-------|---------|---------|
| LATE_CYCLE | 59.7% | **39.7%** |
| SLOWDOWN | ~1% | 20.7% |
| RECESSION | ~5% | 15.4% |
| EXPANSION | ~15% | 15.5% |

**백테스트 성과 (2006~2024)**:
| 지표 | v0 | v1 | v2 |
|------|-----|-----|-----|
| CAGR | +4.51% | +3.53% | +3.99% |
| MDD | -15.66% | -24.64% | -16.26% |
| Sharpe | 0.72 | 0.53 | 0.66 |
| GFC MDD | -9.31% | -17.45% | -10.74% |
| COVID MDD | -15.66% | -11.81% | -11.73% |
| Rate Hike MDD | -11.92% | -11.40% | -9.42% |

구 long_engine v0 대비: v0 CAGR 거의 유지(4.59%→4.51%), v2 CAGR 소폭 하락(5.21%→3.99%)

### 신규 테스트 4건 (`tests/pipeline/strategy_engine/test_long_engine.py`)
- `TestLongPhaseV1Normalization::test_unit_invariance`: CPI/UNRATE 스케일 차이에서도 유효한 ENUM 결과
- `TestLongPhaseV1Normalization::test_nan_fallback_early_period`: 초기구간 NaN → sign fallback 적용 확인
- `TestLongPhaseV1Normalization::test_missing_indicator_id_fallback`: indicator_id 없으면 regime-only (LATE_CYCLE)
- `TestLongPhaseV1Normalization::test_duplicate_indicator_trade_date`: 중복 keep="last" 후 1행 결과

### 미수정 (다음 세션)
- z-score 임계값 조정 (0.0 → 0.3 등): SLOWDOWN/RECESSION 과다 여부 검증 후 결정
- market_structure_long_contract.md 개정: 임계값 확정 후 진행

---

## v2026.02.19 — Allocation v2 (2D lookup) + 아키텍처 리팩토링

### 변경 요약
- Allocation 전략을 `pipeline/backtest/allocation.py`로 분리, 버전별 함수 + `ALLOCATION_REGISTRY` + `dispatch_allocation()` 레지스트리 패턴 도입
- `PRESET_V2` 추가: `target = f(long_phase, mid_regime)` 2D 룩업 — LATE_CYCLE 과도 비율을 allocation 레이어에서 mid_regime으로 분화
- v1 `run_universe=false` 미체크 버그 수정 (INCREASE 차단 누락)
- 신규 테스트 23건 추가, 전체 `280 passed, 1 skipped`

### 핵심 변경

**1) `pipeline/backtest/allocation.py` (신규)**
- `compute_allocation_v0()`: 기존 range-maintenance 로직 위임
- `compute_allocation_v1()`: f(long_phase) target-seeking + `run_universe` 체크 버그 수정
- `compute_allocation_v2()`: f(long_phase, mid_regime) 2D lookup, 4단계 fallback
- `ALLOCATION_REGISTRY`, `dispatch_allocation()`: preset_name 기반 dispatch

**2) `pipeline/backtest/config.py`**
- `BacktestPreset.target_ratio_map_v2: Optional[Dict[Tuple[str,str], float]]` 필드 추가
- `PRESET_V2` 정의 및 `PRESET_REGISTRY["v2"]` 등록
- `BacktestConfig.target_ratio_map_v2` 필드 + `__post_init__` 키/값 검증 + `from_preset()` defaults

**3) `pipeline/backtest/runner.py`**
- `_compute_dynamic_allocation()`: `dispatch_allocation()` 단순 위임으로 교체
- 기존 `_target_seeking_allocation()` inline 메서드 제거

### v2 Target Ratio 2D 테이블
| long_phase \ mid_regime | RISK_ON | NEUTRAL | RISK_OFF | UNKNOWN |
|---|---|---|---|---|
| EXPANSION | 0.80 | 0.70 | 0.55 | 0.65 |
| LATE_CYCLE | 0.60 | 0.45 | **0.30** | 0.45 |
| SLOWDOWN | 0.35 | 0.25 | 0.15 | 0.25 |
| RECOVERY | 0.70 | 0.60 | 0.45 | 0.60 |
| RECESSION | 0.20 | 0.10 | 0.05 | 0.10 |
| UNKNOWN | 0.50 | 0.40 | 0.30 | 0.40 |

핵심: LATE_CYCLE + RISK_OFF = 0.30 (v1의 0.60에서 절반 — 하방 방어 강화)

### 미수정 (다음 세션)
- `long_engine.py` delta_6m 임계값 정밀화: delta_6m_mean이 이질적 지표 혼합 평균이므로 정규화 전략 확립 후 진행

---

## v2026.02.14 — Backtest Engine v0+v1 구현 반영 및 문서 동기화

### 변경 요약
- Strategy Engine 출력 기반 포트폴리오 시뮬레이션 모듈(Backtest Engine)을 구현하고 문서에 반영
- `v0(range-maintenance)` + `v1(target-seeking)` allocation preset을 `BacktestPreset`/`PRESET_REGISTRY`로 고정
- 2006-01-03 ~ 2024-06-03 구간 백테스트 CLI 실행 경로 및 tactical rotation 규칙을 운영 문서에 반영
- Backtest 전용 테스트 62건 포함, 전체 프로젝트 테스트 결과 `256 passed, 1 skipped`로 갱신

---

### 1) Backtest Engine 모듈 추가 (`src/pretrend/pipeline/backtest/`)
- `config.py`
  - `BacktestPreset(frozen)`, `PRESET_REGISTRY(v0/v1)`, `BacktestConfig.from_preset()` 구현
- `portfolio.py`
  - `Portfolio(Position, Trade)` 및 `buy/sell/rebalance_to_weights` 구현
- `rebalancer.py`
  - `compute_target_weights`, `is_rebalance_day`, tactical rotation(`config.tactical_groups`) 구현
- `runner.py`
  - `BacktestRunner` E2E 시뮬레이션
  - `_compute_dynamic_allocation(v0/v1)`, `_target_seeking_allocation` 분기 구현
- `metrics.py`
  - `CAGR`, `MDD`, `Sharpe`, `Sortino`, `Calmar`, 벤치마크 비교 지표 구현
- `report.py`
  - 콘솔 리포트(전체 + GFC/COVID/Rate Hike/Recovery 2023 구간) 구현

---

### 2) Preset 시스템 고정
- `PRESET_V0`
  - range-maintenance (`[0.10, 0.60]`), tactical=`SECTOR`
- `PRESET_V1`
  - target-seeking(phase별 목표 비율), tactical=`SECTOR`
- `PRESET_REGISTRY`
  - `{\"v0\": PRESET_V0, \"v1\": PRESET_V1}`
- `BacktestConfig.from_preset(\"v1\", start_date=..., end_date=..., **overrides)` 지원
- CLI override
  - `--preset v0|v1`
  - `--tactical SECTOR COMMODITY`

---

### 3) v1 Allocation 규칙 반영
- `long_phase -> target ratio`
  - `EXPANSION=0.60`, `RECOVERY=0.60`, `LATE_CYCLE=0.60`, `SLOWDOWN=0.20`, `RECESSION=0.10`, `UNKNOWN=0.40`
- `adjustment_limit=0.10` (월간 최대 10%p), `step_size=0.05` 양자화
- `risk_gate=false`이면 `INCREASE` 차단, `DECREASE` 허용
- v0는 `target_ratio_map=None`으로 Strategy Engine range-maintenance 규칙 위임

---

### 4) Tactical Rotation 규칙
- 조건:
  - `run_universe=true`
  - `risk_gate=true`
  - `long_phase not in {RECESSION, SLOWDOWN}`
- `config.tactical_groups` 기반 필터
  - 기본(v0): `["SECTOR"]`
  - 확장: `["SECTOR", "COMMODITY"]`
- `relative_strength > SPY`인 ETF 상위 2개를 각 15% 비중으로 반영하고, `SCHD`/`SPY`에서 차감

---

### 5) 성과/테스트 현황 (2006-01-03 ~ 2024-06-03)
- 성과 비교:
  - CAGR: v0 `+4.59%`, v1 `+5.37%`, SPY B&H `+10.13%`
  - Total: v0 `+128.7%`, v1 `+162.1%`, SPY B&H `+490.7%`
  - MDD: v0 `-15.7%`, v1 `-23.8%`, SPY B&H `-55.2%`
  - Sharpe: v0 `0.74`, v1 `0.66`
  - GFC MDD: v0 `-9.4%`, v1 `-17.2%`, SPY B&H `-46.0%`
- 테스트:
  - Backtest tests: 62
  - 전체 프로젝트: `257 tests (256 passed, 1 skipped)`

---

## v2026.02.13 — Strategy Engine v0 구현 반영 및 문서 동기화

### 변경 요약
- Strategy Engine 명칭 기준을 확정하고, WHAT/EXPOSURE/SELL 3-경계 출력 + `decision_date` snapshot 저장 원칙을 SOT로 고정
- Gold Macro/EOD snapshot 기반 Strategy Engine v0(7단계 파이프라인) 구현 현황을 문서에 반영
- 테스트 결과(194 passed, 1 skipped) 및 실데이터 검증 요약(GFC 구간 포함)을 운영 문서에 반영
- (Reserved) Stock Extension Port 및 Text/LLM Integration Port를 v1+ 확장 포트로 유지
- Text Observability Contract 신규 추가: Bronze/Silver/Gold 텍스트 레이어, allowlist, event-sort, Strategy Engine 연동 규칙을 문서로 고정

---

## v2026.02.12 — EOD Observability Contract 문서화 및 문서 동기화

### 변경 요약
- PR#1~PR#3 코드 구현을 기준으로 EOD Observability SOT, Bronze/Silver 라벨 계약, Gold EOD Fact Mart를 파이프라인에 반영
- EOD E2E Runner(`eod_job.py`)와 Airflow Gold task(`run_eod_gold_features_task`)를 통합
- EOD 관측용 ETF 세트(Always-on Observability Set)와 분류/라벨 계약을 신규 문서로 고정
- `architecture.md`에 Observability Set 개념(Always-on vs Universe-driven)과 계약 링크를 추가
- `data_requirements.md` EOD 요구사항에 Observability 분류 컬럼 계약(`asset_group`, `asset_name`, `asset_subtype`)을 반영

---

### 1) EOD Observability Contract v1 구현 (PR#1)
- `src/pretrend/pipeline/config/eod_observability.py` 신규 추가
  - SOT 상수: `OBSERVABILITY_SET_V1`, `OBSERVABILITY_SYMBOLS_V1`, `LABEL_BY_SYMBOL_V1`
  - `asset_group` ENUM 5종: `INDEX`, `COUNTRY`, `COMMODITY`, `BOND`, `SECTOR`
  - import 시 `validate_observability_set()` 자동 검증(중복/대문자/ENUM)
- `src/pretrend/pipeline/ingest/eod.py`
  - `EodIngestConfig.default_symbols`를 SOT 참조로 전환
  - `EodNormalizer`에서 미등록 심볼 `ValueError` 처리 및 `asset_group`/`asset_name`/`asset_subtype` 컬럼 확정
- `src/pretrend/pipeline/features/eod_features.py`
  - `build_eod_features()`에서 `asset_*` 라벨을 Silver로 pass-through
- `tests/pipeline/test_eod_observability_contract.py` 신규(9 tests)
  - OL1~OL5 계약 검증(커버리지/라벨/reject/pass-through/멱등 안정성)

---

### 2) 하드코딩 제거 및 SOT 참조 전환 (PR#2)
- `src/pretrend/pipeline/ingest/eod.py` docstring/CLI help를 `Observability SOT` 기준으로 정리
- `dags/eod_pipeline_dag.py` 주석을 `Observability SOT 32개 ETF` 기준으로 정리
- `src/pretrend/pipeline/features/eod_features.py` 내 하드코딩 심볼 예시 정리

---

### 3) Gold EOD Feature v1 Fact Mart 구현 (PR#3)
- `src/pretrend/pipeline/features/gold_eod_features.py` 신규
  - `GOLD_EOD_FEATURE_COLUMNS` 계약
  - `load_silver_eod_features()` 로더
  - `build_gold_eod_features()` Silver→Gold 변환(lineage/dedup)
  - `write_gold_eod_features()` 멱등 저장(symbol/year/month, atomic overwrite)
  - CLI 엔트리포인트: `python -m pretrend.pipeline.features.gold_eod_features`
- `src/pretrend/pipeline/eod_job.py` 신규
  - `EodJobConfig` / `EodJobRunner` / `EodJobResult`
  - Bronze→Silver→Gold 순차 실행 + 메타 로그(`data/meta/eod_job_log.parquet`)
- `dags/eod_pipeline_dag.py`
  - `run_eod_gold_features_task` 추가
  - 의존 체인 Bronze → Silver → Gold로 확장, DAG tag에 `gold` 추가
- `tests/pipeline/test_gold_eod_features.py` 신규(7 tests)
  - GE1~GE5 계약 검증(grain/columns/labels/lineage/idempotency)

---

### 4) 테스트 현황
- 전체 테스트: **71 passed, 1 skipped**

---

### 5) 신규 계약 문서 추가
- `docs/architecture/eod_observability_contract.md` 생성
- 포함 범위:
  - 용어 정의(Observability Set, 분류 컬럼, Always-on vs Universe-driven)
  - Scope / Non-Goals
  - 분류 체계(`INDEX`, `COUNTRY`, `COMMODITY`, `BOND`, `SECTOR`)
  - Base EOD Observability Set v1 전체 심볼 표
  - Bronze/Silver/Gold 라벨 전파 규칙 및 ENUM 계약
  - Universe read-only 소비 원칙 및 변경 관리(Versioning)

### 6) Architecture 문서 동기화
- `docs/architecture.md`에 EOD Observability Set 설명 단락 추가
- Always-on 센서 입력 목적, 라벨 고정 원칙, 계약 문서 링크 반영

---

### 7) Data Requirements 문서 동기화
- `docs/data_requirements.md`의 EOD 섹션에 `Always-on Observability ETFs v1` 항목 추가
- 필수 분류 컬럼 계약 및 Universe 그룹핑 사용 규칙을 명시

---

### 8) Risk-Control 전략 문서 구조 재정의 (4축 + Composer + Allocation v0)
- Design vs Contract 분리 원칙으로 전략 문서를 재구성
  - Design: `docs/strategy_architecture.md`
  - Contracts: `market_structure_long/mid/short/composer`, `universe`, `allocation_engine`
  - Inventory: `docs/market_structure_data_inventory.md`
- 전략 흐름을 `Layer -> Market Structure(4축) -> Composer -> Universe -> Allocation Engine -> Weekly Report`로 고정
- v0 원칙 반영:
  - 총 투자 비율(`invested_ratio`) 조절만 허용
  - `risk_gate` 기반 증가 차단
  - Universe 내부 가중치 조절 금지
- 심리 축 입력 정책 갱신:
  - v0: VIX 필수 아님, Risk Spread + Volatility proxy 기반 상태 전이
  - v1+: VIX 편입(직접 VIX vs term structure 범위 결정 필요)
- 구버전 문서 정리:
  - `docs/architecture/market_structure_v1_contract.md` 삭제
  - 레거시 전략 계약 문서 제거(현행 구조에서 비사용)

---

### 9) 전략 로드맵 문서 동기화
- `docs/milestones.md`에 Risk-Control 전략 로드맵(v0~v3) 추가
- 운영 주기 분리 명시:
  - Adjustment Cycle: 주 1회(화요일)
  - Portfolio Rebalance: 월 1회(마지막 주 금요일, 휴장 시 직전 영업일)

## v2026.02.11 — Gold Macro Feature v1 E2E 통합 구현

### 변경 요약
- Gold Layer v1을 설계 계약(`gold_design_contract.md`)에서 구현 완료 단계로 전환
- `macro_job.py` E2E 플로우에 Gold 단계 통합: Bronze → Silver → Gold 1회 실행 동기화
- Calendar Silver(`econ_events`, `fred_vintages`)를 소비하는 3-tier fallback cascade로 `release_date` 증거 구축
- PIT 불변식(`selected_release_date < trade_date`) 100% 충족 검증 완료

---

### 1) Gold Macro Feature v1 핵심 로직 (`gold_macro_features.py`)
- 기존 순수 함수(`build_gold_macro_features`, MF1-MF10 테스트 완료)에 통합 인프라 추가:
  - `load_silver_macro()`: Silver macro → `[indicator_id, date, value]` 로드
  - `build_release_calendar()`: 3-tier fallback cascade
    - Tier 1: `econ_events` (`release_date = release_date_utc`)
    - Tier 2: `fred_vintages` (`is_first_vintage=True`, `release_date = vintage_date`)
    - Tier 3: `assumed_t+1` (`release_date = observation_date + 1 day`)
  - `write_gold_macro_features()`: `trade_date` 기준 파티션, `tmp -> atomic rename` 멱등 저장

---

### 2) `macro_job.py` E2E 플로우 통합
- 변경 전:
  - `bronze_ingest -> bronze_vintages -> bronze_econ_events -> silver_features -> silver_calendar`
- 변경 후:
  - 위 플로우 + `gold_macro_features` 추가
- `MacroJobConfig.gold_root` 프로퍼티, `MacroJobResult.gold_macro_result` 필드, Meta log `gold_macro_row_count` 반영

---

### 3) Calendar Runner Silver 로더 추가 (`calendar/runner.py`)
- `load_silver_econ_events()`, `load_silver_fred_vintages()` 추가
- Gold가 Silver Calendar의 첫 번째 downstream 소비자

---

### 4) E2E 검증 결과 (`--start 2024-01-01 --end 2024-06-30`)
- Gold 출력: 650행 (5 지표 × 130 영업일), 6개 월별 파티션
- PIT 불변식 위반: 0건
- `release_source` 태깅:
  - `CPI_US_ALL_ITEMS_SA`, `CPI_US_CORE_SA`, `US_UNEMPLOYMENT_RATE` → `econ_events`
  - `US_FED_FUNDS_RATE`, `US_TREASURY_10Y_YIELD` → `fred_vintages`
- `is_assumption_based`: 전부 `False` (Calendar 증거 100% 커버)
- Gold 저장 경로:
  - `data/gold/macro/macro_features/year=YYYY/month=MM/gold_macro_features_YYYYMM.parquet`

---

### 5) 테스트 현황
- Gold MF1-MF10: 22개 패스 (`tests/pipeline/test_gold_macro_feature_v1.py`)
- Calendar ST1-ST11: 12개 패스 (`tests/pipeline/test_calendar.py`)
- 전체 34개 테스트 통과

---

### 6) zscore_12m v1.1 구현 (`gold_macro_features.py`)
- `_zscore_12m()` 헬퍼 함수 추가 (lines 194-217)
- 공식: `(selected_value - mean) / std` — 12-month rolling z-score
- Monthly 지표 (CPI, UNRATE, FEDFUNDS): window = 12 관측치
- Daily 지표 (DGS10): window = 252 관측치 (약 1년 영업일)
- Edge cases:
  - `selected_value` NULL/NaN → None
  - window 내 관측치 부족 → None
  - std == 0 또는 NaN → None
- `_select_and_compute()`에서 기존 `"zscore_12m": None` → `_zscore_12m()` 호출로 변경

---

### 7) zscore_12m 테스트 (MF10a-MF10e)
- 기존 `TestZscoreV1` (항상 NULL 검증) → `TestZscoreV1_1` (실제 계산 검증)으로 교체
- MF10a: zscore_12m 컬럼 존재 확인
- MF10b: 히스토리 부족 시 NULL (standard fixture: 7 CPI months < 12)
- MF10c: 충분한 히스토리 시 계산값 검증 (12 monthly values, expected = 5.5/sqrt(13))
- MF10d: selected_value=NULL → zscore=NULL
- MF10e: std=0 (모든 값 동일) → zscore=NULL
- 전체 테스트: 54 passed, 1 skipped (EOD integration)

---

### 8) Gold EOD Feature v1 E2E 통합 구현
- `gold_eod_features.py`에 CLI 엔트리포인트(`parse_args`, `main`)를 추가하여 모듈 단독 실행을 지원
  - `python -m pretrend.pipeline.features.gold_eod_features --start ... --end ...`
- `eod_job.py`를 추가하여 EOD Bronze → Silver → Gold를 1회 실행으로 동기화
  - 핵심 구성: `EodJobConfig`, `EodJobRunner`, `EodJobResult`
  - 메타 로그: `data/meta/eod_job_log.parquet`
- `eod_pipeline_dag.py`에 `run_eod_gold_features_task`를 추가하고 의존 체인을 Bronze → Silver → Gold로 확장
- Gold EOD 출력 계약:
  - Grain: `(symbol, trade_date)`
  - 저장 경로: `data/gold/eod/eod_features/symbol=XXX/year=YYYY/month=MM/gold_eod_features_YYYYMM.parquet`
  - 라벨(`asset_group`, `asset_name`, `asset_subtype`)은 Silver에서 carry-forward

---

### 향후 계획
- (완료) `zscore_12m` 구현 (v1.1)
- (완료) EOD Gold Layer 설계 및 구현
- Universe(U0~U3) 계산 로직 구현

## v2026.02.10 — Calendar Pipeline v1 구현 (Bronze + Silver)

### 변경 요약
- Calendar Pipeline v1을 설계 명세 단계에서 구현 완료 단계로 전환하여, `econ_events` / `fred_vintages` Bronze→Silver 파이프라인이 실제 동작하도록 반영
- FRED 기반 Calendar Bronze ingest를 추가하여 release 증거 수집 경로를 코드로 고정
- `macro_job.py` E2E 플로우에 `bronze_econ_events`와 `silver_calendar(econ_events + fred_vintages)` 단계를 통합
- Silver Calendar 스키마를 release evidence 중심으로 경량화(`actual_value`, `value` 제거)
- Calendar 테스트 12개(ST1~ST11 + ST3 variant)를 통해 스키마/멱등성/dedup/timezone 계약 검증 완료

---

### 1) Calendar Silver 구현 완료 (`econ_events` + `fred_vintages`)
- 구현 모듈:
  - `src/pretrend/pipeline/calendar/config.py`
  - `src/pretrend/pipeline/calendar/econ_events.py`
  - `src/pretrend/pipeline/calendar/fred_vintages.py`
  - `src/pretrend/pipeline/calendar/runner.py`
- `runner.py`는 Bronze loader(`load_bronze_econ_events`, `load_bronze_fred_vintages`)와 CLI(`--target econ_events|fred_vintages|all`)를 제공
- 저장 경로(파티션 overwrite):
  - Bronze: `data/bronze/calendar/{econ_events|fred_vintages}/year=YYYY/month=MM/*.parquet`
  - Silver: `data/silver/calendar/{econ_events|fred_vintages}/year=YYYY/month=MM/*.parquet`

---

### 2) Calendar Bronze ingest 추가 (FRED release/dates + vintage API)
- `src/pretrend/pipeline/ingest/macro.py` 확장:
  - `MacroFetcher.fetch_vintages()` 추가
    - FRED observations API(`realtime_start/end`) 기반 vintage 수집
    - observation 연도 × realtime 2년 이중 청크
    - rate limit 0.5s + 429 exponential backoff
  - `MacroFetcher.fetch_econ_events()` 추가
    - FRED release/dates API 기반 release 날짜 수집
    - `release_id=10`(CPI), `release_id=50`(Employment) 반영
    - `release_id=18`(H.15)은 제외(주간/일간 릴리즈, `fred_vintages` fallback으로 커버)
    - `release_date -> observation_date`는 전월 1일 매핑(월간 지표)
  - `VintageNormalizer` / `VintageWriter`, `EconEventsNormalizer` / `EconEventsWriter` 추가

---

### 3) `macro_job.py` E2E 플로우 통합
- 변경 전:
  - `bronze_ingest -> bronze_vintages -> silver_features -> silver_calendar(fred_vintages만)`
- 변경 후:
  - `bronze_ingest -> bronze_vintages -> bronze_econ_events -> silver_features -> silver_calendar(fred_vintages + econ_events)`
- 결과적으로 Macro Job 1회 실행으로 Calendar Bronze+Silver까지 동기화 가능

---

### 4) Silver Calendar 스키마 경량화
- `econ_events Silver`에서 `actual_value` 컬럼 제거
- `fred_vintages Silver`에서 `value` 컬럼 제거
- Calendar Silver는 값(value) 저장소가 아니라 Gold PIT용 `release_date` 증거 레이어로 역할 고정

---

### 5) 테스트 및 검증
- 테스트 파일: `tests/pipeline/test_calendar.py`
- 테스트 수: 12개 (ST1~ST11 + ST3 variant)
  - Schema invariant
  - Idempotency
  - Dedup
  - Timezone normalization
- 모든 테스트는 synthetic fixture 기반이며 외부 API 호출 없음
- 검증 실행 요약:
  - 단기 실행(`--start 2024-01-01 --end 2024-06-30`): Bronze 21행, Silver 18행(econ_events)
  - 전체 실행(`--start 2015-01-01 --end 2026-02-01`): `fred_vintages` Silver 28,412행

---

### 향후 계획
- (완료) Gold Layer v1에서 Calendar(`econ_events`, `fred_vintages`)를 소비하는 PIT-safe 결합 로직 구현
- Gold release source 태깅(`econ_events` / `fred_vintages` / `assumed_t_plus_1`)과 계약 테스트 연계 강화

## v2026.02.06 — Pipeline Idempotency 강화 및 Agent 운영 기준 확정

### 변경 요약
- Macro / EOD Silver 파이프라인의 **멱등성(idempotency) 검증 수준을 파티션 invariant 기준으로 상향**
- AI Agent(Codex) 도입 범위를 **tests/docs 전용 보조 도구**로 명확히 제한하고, 운영 규칙을 문서로 고정
- 현재 구현 범위와 문서 간 **정합성(Doc Sync) 완료**

---

### 1) Silver Layer 멱등성 검증 강화

#### Macro / EOD Silver 공통
- 기존:
  - 파일 존재 여부 또는 단일 파일 overwrite 여부 중심 검증
- 개선:
  - **파티션 단위 invariant 검증**
    - 재실행 시 파티션 내 row 수 증가 없음
    - 중복 artifact 생성 없음
    - overwrite 보장

#### 테스트 설계 원칙
- 구현 세부(파일명, 내부 로직)에 결합된 assert 제거
- 의미적 불변조건(invariant) 중심 테스트로 재설계
- 향후 저장 포맷/경로 변경에도 테스트 재사용 가능하도록 구성

---

### 2) 테스트 품질 및 결합도 개선
- 파티션 전체를 기준으로 검증하도록 테스트 구조 단순화
- parquet 파일 반복 로딩/순회 로직 제거
- 테스트가 “구현을 설명”하지 않고 “결과를 검증”하도록 역할 정리

---

### 3) Agent(Codex) 도입 운영 기준 확정

#### 도입 결론
- Codex는 **설계·판단·전략·실행 주체가 아님**
- 역할:
  - 테스트 코드 초안 생성
  - 문서 동기화
  - 반복 작업 보조

#### 통제 장치
- `AGENTS.md` 고정:
  - Scope 제한 (tests/docs 중심)
  - 작은 diff (1 task / ≤300 LOC 권장)
  - public API 변경 금지
  - 멱등성/파티션 overwrite 규칙 보존
  - 검증 커맨드 명시 필수
- 브랜치 전략:
  - `codex/<task>` 단위 작업
- Task Spec에 Scope / DoD 명시

#### 면접·대외 설명 기준
- “AI가 다 했다” ❌
- “AI 초안 → 사람이 리뷰·수정·승인 → 테스트/문서로 증명” ⭕
- Agent 사용 여부 및 역할 분리는 `agent_adoption_notes.md`에 명시

---

### 4) 문서 동기화 완료
- README
- operation_guide
- agent_adoption_notes

→ 현재 코드 구현 범위(Macro/EOD Bronze→Silver, 멱등성 정책, Agent 운영 기준)와 문서 내용이 일치하도록 정렬 완료

---

### 5) 현재 스코프 및 다음 단계

#### 완료 범위
- Macro Bronze → Silver 파이프라인
- EOD Bronze → Silver 파이프라인
- 파티션 overwrite 기반 멱등성 보장
- 운영 환경을 가정한 테스트/문서/Agent 통제 구조

#### 다음 목표 (Out of scope → Next)
- Gold Layer:
  - Macro Silver + EOD Silver 결합
  - as-of join 기반 Feature Mart 설계
- Universe(U1~U3) 계산 로직 구현 및 테스트


## v2026.01.14
- Macro Pipeline 운영 정책 정리
  - DAG 매일 트리거 + 직전월 1일~전일 롤링 재처리
  - Silver Macro Feature year/month overwrite 멱등성 명시
- Gold Layer 설계 준비를 위한 Macro/EOD 정합성 문서화

## v2025.12.05 - EOD Airflow Pipeline (Bronze → Silver) 통합 및 Silver Feature Layer 구축

### 변경 요약
- EOD Bronze/Silver를 하나의 Airflow DAG(`eod_pipeline_dag`)로 통합
- 미국장 기준 "마지막 완전 거래일" 기반 Bronze ingest 자동화
- EOD Silver Feature Layer(v1) 신규 구축 (수익률/MA/ATR/RSI 포함)
- Silver Writer 멱등성 적용 및 파티션 구조 확정
- Gold Layer 설계를 위한 준비 작업 완료

---

### 1) EOD Pipeline 통합 (Bronze → Silver)
- 기존 단일 Bronze DAG를 제거하고 Macro pipeline 구조와 동일하게 **Bronze→Silver 통합 DAG** 구성
- DAG: `eod_pipeline_dag`
  - Task 1: `run_eod_bronze_ingest`
    - yfinance 기반 SPY/QQQ/VOO ingest
    - 미국장 ET 기준 "마지막 완전 거래일" 계산하여 하루 구간만 ingest
    - Bronze 저장 구조 유지:
      ```
      data/bronze/eod/daily_prices/
        source=YF/theme=GENERIC/symbol=SPY/trade_date=YYYY-MM-DD/eod.parquet
      ```
  - Task 2: `run_eod_silver_features`
    - Bronze 결과(XCom) 기반 동일 날짜/심볼로 Silver 생성
    - EOD Silver Writer는 (symbol/year/month) 파티션으로 멱등성 저장

---

### 2) EOD Silver Feature Layer 구축
- 신규 파일: `src/pretrend/pipeline/features/eod_features.py`
- Feature Set(v1):
  - **수익률:** ret_1d / log_ret_1d / ret_5d / ret_20d
  - **변동성:** vol_20d / vol_60d
  - **이동평균:** ma_5 / ma_20 / ma_60 / ma_120 / ma_ratio_5_20
  - **ATR & TR:** atr_14
  - **RSI:** rsi_14 (gain/loss SMA 기반)
  - **Volume 특성:** volume_zscore_20d
  - **Micro-structure:** gap_open, intraday_range
  - **Data Quality Flags:** is_trading_day, is_missing_imputed, is_outlier, is_partial_day
- Feature 계산 방식은 symbol 단위 groupby에서 shift/rolling 기반으로 안정화

---

### 3) EOD Silver 저장 구조 표준화
- 저장 경로: data/silver/eod/eod_features/symbol=SPY/year=2024/month=12/eod_features_202412.parquet
- 멱등성 전략: `_tmp_run={run_id}` 임시 디렉토리 생성
- 파티션 단위 atomic overwrite

---

### 4) Gold Layer 준비 단계 완료
- Gold 설계를 위해 필요한 전제조건 모두 충족:
- Macro Silver 완성
- EOD Silver v1 완성
- Airflow 기반 Bronze→Silver 자동화 환경 구축

### 향후계획
- Macro Silver + EOD Silver as-of join 구조 설계
- Gold Feature 스키마 정의
- Gold Pipeline DAG 구성(`gold_pipeline_dag`)
- 이후 NLP Bronze/Silver 추가(뉴스/FOMC/경제 리포트)
---

## v2025.12.03 - Macro Airflow Pipeline (Bronze → Silver) E2E 통합

### 변경 요약
- Macro Bronze/Silver 파이프라인을 Airflow DAG(`macro_pipeline_dag`)로 통합
- Airflow 전용 환경(`airflow-pretrend`)에서 MacroJob E2E (Bronze ingest → Silver features → Meta log) 자동 실행 성공
- 운영을 위한 환경변수 설계(`.env.airflow`) 및 개발용 런처 스크립트(`run_airflow_dev.sh`) 도입

### Airflow 환경 구성
- 별도 conda env: `airflow-pretrend`
- `AIRFLOW_HOME=/home/redtable/Desktop/ethan/pretrend/airflow_pretrend`
- `DAGS_FOLDER`를 `pretrend_ai/dags`로 지정 (`AIRFLOW__CORE__DAGS_FOLDER`)
- `run_airflow_dev.sh`에서:
  - `PROJECT_ROOT` 기반 공통 경로 설정
  - `.env.airflow`를 `set -a; source .env.airflow; set +a` 패턴으로 로드하여 환경변수 일괄 export
  - `webserver`, `scheduler`, `init-db`를 서브커맨드 형태로 실행 가능하도록 구성

### 환경변수 / 시크릿 설계
- `.env.airflow`에 운영에 필요한 핵심 변수만 정의
  - `FRED_API_KEY` : FRED 연동용 API 키
  - `PRETREND_DATA_ROOT` : `/home/redtable/Desktop/ethan/pretrend/pretrend_ai/data`
- 모든 시크릿/경로는 Git에 커밋하지 않고 `.env.airflow` + 런처 스크립트 구조로 관리

### MacroJob Airflow 통합
- DAG: `macro_pipeline_dag`
  - Task: `run_macro_job` (PythonDecoratedOperator 기반)
  - 내부에서 `MacroJobRunner.from_env()` 호출
- Airflow 실행 시 E2E 플로우:
  1. Bronze ingest
     - MacroFetcher → MacroNormalizer → MacroWriter
     - FRED에서 FEDFUNDS, 10Y YIELD 등 거시 지표 수집
     - 절대경로 기반 저장:
       - `data/bronze/macro/econ_indicators/year=YYYY/month=MM/{indicator_id}_YYYYMM.parquet`
  2. Silver macro features
     - Bronze 파티션 로딩 후 feature 계산
     - `data/silver/macro/macro_features/year=YYYY/month=MM/macro_features_YYYYMM.parquet`
  3. Meta log
     - `data/meta/macro_job_log.parquet`에 run_id, 기간, row count 등 실행 이력 기록

### 기술 이슈 해결 내역
- Airflow 태스크 내에서 `FRED_API_KEY` 미설정 오류 발생 → `.env.airflow` + `run_airflow_dev.sh`로 해결
- Parquet 저장 시 `pyarrow` 미설치로 인한 ImportError 발생 → `airflow-pretrend` 환경에 `pyarrow` 추가 설치
- `PRETREND_DATA_ROOT`를 기준으로 Bronze/Silver/Meta 경로를 절대경로로 통일 → CLI와 Airflow 간 경로 일관성 확보

### 향후 계획 (Macro 관련)
- `macro_pipeline_dag`의 `schedule_interval`을 매일 1회, 한국 시간 기준 오전(예: 09:00 KST)으로 설정하여 EOD Macro 자동 수집
- pandas `groupby.apply` FutureWarning 제거를 위한 Silver Feature 코드 리팩토링
- Macro DAG 모니터링 및 실패 알림(Slack/Email) 연동을 MLOps 단계에서 추가
---

## v2025.12.02 - FRED macro CPI ingest + parquet writer (bronze)

### 구조
  - IngestContext + BaseFetcher / BaseNormalizer / BaseWriter 공통 인터페이스 확립
  - MacroFetcher → MacroNormalizer → MacroWriter E2E 플로우 정상 동작

### FRED 연동
  - FRED API Key 환경변수로 연동 (FRED_API_KEY)
  - CPIAUCSL 기준으로 fetch/normalize/write 전부 검증 완료

### 저장 스키마
  - Bronze 스키마: indicator_id, date, value, unit, source, run_id, ingestion_ts
  - 디렉토리/파일 구조: data/bronze/macro/econ_indicators/year=YYYY/month=MM/{indicator_id}_YYYYMM.parquet

### 멱등성
  - 기준 키: (indicator_id, date)
  - 같은 파라미터로 재실행 시 파일 덮어쓰기 → 비즈니스 데이터 상태는 동일
  - run_id, ingestion_ts는 실행 이력(lineage)용 메타데이터

### Multi-indicator 확장 준비
  - FredSeriesSpec, FredMacroConfig 설계 완료
  - from_env_with_defaults()에서 CPI, Core CPI, UNRATE, FEDFUNDS, DGS10까지 한 번에 수집 가능
  - MacroFetcher는 series_list 기반 multi-series ingest 구조로 설계됨
---

## v2025.11.28

### 변경 요약
- Universe 설계를 "전 종목 기반"에서 "거시→테마→종목(U0~U3)" 구조로 전면 개편
- 한국 주식 종목은 Universe 대상에서 제외하고, 글로벌/미국 시장 중심 구조로 전환
- EOD 수집 대상은 전체 종목이 아니라 **U3 최종 Universe에 포함된 종목만**으로 한정

### 신규 문서
- `docs/universe_design.md`
  - U0: Macro Signal Detector (거시 신호 감지 및 영향력 수치화)
  - U1: Theme Prioritization (각광받을 테마 스코어링)
  - U2: Theme Universe Builder (테마 기반 주요 종목 1차 필터링)
  - U3: Growth & Flow Candidates (성장성 + 수급 기반 최종 Universe)
  - Universe와 EOD Ingest 연계 구조 정의

- `docs/data_requirements.md`
  - Macro / Theme / Stock / EOD별 필수 데이터 항목 정의
  - MVP 단계에서 수집해야 할 최소 데이터 셋(Macro 4종, Theme 3종, Stock 3종, EOD OHLCV) 명시
  - 주요 데이터 소스(FRED, Yahoo Finance, FMP 등) 개략 정리

### 설계 방향 결정 사항
- 한국 주식 종목은 Universe에서 제외하고, 미국/글로벌 종목을 기반으로 전략 설계
- 전 종목 EOD 수집은 스코프에서 제외
- Universe는 "신호 → 테마 → 종목"의 탑다운 방식으로 생성하고,
  U0~U3 각 단계의 역할과 필요 데이터 정의를 완료
