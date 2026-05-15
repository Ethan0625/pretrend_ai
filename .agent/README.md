# Agent Docs Publication Guide

Markers: agent, security, operation
Status: active
Publication: public

## Purpose

This directory contains agent operating rules and task state. Publication is whitelist-only because some files contain local paths, session history, or private operator notes.

## Public Whitelist

The following files are intended to be safe for Git publication:

```text
AGENTS.md
CLAUDE.md
.agent/README.md
.agent/STABLE_CONTEXT.md
.agent/INVARIANTS.md
.agent/WORKFLOW.md
.agent/CHANGE_GATES.md
.agent/TASK_QUEUE.md
.agent/TASK_TEMPLATE.md
.agent/PARENTS_TASK_TEMPLATE.md
.agent/task/P30_parent_reproducible_runtime.md
.agent/task/P30-0_formalize_runtime_contract.md
.agent/task/P30-1_runtime_volume_contract.md
.agent/task/P30-2_docker_build_test_runtime.md
.agent/task/P30-3_data_bootstrap_db_restore_contract.md
.agent/task/P30-4_reproducibility_verification.md
.agent/task/P30-5_agent_docs_publication_safety.md
.agent/task/P30-6_docs_marker_classification.md
```

## Excluded By Default

The following files and directories remain private unless a future task explicitly reviews and whitelists them:

```text
.agent/settings.local.json
.agent/RUN_LOG.md
.agent/task/archive/
.agent/*.code-workspace
.agent/After_Phase2_Plan.md
.agent/DIRECTION.md
.agent/REFACTOR_2026Q2.md
.agent/REPORT_TASK_QUEUE_AUDIT.md
.agent/PROMPTS.md
```

Exclusion reasons:

- Local machine paths or external private planning note references.
- Session logs and historical handoff records.
- Workspace/editor files.
- Archive/history files that are not required for a fresh clone.

## Marker Policy

Docs marker vocabulary is defined in `docs/README.md`.

Publication rules:

- `agent`, `operation`, `contract`, `testing`, and `architecture` docs can be public after secret/local-path scan.
- `security` docs require explicit review before publication.
- `legacy` docs are reference-only and are not promoted to active source of truth by publication.
- Archive/history docs stay private by default even if they contain useful context.

## Safety Checks

Use these checks before staging publication changes:

```bash
git check-ignore -v .agent/RUN_LOG.md .agent/settings.local.json
git status --short --ignored .agent AGENTS.md CLAUDE.md
grep -RIlE "(API_KEY|TOKEN|SECRET|PASSWORD|[\\/]home[\\/][^[:space:]]+|\\.env.airflow)" AGENTS.md CLAUDE.md .agent/README.md .agent/STABLE_CONTEXT.md .agent/INVARIANTS.md .agent/WORKFLOW.md .agent/CHANGE_GATES.md .agent/TASK_QUEUE.md .agent/TASK_TEMPLATE.md .agent/PARENTS_TASK_TEMPLATE.md .agent/task/P30_parent_reproducible_runtime.md .agent/task/P30-[0-9]*.md
```

The grep check is a review aid, not an automatic failure by itself. Placeholder key names and policy text are allowed; actual secret values and local absolute paths are not allowed.
