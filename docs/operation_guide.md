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
- v0(range-maintenance) 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v0`
- v1(target-seeking) 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v1`
- v2(2D target-seeking: long_phase × mid_regime) 실행:
  - `PYTHONPATH=src python -m pretrend.pipeline.backtest.runner --start 2006-01-03 --end 2024-06-03 --preset v2`
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
