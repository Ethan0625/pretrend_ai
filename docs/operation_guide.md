# Operation Guide

## Agent-assisted development (Codex)
- **Workflow:** `dev` → `codex/<task>` 분기 → 작업/커밋 → PR/머지 → `dev` 반영.
- **Verification checklist:** `pytest -q` (필요 시 대상 파일 예: `pytest -q tests/pipeline/<file>.py`), `git diff --cached`.
- **Guardrails:** `.agent/WORKFLOW.md`, `.agent/CHANGE_GATES.md` 준수, 비공개 정보/시크릿 금지, 요청 없는 공개 API 변경 금지, 파티션 overwrite·멱등성 보존.
- **Rollback:** 브랜치 폐기 또는 `git restore`로 변경 취소.

## Calendar Pipeline 실행
- `macro_job.py` 실행 시 Calendar Bronze + Silver(`econ_events`, `fred_vintages`)가 함께 빌드된다.
- Calendar만 독립 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.calendar.runner --target all`
- Calendar 테스트 실행:
  - `conda run -n pytest-pretrend pytest tests/pipeline/test_calendar.py -v`

## Gold Macro Feature v1 실행
- `macro_job.py` 실행 시 Bronze → Silver → Gold(Macro v1)까지 1회 실행으로 동기화된다.
- 실행 명령:
  - `PYTHONPATH=src python -m pretrend.pipeline.macro_job --start 2024-01-01 --end 2024-06-30`
- Gold/Calendar 통합 테스트 실행:
  - `conda run -n pytest-pretrend pytest tests/pipeline/test_gold_macro_feature_v1.py -v`
  - `conda run -n pytest-pretrend pytest tests/pipeline/test_calendar.py -v`

## Gold EOD Feature v1 실행
- Gold EOD 단독 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.features.gold_eod_features --start 2024-01-01 --end 2024-06-30`
- EOD Bronze → Silver → Gold E2E 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.eod_job --start 2024-01-01 --end 2024-06-30`
- Airflow `eod_pipeline_dag`는 Bronze → Silver → Gold 순서로 실행된다.
- EOD Gold 테스트 실행:
  - `conda run -n pytest-pretrend pytest tests/pipeline/test_gold_eod_features.py -v`

## Strategy Engine 실행
- Strategy Engine v0 단일 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.strategy_engine.strategy_job --date 2024-06-03 --invested-ratio 0.10`
- Strategy Engine z-threshold 지정 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.strategy_engine.strategy_job --date 2024-06-03 --invested-ratio 0.10 --long-z-threshold 0.3`
- 입력 전제:
  - Gold Macro snapshot
  - Gold EOD snapshot
- 출력 경계:
  - `WHAT_TO_HOLD`
  - `HOW_MUCH_EXPOSURE`
  - `HOW_MUCH_TO_SELL`
- 스냅샷 저장 기준:
  - `decision_date` 파티션
  - overwrite + atomic write
  - `next_step_history` 증분 저장(`trade_date, decision_date_ref` key)

## 재현성 저장 원칙 (Compute once, store, compare many)
- 계산 가능한 전이예측 feature(`state_age/sojourn/hazard`)는 snapshot/history로 선저장한다.
- 소비자는 저장본을 우선 사용하고 결측 시에만 fail-open fallback을 사용한다.
- 결과 비교는 registry + summary artifact로 재실행 없이 조회 가능해야 한다.
- 실행 기준 bias는 `bias_20d` 단일 경로를 사용한다 (`1m/3m` alias 비사용).

### next_step 지평 마이그레이션 (5/10/20/60/120D)
- dry-run:
  - `python scripts/migrate_next_step_horizons.py --dry-run`
- apply:
  - `python scripts/migrate_next_step_horizons.py --apply`

## 통합 테스트 실행
- 전체 테스트:
  - `conda run -n pytest-pretrend pytest tests/ -v`
- 테스트 상태 기록 원칙:
  - 고정 숫자 대신 최신 pytest/CI 로그를 기준으로 확인

## 권장 E2E 실행 시퀀스
- Macro 파이프라인(Bronze→Silver→Calendar→Gold):
  - `PYTHONPATH=src python -m pretrend.pipeline.macro_job --start 2006-01-01 --end 2026-02-12`
- EOD 파이프라인(Bronze→Silver→Gold):
  - `PYTHONPATH=src python -m pretrend.pipeline.eod_job --start 2006-01-01 --end 2026-02-12`
- Strategy Engine 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.strategy_engine.strategy_job --date 2024-06-03 --invested-ratio 0.10`

