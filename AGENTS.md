# Pretrend — Codex Operating Rules

## Scope & Safety
- This repo is a production-like portfolio project. Prefer minimal, reviewable diffs.
- Never hardcode secrets. Use DEMO_KEY / EXAMPLE_TOKEN in examples only.
- Do not change public API signatures unless explicitly requested.
- Preserve pipeline idempotency and partition overwrite behavior.

## Required Workflow (always)
1) Write a short plan: files to touch + why.
2) Implement changes with small diffs (one task per PR, prefer <= 300 LOC).
3) Suggest exact commands for verification (pytest, formatters). Do NOT claim you ran them unless you actually did.
4) Update docs/README if behavior/schema changes.
5) Summarize: what changed / why / risks / rollback.

## Testing
- For any pipeline logic change: add/update at least 2 pytest cases.
- Prefer tests in existing style under tests/ (match fixtures/patterns).

## Output Format
- Changed files list
- Commands to run
- Risks & rollback steps
