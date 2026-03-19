"""
Allocation Engine schema.

Contract: docs/architecture/allocation_engine_contract.md §5
"""
from __future__ import annotations

from typing import FrozenSet, List

ACTION_ENUM: FrozenSet[str] = frozenset({"INCREASE", "DECREASE", "HOLD"})

ALLOCATION_OUTPUT_COLUMNS: List[str] = [
    "trade_date",
    "action",
    "next_invested_ratio",
    "delta_ratio",
    "blocked_by_risk_gate",
    "notes",
]