## Backtest Engine 실행
- 실행 규칙(현재):
  - 월 첫 거래일: `monthly_addition` 자금 추가(DCA)
  - 월요일: 전 거래일(T-1) 기준 신호 평가
  - 화요일: `INCREASE` 실행(현금 배포 매수)
  - 금요일: `DECREASE` 단계 매도(`50% → 30% → 20%`, 3주)
  - `risk_gate=false(PANIC)`: `INCREASE` 허용, `DECREASE` 신규 생성 차단/진행 트랜치 동결
- v0(range-maintenance) 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v0`
- v1(target-seeking) 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v1`
- v2(2D target-seeking: long_phase × mid_regime) 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v2`
- v3(2D + next_step soft gate) 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3`
- v3.1(v3 + monthly bias lock) 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.1`
- v3.2(v3.1 + shock override/cooldown) 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.2`
- v3.3(v3.2 + hazard-aware override gate) 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.3`
- v3.4(v3.3 + tactical group transition gate) 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.4`
- v3.4.1(v3.4 + recovery-aware re-entry gate) 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.4.1`
  - 규칙: `WEAK>=2`일 때만 축소, `RELIEF 2연속` 또는 `MID=RISK_ON`에서 축소 해제
- v3.4.2-phase(v3.4.1 + phase-aware bias state machine) 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.4.2-phase`
  - 규칙: `RECOVERY -> RISK_ON_BIAS` baseline, 월요일 판정, hysteresis/cooldown(5거래일)
- v3.4.2a(v3.4.2-phase + 체류 규칙 완화 실험) 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.4.2a`
  - 규칙: cooldown 기본 5일 유지 + `mid=RISK_ON` 또는 `RELIEF 2연속`에서 cooldown 2일 압축
  - 보조 규칙: `run_universe` 복귀 + `RELIEF 2연속`이면 월요일에 `RISK_OFF -> NEUTRAL` 1단 완화(soft-only)
- 운영 기준:
  - `v3.4.2a`는 실험군으로만 유지한다.
  - 운영 기본 preset은 `v3.4.1`을 사용한다.
- 결과 저장 원칙:
  - `save_result()`를 호출한 실행만 아티팩트/registry에 저장된다.
  - 단순 `BacktestRunner().run()` 호출은 콘솔 결과만 생성하고 파일은 남기지 않는다.
- 권장 저장 경로(기간 포함):
  - `result/backtest_compare/<window>_<YYYYMMDD-YYYYMMDD>/<preset>/`
  - 예: `result/backtest_compare/long_20060103-20240603/v3.3/`
- 표준 저장 아티팩트(`save_result`):
  - `{stem}.parquet` (legacy daily log)
  - `{stem}_daily_nav.parquet`
  - `{stem}_trades.parquet`
  - `{stem}_config.json`
  - `{stem}_metrics.json` (legacy)
  - `{stem}_summary_metrics.parquet`
  - `{stem}_summary_metrics.json`
  - `{stem}_diagnostics.parquet`
  - `{stem}_final_positions.parquet`
- registry 저장:
  - `result/backtest/registry/pipeline=backtest/run_date=YYYY-MM-DD/registry.parquet`
  - `artifact_path`/`run_id`/기간/버전 메타로 재실행 없이 비교 조회 가능
- 결과 저장 후 비교(실행 직후 + 저장본 재조회):
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v2`
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.1`
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.2`
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.3`
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.4`
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v3.4.1`
- v2 + DCA 월 적립금 지정 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v2 --monthly-addition 300`
- v1 + tactical override 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v1 --tactical SECTOR COMMODITY`

아티팩트 누락 점검/재생성:
```bash
# 1) 저장 파일 확인
find result/backtest_compare -maxdepth 3 -type d | sort

