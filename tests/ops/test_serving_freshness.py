from __future__ import annotations

from datetime import date

import pytest

from pretrend.ops.serving_freshness import (
    ServingFreshnessSnapshot,
    evaluate_serving_freshness,
    evaluate_serving_freshness_many,
)


pytestmark = pytest.mark.invariant


def test_ofs_101_serving_freshness_detects_gold_postgres_lag() -> None:
    """OFS-101: API health가 정상이어도 serving mirror가 Gold보다 뒤처지면 실패해야 한다."""
    result = evaluate_serving_freshness(
        ServingFreshnessSnapshot(
            table="gold_eod_features",
            gold_max_date=date(2026, 5, 15),
            serving_max_date=date(2026, 5, 10),
            gold_row_count=100,
            serving_row_count=80,
            allowed_lag_days=1,
        )
    )

    assert result.ok is False
    assert result.reason == "serving_lag"
    assert result.lag_days == 5


def test_ofs_101_serving_freshness_allows_declared_lag_window() -> None:
    """OFS-101: 허용 지연 범위 안이면 freshness gate를 통과한다."""
    result = evaluate_serving_freshness(
        ServingFreshnessSnapshot(
            table="gold_macro_features",
            gold_max_date=date(2026, 5, 15),
            serving_max_date=date(2026, 5, 14),
            allowed_lag_days=1,
        )
    )

    assert result.ok is True
    assert result.reason == "fresh"
    assert result.lag_days == 1


def test_ofs_101_serving_freshness_treats_empty_serving_as_failure() -> None:
    """OFS-101: Gold에는 데이터가 있는데 serving mirror가 비어 있으면 운영 장애다."""
    result = evaluate_serving_freshness(
        ServingFreshnessSnapshot(
            table="gold_macro_features",
            gold_max_date=date(2026, 5, 15),
            serving_max_date=None,
            gold_row_count=100,
            serving_row_count=0,
        )
    )

    assert result.ok is False
    assert result.reason == "serving_empty"


def test_ofs_101_serving_freshness_many_keeps_table_identity() -> None:
    results = evaluate_serving_freshness_many(
        [
            ServingFreshnessSnapshot(
                table="gold_macro_features",
                gold_max_date=date(2026, 5, 15),
                serving_max_date=date(2026, 5, 15),
            ),
            ServingFreshnessSnapshot(
                table="gold_eod_features",
                gold_max_date=date(2026, 5, 15),
                serving_max_date=date(2026, 5, 1),
            ),
        ]
    )

    assert [(result.table, result.ok) for result in results] == [
        ("gold_macro_features", True),
        ("gold_eod_features", False),
    ]
