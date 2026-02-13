"""
Policy Selector schema — Composer 최종 출력 컬럼 정의.

Market Position + Policy Config resolve = 완전한 Composer 출력.

SOT: docs/strategy_engine_design.md §A3
Contract: docs/architecture/market_structure_composer_contract.md §4
"""
from __future__ import annotations

from typing import List

POLICY_SELECTION_COLUMNS: List[str] = [
    "trade_date",
    "long_phase",
    "mid_regime",
    "short_signal",
    "run_universe",
    "risk_gate",
    "policy_profile_id",
    "target_invested_lower",
    "target_invested_upper",
    "adjustment_limit",
    "step_size",
    "policy_version",
    "notes",
    "source_run_id",
]