# 2) 특정 preset 파일 확인
find result/backtest_compare/long_20060103-20240603/v3.3 -maxdepth 1 -type f | sort

# 3) registry 확인
python - << 'PY'
import pandas as pd
p='result/backtest/registry/pipeline=backtest/run_date=2026-02-25/registry.parquet'
df=pd.read_parquet(p)
print(df[['pipeline','preset','start_date','end_date','artifact_path','run_id']].tail(20).to_string(index=False))
PY
```

Backtest/Walk-forward 해석 키:
- `sojourn_prob_*`: 현재 상태가 해당 기간(5/10/20/60/120일) 더 유지될 확률
- `transition_hazard_*`: 해당 기간 내 상태 전환 위험도 (`1 - sojourn_prob`)
- `PRETREND_HAZARD_THRESHOLD_10D`:
  - v3.3 hazard-aware override 게이트 임계치 (기본 `0.95`)
  - `transition_hazard_10d < threshold`일 때 override 억제
- `bias_state_source` / `bias_switch_reason` / `bias_cooldown_left`:
  - v3.4.2-phase 상태머신 메타
  - SIGNAL/PAPER에서 전환 근거 설명용으로 사용
- `cooldown_compressed_flag/reason`, `hard_gate_exit_assist_flag/reason`:
  - v3.4.2a 체류 완화 메타
  - PAPER_RESULT의 게이트/강도 섹션에서 보조 설명으로 노출

## Paper Trading 기본 조건
- 초기 자금: `1,000,000원`
- 월 첫 거래일 DCA: `300,000원`
- 환산 환율: `PAPER_FX_USDKRW` (기본 `1300`)
- 실행 규칙:
  - 월요일: 전 거래일(T-1) 기준 신호 평가
  - 화요일: `INCREASE` 실행(현금 배포 매수)
  - 금요일: `DECREASE` 분할 매도(`50% -> 30% -> 20%`)
- 코어 제약:
  - `SCHD` 매도 금지
  - phase별 매수 강도만 조절(`next_invested_ratio`)
- 입력 범위 제어:
  - `PAPER_START_DATE` 환경변수(기본 `2026-01-01`) 이후 구간만 누적 계산
- 통화 처리:
  - 운영 입력(초기 자금/DCA)은 KRW로 관리
  - 실제 체결 계산은 USD(가격 소스: Gold EOD `adj_close`)로 환산 후 실행
- 계약 참조:
  - `docs/architecture/paper_execution_ledger_contract.md`
  - `docs/architecture/paper_trading_alert_contract.md`
  - `docs/architecture/next_step_signal_contract.md`
  - `docs/architecture/walk_forward_validation_contract.md`

## Walk-Forward 실행
- v2 4년 창 / 2년 슬라이드 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.walk_forward --preset v2 --window-years 4 --step-years 2`
- v3.3 4년 창 / 2년 슬라이드 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.walk_forward --preset v3.3 --window-years 4 --step-years 2`
- 결과 저장(`parquet` + `summary.json`):
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.walk_forward --preset v2 --window-years 4 --step-years 2 --save`

## 결과 레지스트리 조회
- 저장 경로: `PRETREND_RESULT_ROOT/backtest/registry/pipeline=*/run_date=*/registry.parquet`
- 권장: 같은 구간(v2/v3.1/v3.2/v3.3) 실행 후 registry 기반 비교표를 재생성해 실행결과와 일치성 확인

## Backtest 테스트 실행
- Backtest 테스트:
  - `conda run -n pytest-pretrend pytest tests/pipeline/backtest/ -v`

## Airflow 서비스 관리 (systemd)

서비스 파일 위치: `airflow_pretrend/airflow-scheduler.service`, `airflow_pretrend/airflow-webserver.service`
시스템 등록 위치: `/etc/systemd/system/`
환경변수 파일: `.env.airflow` (EnvironmentFile 지시자로 로드)

