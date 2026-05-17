"""
Market Position schema — 상태 벡터 출력 컬럼 정의.

SOT: docs/architecture/strategy_engine_design.md §A3, §B
Contract: docs/architecture/market_structure_composer_contract.md §4
"""
from __future__ import annotations

from typing import List

MARKET_POSITION_COLUMNS: List[str] = [
    "trade_date",
    "long_phase",
    "mid_regime",
    "short_signal",
    "run_universe",
    "risk_gate",
    "notes",
    "source_run_id",
]
