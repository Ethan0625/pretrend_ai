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