### 핵심 구성 요소
- **WorkingDirectory**: 프로젝트 루트 (`/home/redtable/Desktop/ethan/pretrend/pretrend_ai`)
- **PATH**: conda 환경 bin 디렉토리 포함 (SequentialExecutor subprocess에서 `airflow` 명령 사용)
- **EnvironmentFile**: `.env.airflow` — FRED_API_KEY, TELEGRAM 토큰, DAGS_FOLDER, DEFAULT_TIMEZONE 등
- **AIRFLOW__CORE__DEFAULT_TIMEZONE**: `Asia/Seoul` (`.env.airflow`에서 설정)

### 최초 등록 / 서비스 파일 업데이트
서비스 파일 수정 후 반드시 복사 + daemon-reload + restart:
```bash
sudo cp airflow_pretrend/airflow-scheduler.service /etc/systemd/system/
sudo cp airflow_pretrend/airflow-webserver.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable airflow-scheduler airflow-webserver
sudo systemctl restart airflow-scheduler airflow-webserver
```

### 서비스 상태 확인
```bash
systemctl status airflow-scheduler --no-pager
systemctl status airflow-webserver --no-pager
```

### 서비스 시작 / 중지 / 재시작
```bash
sudo systemctl start airflow-scheduler airflow-webserver
sudo systemctl stop airflow-scheduler airflow-webserver
sudo systemctl restart airflow-scheduler airflow-webserver
```

### 로그 확인
재시작 시 덮어쓰기 — 최신 실행 로그만 유지된다.
```bash
# 실시간 스트림
tail -f airflow_pretrend/logs/scheduler.log
tail -f airflow_pretrend/logs/webserver.log

# 에러만
tail -f airflow_pretrend/logs/scheduler-error.log
tail -f airflow_pretrend/logs/webserver-error.log
```

### DAG별 태스크 로그
Airflow 내부 태스크 로그는 systemd와 무관하게 AIRFLOW_HOME 아래에 누적된다.
```bash
ls airflow_pretrend/logs/dag_id=*/run_id=*/task_id=*/
```

### 트러블슈팅
| 증상 | 원인 | 조치 |
|------|------|------|
| Scheduler restart loop (`FileNotFoundError: 'airflow'`) | systemd 서비스에 PATH 미설정 | 서비스 파일에 `Environment=PATH=...` 추가 후 재배포 |
| `.env.airflow` 변수 미적용 (TIMEZONE=utc 등) | `EnvironmentFile` 누락 또는 대시 prefix(`-`) | `EnvironmentFile=/path/.env.airflow` (대시 없이) 설정 |
| DAG 미인식 | `DAGS_FOLDER` 경로 불일치 | `.env.airflow`의 `AIRFLOW__CORE__DAGS_FOLDER` 확인 |
| 서비스 파일 수정 후 반영 안됨 | `/etc/systemd/system/`에 복사 안됨 | `sudo cp` + `daemon-reload` + `restart` |

환경변수 확인 (실행 중 프로세스):
```bash
cat /proc/$(systemctl show airflow-scheduler -p MainPID --value)/environ | tr '\0' '\n' | grep -E "TIMEZONE|DAGS_FOLDER"
```

## Airflow DAG 스케줄 요약

| DAG | 스케줄 (KST) | 설명 |
|-----|-------------|------|
| `eod_pipeline_dag` | 매일 08:00 KST | EOD Bronze→Silver→Gold (미국 장 마감 후 2시간+) |
| `macro_pipeline_dag` | 매일 09:00 KST | FRED Macro Bronze→Silver→Gold |
| `strategy_engine_dag` | 매일 10:00 KST | Strategy Engine 7단계 + Telegram 리포트 |
| `paper_trading_dag` | 매일 10:30 KST | Paper Trading 일일 요약 + Telegram(PAPER_RESULT) |

실행 순서: EOD(08:00) → Macro(09:00) → Strategy(10:00) → Paper(10:30), 고정 시간으로 의존성 보장.
모든 DAG의 `start_date`는 `tz="Asia/Seoul"` 기준이며, `default_timezone=Asia/Seoul`로 설정됨.

### Telegram 알림 설정
`.env.airflow`에 설정 (systemd가 EnvironmentFile로 로드):
```
TELEGRAM_BOT_TOKEN=<bot_token>
TELEGRAM_CHAT_ID=<chat_id>
```
미설정 시 알림만 스킵되고 파이프라인은 정상 실행된다.

