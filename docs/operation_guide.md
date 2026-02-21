# Operation Guide

## Agent-assisted development (Codex)
- **Workflow:** `dev` → `codex/<task>` 분기 → 작업/커밋 → PR/머지 → `dev` 반영.
- **Verification checklist:** `pytest -q` (필요 시 대상 파일 예: `pytest -q tests/pipeline/<file>.py`), `git diff --cached`.
- **Guardrails:** `AGENTS.md` 준수, 비공개 정보/시크릿 금지, 요청 없는 공개 API 변경 금지, 파티션 overwrite·멱등성 보존.
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
  - `PYTHONPATH=src python -m pretrend.pipeline.strategy_engine.strategy_job --date 2024-06-03 --invested-ratio 0.10 --z-threshold 0.3`
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

## 통합 테스트 실행
- 전체 테스트:
  - `conda run -n pytest-pretrend pytest tests/ -v`
- 2026-02-21 기준 보고:
  - `305 passed, 1 skipped`

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
- v2 + DCA 월 적립금 지정 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v2 --monthly-addition 300`
- v1 + tactical override 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v1 --tactical SECTOR COMMODITY`

## Walk-Forward 실행
- v2 4년 창 / 2년 슬라이드 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.walk_forward --preset v2 --window-years 4 --step-years 2`
- 결과 저장(`parquet` + `summary.json`):
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.walk_forward --preset v2 --window-years 4 --step-years 2 --save`

## Backtest 테스트 실행
- Backtest 테스트:
  - `conda run -n pytest-pretrend pytest tests/pipeline/backtest/ -v`

## Airflow 서비스 관리 (systemd)

서비스 파일 위치: `airflow_pretrend/airflow-scheduler.service`, `airflow_pretrend/airflow-webserver.service`
시스템 등록 위치: `/etc/systemd/system/`

### 최초 등록
```bash
sudo cp airflow_pretrend/airflow-scheduler.service /etc/systemd/system/
sudo cp airflow_pretrend/airflow-webserver.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable airflow-scheduler airflow-webserver
sudo systemctl start airflow-scheduler airflow-webserver
```

### 서비스 상태 확인
```bash
sudo systemctl status airflow-scheduler
sudo systemctl status airflow-webserver
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

## Airflow DAG 스케줄 요약

| DAG | 스케줄 | 설명 |
|-----|--------|------|
| `macro_pipeline_dag` | 매일 09:00 UTC | FRED Macro Bronze→Silver |
| `eod_pipeline_dag` | 매일 08:00 UTC | EOD Bronze→Silver→Gold |
| `strategy_engine_dag` | 매일 10:00 UTC | Strategy Engine 7단계 + Telegram 리포트 |

실행 순서: EOD(08:00) → Macro(09:00) → Strategy(10:00), 고정 시간으로 의존성 보장.

### Telegram 알림 설정
`.env` 또는 systemd 서비스 파일의 `Environment=` 항목에 추가:
```
TELEGRAM_BOT_TOKEN=<bot_token>
TELEGRAM_CHAT_ID=<chat_id>
```
미설정 시 알림만 스킵되고 파이프라인은 정상 실행된다.
