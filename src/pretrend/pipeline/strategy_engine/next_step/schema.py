"""Next Step Signal schema constants."""
from __future__ import annotations

from typing import FrozenSet, List

NEXT_STEP_BIAS_ENUM: FrozenSet[str] = frozenset(
    {"RISK_ON_BIAS", "NEUTRAL_BIAS", "RISK_OFF_BIAS", "UNKNOWN"}
)

NEXT_STEP_SIGNAL_COLUMNS: List[str] = [
    "trade_date",
    "bias_1m",
    "confidence_1m",
    "bias_3m",
    "confidence_3m",
    # v3.2 extension ports (nullable)
    "bias_effective",
    "bias_override_flag",
    "bias_override_reason",
    # v3.3 hypothesis extension ports (nullable)
    "state_age_days",
    "sojourn_prob_5d",
    "sojourn_prob_10d",
    "sojourn_prob_20d",
    "transition_hazard_5d",
    "transition_hazard_10d",
    "transition_hazard_20d",
    "transition_expected",
    "evidence_axis_macro",
    "evidence_axis_price",
    "evidence_axis_flow",
    "evidence_axis_sentiment",
    "evidence_quality_score",
    "evidence_unknown_ratio",
    "diag_12slot_coverage",
    "diag_12slot_quality",
    "source_run_id",
]
