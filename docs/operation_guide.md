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
