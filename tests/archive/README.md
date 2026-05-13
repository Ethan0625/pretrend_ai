# Test Archive

## Purpose

`tests/archive/` preserves frozen-track regression tests that are no longer part of the default active pytest surface.

## Why Excluded From Default Pytest

Personal Track code is frozen and operationally stopped. Default pytest is reserved for active Observability and Infrastructure work.

## Manual Run Command

```bash
conda run -n pytest-pretrend pytest tests/archive/personal/ -q --tb=short
```

## When To Run

Run the archive suite when frozen Personal Track code changes, when validating legacy behavior, or when comparing against pre-archive regression status.
