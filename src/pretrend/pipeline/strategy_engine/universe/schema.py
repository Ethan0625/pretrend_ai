"""
Universe Selector schema.

Contract: docs/architecture/universe_contract.md §4
"""
from __future__ import annotations

from typing import FrozenSet, List

ASSET_GROUP_ENUM: FrozenSet[str] = frozenset({
    "INDEX", "COUNTRY", "COMMODITY", "BOND", "SECTOR",
})

UNIVERSE_OUTPUT_COLUMNS: List[str] = [
    "decision_date",
    "symbol",
    "asset_group",
    "relative_strength",
    "is_candidate",
]
