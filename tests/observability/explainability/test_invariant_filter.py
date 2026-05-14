from __future__ import annotations

import pytest

from pretrend.observability.explainability.llm_client import (
    FORBIDDEN_TERMS,
    InvariantViolationError,
    check_invariant_or_raise,
)


@pytest.mark.parametrize("term", FORBIDDEN_TERMS)
def test_invariant_filter_blocks_forbidden_terms(term: str) -> None:
    with pytest.raises(InvariantViolationError):
        check_invariant_or_raise(f"bad {term} value")


def test_invariant_filter_allows_observational_schema_name() -> None:
    check_invariant_or_raise("short_signal_code is an observed regime field")