Telegram 표기 기준(혼동 방지):
- `중기 성향`: `mid_regime` 표시 별칭 (`RISK_ON/NEUTRAL/RISK_OFF`)
- `단기 공황 여부`: 사용자 표시 별칭 (`is_panic = not risk_gate`)
  - `예` = 단기 PANIC
  - `아니오` = 단기 정상
- `전술 실행`: `run_universe` 스위치 표시 (`허용/제한`)
- `message_type`:
  - `SIGNAL` = `strategy_engine_dag` 메시지
  - `PAPER_RESULT` = `paper_trading_dag` 메시지
- snapshot 단일소스 원칙:
  - SIGNAL/PAPER의 next-step 표시는 `next_step_signal snapshot` 값을 직접 소비한다.
  - snapshot 결측 시 즉석 재계산 없이 `UNKNOWN/N/A` fail-open 표기만 허용한다.
- SIGNAL `다음 스텝 가설` 표기:
  - `10D bias+confidence + transition_hazard_10d + transition_expected_10d` 상세
  - `5D/20D/60D/120D bias+confidence` 요약 1줄
  - `horizon_bias_diversity_count`, `horizon_bias_diversity_ratio_60d`, `horizon_conf_spread` 진단 1줄
- SIGNAL `전술 그룹 다음 스텝` 표기:
  - `asset_group별 state_now -> expected_10d`
  - `group_transition_hazard_10d` (결측 시 `N/A`)
- PAPER_RESULT `게이트/강도` 표기:
  - `effective_bias`, `bias_source`, `override_reason`
  - `hard_gate(run_universe/risk_gate)`
  - `effective_max_tactical_slots`, `effective_tactical_weight`, `hazard_10d`
  - `paper_start_date` (누적 시뮬레이션 시작일)
- PAPER_RESULT `전술 적용 근거` 표기:
  - `group_gate_applied_groups`, `group_gate_reduced_groups`, `group_gate_source`
- 실패 정책:
  - Telegram 전송 오류/토큰 미설정 시 fail-open (경고 로그만 남기고 DAG 성공 유지)

### SIGNAL 메시지 구조 (8섹션 고정)

`strategy_engine_dag`가 생성하는 SIGNAL 메시지는 아래 8개 섹션으로 고정된다.
섹션 순서·헤더 문자열은 계약 변경 없이 변경 불가.

| 순서 | 섹션 헤더 | 표시 내용 | 비고 |
|------|-----------|-----------|------|
| 1 | 헤더 | 날짜 · `message_type=SIGNAL` · `source_job=strategy_engine_dag` · action(비중 변화) | 공황 시 `⚠️ 단기 공황 — 매도 동결` 삽입 |
| 2 | `── 시장 컨텍스트 ──` | 3-state(장기/중기/단기) + 스위치(공황여부/전술실행) | `build_context_lines()` + `build_switch_lines()` |
| 3 | `── 다음 스텝 가설 ──` | **10D 상세** (bias/hazard/expected) + 지평 요약(5/20/60/120D) + 분화도 | **10D 중심 원칙** |
| 4 | `── 시장 근거 ──` | 4축(매크로·가격·수급구조·심리) | `build_evidence_lines()` |
| 5 | `── 진단 요약 ──` | 12셀 품질 (coverage/unknown 비율) | snapshot 결측 시 즉석 계산 fallback |
| 6 | `── 전술 그룹 다음 스텝 ──` | asset_group별 state→expected(5D/10D) + hazard | `format_group_transition_lines()` |
| 7 | `── 전술 ETF (SPY 대비 20일 상대강도) ──` | 그룹별 상위 ETF + RS 수치 | COUNTRY→COMMODITY→BOND→SECTOR 순 |

**10D-centric 원칙**: `다음 스텝 가설` 섹션에서 10D bias/hazard/expected를 1차(상단)로 표시하고,
나머지 지평(5D·20D·60D·120D)은 한 줄 요약으로 압축한다. 10D는 요약 줄에 포함하지 않는다.

