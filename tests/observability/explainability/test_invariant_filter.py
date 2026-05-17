from __future__ import annotations

import pytest

from pretrend.observability.explainability.llm_client import (
    FORBIDDEN_TERMS,
    InvariantViolationError,
    check_invariant_or_raise,
)


@pytest.mark.parametrize("term", FORBIDDEN_TERMS)
def test_invariant_filter_blocks_forbidden_terms(term: str) -> None:
    """OFS-103: explainability/report text는 예측·추천·매매 판단 용어를 통과시키지 않는다."""
    with pytest.raises(InvariantViolationError):
        check_invariant_or_raise(f"bad {term} value")


def test_invariant_filter_allows_observational_schema_name() -> None:
    check_invariant_or_raise("short_signal_code is an observed regime field")
