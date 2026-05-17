"""
Axis × Horizon State schema — ENUM 상수 및 출력 컬럼 정의.

SOT: docs/architecture/strategy_engine_design.md §A3, §F
Contract:
  - docs/architecture/market_structure_long_v1_contract.md
  - docs/architecture/market_structure_mid_v1_contract.md
  - docs/architecture/market_structure_short_v1_contract.md
  - docs/architecture/axis_horizon_dependency_contract.md
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
    "long_detail_json",
    "source_run_id",
]

MID_OUTPUT_COLUMNS: List[str] = [
    "trade_date",
    "mid_regime",
    "mid_regime_confidence",
    "mid_detail_json",
    "source_run_id",
]

SHORT_OUTPUT_COLUMNS: List[str] = [
    "trade_date",
    "short_signal",
    "short_signal_confidence",
    "short_detail_json",
    "source_run_id",
]

# ── Combined Output (3-state + details) ──────────────────

AXIS_HORIZON_STATE_COLUMNS: List[str] = [
    "trade_date",
    "long_phase",
    "long_phase_confidence",
    "long_detail_json",
    "mid_regime",
    "mid_regime_confidence",
    "mid_detail_json",
    "short_signal",
    "short_signal_confidence",
    "short_detail_json",
    "source_run_id",
]
