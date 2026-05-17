from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ServingFreshnessSnapshot:
    table: str
    gold_max_date: date | None
    serving_max_date: date | None
    gold_row_count: int | None = None
    serving_row_count: int | None = None
    allowed_lag_days: int = 0


@dataclass(frozen=True)
class ServingFreshnessResult:
    table: str
    ok: bool
    reason: str
    lag_days: int | None


def evaluate_serving_freshness(
    snapshot: ServingFreshnessSnapshot,
) -> ServingFreshnessResult:
    """Compare Gold SOT coverage with its Postgres serving mirror."""
    if snapshot.gold_max_date is None:
        return ServingFreshnessResult(
            table=snapshot.table,
            ok=True,
            reason="gold_empty",
            lag_days=None,
        )

    if snapshot.serving_max_date is None:
        return ServingFreshnessResult(
            table=snapshot.table,
            ok=False,
            reason="serving_empty",
            lag_days=None,
        )

    lag_days = (snapshot.gold_max_date - snapshot.serving_max_date).days
    if lag_days <= snapshot.allowed_lag_days:
        return ServingFreshnessResult(
            table=snapshot.table,
            ok=True,
            reason="fresh",
            lag_days=lag_days,
        )

    return ServingFreshnessResult(
        table=snapshot.table,
        ok=False,
        reason="serving_lag",
        lag_days=lag_days,
    )


def evaluate_serving_freshness_many(
    snapshots: list[ServingFreshnessSnapshot],
) -> list[ServingFreshnessResult]:
    return [evaluate_serving_freshness(snapshot) for snapshot in snapshots]
