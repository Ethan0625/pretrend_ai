"""
Sell Advisor schema.

SOT: docs/strategy_engine_design.md §D3
"""
from __future__ import annotations

from typing import List

SELL_ADVICE_OUTPUT_COLUMNS: List[str] = [
    "decision_date",
    "sell_budget_ratio",
    "sell_priority_list",
    "rationale_tags",
    "execution_notes",
]
