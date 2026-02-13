"""
Axis × Horizon State schema — ENUM 상수 및 출력 컬럼 정의.

SOT: docs/strategy_engine_design.md §A3, §F
Contract:
  - docs/architecture/market_structure_long_v1_contract.md
  - docs/architecture/market_structure_mid_v1_contract.md
  - docs/architecture/market_structure_short_v1_contract.md
  - docs/architecture/axis_horizon_dependency_v1_contract.md
"""
from __future__ import annotations

from typing import FrozenSet, List

# ── Long Phase ENUM ──────────────────────────────────────

LONG_PHASE_ENUM: FrozenSet[str] = frozenset({
    "EXPANSION",
    "LATE_CYCLE",
    "SLOWDOWN",
    "RECESSION",
    "RECOVERY",
    "UNKNOWN",
})

# ── Mid Regime ENUM ──────────────────────────────────────

MID_REGIME_ENUM: FrozenSet[str] = frozenset({
    "RISK_ON",
    "NEUTRAL",
    "RISK_OFF",
    "UNKNOWN",
})

# ── Short Signal ENUM ────────────────────────────────────

SHORT_SIGNAL_ENUM: FrozenSet[str] = frozenset({
    "PANIC",
    "STABLE",
    "RELIEF",
    "UNKNOWN",
})

# ── Output Columns ───────────────────────────────────────

LONG_OUTPUT_COLUMNS: List[str] = [
    "trade_date",
    "long_phase",
    "long_phase_confidence",
    "source_run_id",
]

MID_OUTPUT_COLUMNS: List[str] = [
    "trade_date",
    "mid_regime",
    "mid_regime_confidence",
    "source_run_id",
]

SHORT_OUTPUT_COLUMNS: List[str] = [
    "trade_date",
    "short_signal",
    "short_signal_confidence",
    "source_run_id",
]

# ── 12-Slot Combined Output ──────────────────────────────

AXIS_HORIZON_STATE_COLUMNS: List[str] = [
    "trade_date",
    "long_phase",
    "long_phase_confidence",
    "mid_regime",
    "mid_regime_confidence",
    "short_signal",
    "short_signal_confidence",
    "source_run_id",
]
