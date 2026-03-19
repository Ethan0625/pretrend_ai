"""Next Step Signal schema constants."""
from __future__ import annotations

from typing import FrozenSet, List

NEXT_STEP_BIAS_ENUM: FrozenSet[str] = frozenset(
    {"RISK_ON_BIAS", "NEUTRAL_BIAS", "RISK_OFF_BIAS", "UNKNOWN"}
)

NEXT_STEP_SIGNAL_COLUMNS: List[str] = [
    "trade_date",
    # v3.5: trading-day horizons (5/10/20/60/120D)
    "bias_5d",
    "confidence_5d",
    "bias_10d",
    "confidence_10d",
    "bias_20d",
    "confidence_20d",
    "bias_60d",
    "confidence_60d",
    "bias_120d",
    "confidence_120d",
    # v3.2 extension ports (nullable)
    "bias_effective",
    "bias_override_flag",
    "bias_override_reason",
    # phase-aware bias state machine metadata (nullable)
    "bias_state_source",
    "bias_switch_flag",
    "bias_switch_reason",
    "bias_cooldown_left",
    "bias_candidate_20d",
    "cooldown_compressed_flag",
    "cooldown_compressed_reason",
    "hard_gate_exit_assist_flag",
    "hard_gate_exit_assist_reason",
    # v3.3 hypothesis extension ports (nullable)
    "state_age_days",
    "sojourn_prob_5d",
    "sojourn_prob_10d",
    "sojourn_prob_20d",
    "sojourn_prob_60d",
    "sojourn_prob_120d",
    "transition_hazard_5d",
    "transition_hazard_10d",
    "transition_hazard_20d",
    "transition_hazard_60d",
    "transition_hazard_120d",
    "transition_expected_5d",
    "transition_expected_10d",
    "transition_expected_20d",
    "transition_expected_60d",
    "transition_expected_120d",
    "evidence_axis_macro",
    "evidence_axis_price",
    "evidence_axis_flow",
    "evidence_axis_sentiment",
    "evidence_quality_score",
    "evidence_unknown_ratio",
    "diag_12slot_coverage",
    "diag_12slot_quality",
    # P1-1 diagnostics (nullable, backward compatible)
    "horizon_bias_diversity_count",
    "horizon_bias_diversity_ratio_60d",
    "horizon_conf_spread",
    "source_run_id",
]
