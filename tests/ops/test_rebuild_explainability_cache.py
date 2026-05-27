from __future__ import annotations

from datetime import date

import pytest

from pretrend.ops.rebuild_explainability_cache import _query_dates, _use_cases


def test_query_dates_supports_days_back_window() -> None:
    assert _query_dates("2026-05-20", 3) == [
        date(2026, 5, 18),
        date(2026, 5, 19),
        date(2026, 5, 20),
    ]


def test_query_dates_supports_explicit_period() -> None:
    assert _query_dates(None, 1, "2026-05-13", "2026-05-15") == [
        date(2026, 5, 13),
        date(2026, 5, 14),
        date(2026, 5, 15),
    ]


def test_query_dates_requires_complete_period_bounds() -> None:
    with pytest.raises(ValueError, match="provided together"):
        _query_dates(None, 1, "2026-05-13", None)


def test_query_dates_rejects_reversed_period() -> None:
    with pytest.raises(ValueError, match="before or equal"):
        _query_dates(None, 1, "2026-05-20", "2026-05-13")


def test_use_cases_defaults_to_all_cache_surfaces() -> None:
    assert _use_cases(None) == {"similarity_events", "regime", "macro"}
    assert _use_cases(["all"]) == {"similarity_events", "regime", "macro"}


def test_use_cases_supports_explicit_subset() -> None:
    assert _use_cases(["similarity_regime", "regime", "macro"]) == {
        "similarity_regime",
        "regime",
        "macro",
    }
